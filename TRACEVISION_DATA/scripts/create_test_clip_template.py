#!/usr/bin/env python
"""Phase 0D - generate the BLANK annotation files the team fills in by hand. Nothing is labelled here.

Outputs (in --out, default TRACEVISION_DATA/evaluation):
  clips.csv                         one row per clip found in --videos (clip_id, file, duration, size, fps
                                    pre-filled from the video header; source / url / licence / country /
                                    camera_id / scenarios BLANK for the team). Existing rows are kept.
  test_clip_labels_TEMPLATE.csv     the spec's label columns. --rows-per-clip blank rows per clip with only
                                    clip_id (+ source/licence/country/camera_id copied from clips.csv if
                                    filled) and a target_vehicle_id placeholder. Plate text, colour, type,
                                    make/model, in_registry and cross-camera ids are ALWAYS left blank.
  LABELING_GUIDE.md                 allowed values and rules (uppercase, no spaces, `?` for unreadable chars)

The team copies the template to test_clip_labels.csv, fills it in, then runs validate_test_labels.py.
It refuses to overwrite an existing filled test_clip_labels.csv (that file is never written by this script).

Deps  opencv-python (only to read clip headers)
Usage
  python TRACEVISION_DATA/scripts/create_test_clip_template.py --videos TRACEVISION_DATA/raw/test_videos --out TRACEVISION_DATA/evaluation
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

try:
    import cv2
except ImportError as e:
    sys.exit(f"missing dependency: {e}")

VID_EXT = {".mp4", ".avi", ".mov", ".mkv", ".m4v", ".webm"}
LABEL_COLUMNS = [
    "clip_id", "source", "source_url", "licence", "country", "camera_id", "target_vehicle_id",
    "first_frame", "last_frame", "timestamp_first", "vehicle_bbox_first_frame",
    "plate_bbox_first_frame", "plate_text_truth", "unreadable_positions",
    "plate_readability", "colour", "vehicle_type", "make", "model",
    "in_registry", "cross_camera_group_id", "notes",
    # extra (documented in LABELING_GUIDE.md): full plate known from OUTSIDE the clip (e.g. we filmed our own
    # car); needed to seed the registry when plate_text_truth contains '?'. Leave blank if unknown.
    "registry_plate_full",
]
CLIP_COLUMNS = ["clip_id", "file", "duration_s", "width", "height", "fps", "source", "source_url", "licence",
                "country", "camera_id", "time_of_day", "scenarios_covered", "notes"]
COLOURS = ["white", "black", "silver", "grey", "red", "blue", "green", "yellow", "brown", "orange", "other", "unknown"]
TYPES = ["car", "SUV", "motorcycle", "scooter", "auto_rickshaw", "bus", "truck", "van", "bicycle", "other", "unknown"]

GUIDE = f"""# Test-clip labelling guide (Phase 0D)

**Only humans write these labels. Never guess a character: write `?`.** These labels are the answer key the whole system is graded against.

## Step by step (about 5–10 minutes per clip)

**0. Get the files.** `git pull`, then `git lfs pull`. The clips are in `TRACEVISION_DATA/raw/test_videos/` (clip01–09). clip10 and clip11 are Pexels stock and not in git: download them from the links in `clips.csv`, choosing the original 4K quality, and save them as `clip10.mp4` and `clip11.mp4`.

**1. Split the clips between labellers,** so two people never edit the same rows. For example: A takes clip01–04, B takes clip05–08, C takes clip09–11.
**Easiest way to work together:** import `test_clip_labels_TEMPLATE.csv` into one shared Google Sheet. Everyone fills only their own clips' rows. When finished, use File → Download → CSV, save it as `TRACEVISION_DATA/evaluation/test_clip_labels.csv` and commit it.

**2. Pick 3–5 target vehicles per clip.** Open `processed/test_video_frames/clipNN/contact_sheet_fps2.jpg`. Every thumbnail shows its **frame number** and time. Good targets:
- stay visible for at least 2–3 s
- show their plate at some point, even partly (partly readable plates are valuable)
- vary the type: car, two-wheeler, auto, truck or bus
On clip02 and clip06 (high, far views), plates are mostly unreadable. Label them `none`; the vehicle's type and colour still count.

**3. For each target, fill one row.** Add rows if you need more than 3 for a clip, giving them new ids such as `clip04_v04`.
- **first_frame / last_frame:** the frame numbers from the contact sheet where the vehicle first and last appears usefully.
- **timestamp_first:** the time shown on the thumbnail, in seconds.
- **vehicle_bbox_first_frame:** run `extract_test_video_frames.py` once to get full-size frames, or open the clip in a player at that time. Then open the frame in **Paint**: when you hover the mouse, the bottom bar shows pixel coordinates. Write the box as `x1,y1,x2,y2`, meaning top-left x, top-left y, bottom-right x, bottom-right y.
- **plate_text_truth:** zoom in (Ctrl + scroll). Write it **uppercase with no spaces**. **Write `?` for any character you cannot read.** For two-row plates, write the top row then the bottom row as one string.
- **unreadable_positions:** the positions of the `?` characters, counting from 1, e.g. `5;9`.
- **plate_readability:** `full` (no `?`), `partial` (some `?`) or `none` (nothing readable; leave the plate blank).
- **colour / vehicle_type:** use only the allowed words (table below).
- **in_registry:** `yes` or `no`. **Across all clips, mark at least 2 vehicles `no`** (the no-match test).
- **source / licence / country / camera_id:** already filled in. Leave them.

**4. Check.** Run `python TRACEVISION_DATA/scripts/validate_test_labels.py`. It lists every problem in plain English, for example "`?` positions don't match", "box outside the frame" or "colour not allowed", and **never changes your file**. Fix the rows and run it again until it reports 0 errors.

**Example row** (in a spreadsheet):
`clipXX | … | clipXX_v01 | 120 | 330 | 4.0 | 410,620,700,1010 | 470,880,600,930 | CG04AB12?4 | 9 | partial | white | SUV | | | yes | | plate partly hidden by a bike |`
The plate and numbers are invented for illustration and match no clip. Label what you actually see.

## Columns
| Column | Rule |
|---|---|
| target_vehicle_id | Unique, e.g. `clip01_v01` |
| first_frame / last_frame | **Original** frame indices (`frames_index.csv` from `extract_test_video_frames.py`, or a video player's frame counter) |
| timestamp_first | Seconds, e.g. `12.4` |
| vehicle_bbox_first_frame | `x1,y1,x2,y2` in pixels on first_frame (required) |
| plate_bbox_first_frame | Same format, optional |
| plate_text_truth | **UPPERCASE, no spaces. Write `?` for every character a human cannot read in the clip. Never guess.** Example `CG04?B12?4` |
| unreadable_positions | 1-based positions of the `?` characters, `;`-separated, e.g. `5;9`. Blank if none. |
| plate_readability | `full` (no `?`), `partial` (some `?`), `none` (no character readable: leave plate_text_truth blank) |
| colour | one of: {", ".join(COLOURS)} |
| vehicle_type | one of: {", ".join(TYPES)} |
| make / model | Only if **verified** (badge visible, or it is our own car). Otherwise blank. |
| in_registry | `yes` / `no`. **At least 2 vehicles must be `no`** (no-match test). |
| cross_camera_group_id | Same id on the rows for the same physical vehicle in **different** clips, e.g. `X1`. Only if you **know** it is the same vehicle (you filmed it). Looking similar is not enough. |
| registry_plate_full | Optional. The full plate if you know it from **outside** the clip (e.g. your own vehicle), needed to put a partly-readable vehicle into the registry. Never inferred from the video. |
| notes | Anything odd: occlusion, night, glare, two-row plate … |

## Coverage to aim for across the labelled vehicles
Clear daylight plate · blurry plate · partly occluded plate · motorcycle/scooter · auto-rickshaw · truck/bus · night (clip11) · several vehicles in one frame · similar-looking vehicles (clip04) · two-row plate (clip08, clip10) · **same vehicle in two clips (≥ 1; the car pair to be filmed later)** · **vehicle not in registry (≥ 2)** · partly visible plate with unreadable characters.

Privacy: plates of vehicles in our clips only ever go into the registry as `evaluation_seed` rows. No owner names, phone numbers or addresses anywhere.
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--videos", default="TRACEVISION_DATA/raw/test_videos")
    ap.add_argument("--out", default="TRACEVISION_DATA/evaluation")
    ap.add_argument("--rows-per-clip", type=int, default=3)
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    vids = sorted(p for p in Path(a.videos).iterdir() if p.suffix.lower() in VID_EXT) if Path(a.videos).exists() else []

    # clips.csv - keep anything the team already typed
    clips_path = out / "clips.csv"
    existing = {}
    if clips_path.exists():
        with open(clips_path, newline="", encoding="utf-8") as f:
            existing = {r["clip_id"]: r for r in csv.DictReader(f)}
    rows = []
    for p in vids:
        cap = cv2.VideoCapture(str(p))
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        hdr = {"clip_id": p.stem, "file": p.name, "duration_s": round(n / fps, 2) if fps else "",
               "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
               "fps": round(fps, 3)}
        cap.release()
        r = {c: "" for c in CLIP_COLUMNS}
        r.update(existing.get(p.stem, {}))
        r.update(hdr)  # header facts are always refreshed
        rows.append(r)
    for cid, r in existing.items():  # clips that disappeared from the folder are kept, flagged
        if cid not in {x["clip_id"] for x in rows}:
            r = {c: r.get(c, "") for c in CLIP_COLUMNS}
            r["notes"] = (r.get("notes", "") + " [file not found in videos folder]").strip()
            rows.append(r)
    with open(clips_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CLIP_COLUMNS); w.writeheader(); w.writerows(rows)

    # blank label template
    with open(out / "test_clip_labels_TEMPLATE.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LABEL_COLUMNS); w.writeheader()
        for r in rows:
            for k in range(1, a.rows_per_clip + 1):
                row = {c: "" for c in LABEL_COLUMNS}
                row.update({c: r.get(c, "") for c in ("clip_id", "source", "source_url", "licence", "country", "camera_id")})
                row["target_vehicle_id"] = f"{r['clip_id']}_v{k:02d}"
                w.writerow(row)
    (out / "LABELING_GUIDE.md").write_text(GUIDE, encoding="utf-8")
    filled = out / "test_clip_labels.csv"
    print(f"clips found: {len(vids)} | clips.csv rows: {len(rows)} | template rows: {len(vids) * a.rows_per_clip}"
          f" | filled labels file {'EXISTS (untouched)' if filled.exists() else 'not yet created'}")
    print("wrote", clips_path, out / "test_clip_labels_TEMPLATE.csv", out / "LABELING_GUIDE.md")


if __name__ == "__main__":
    main()
