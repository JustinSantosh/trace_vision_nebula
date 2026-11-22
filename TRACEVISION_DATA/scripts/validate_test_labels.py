#!/usr/bin/env python
"""Phase 0D/0E - validate the team's hand labels, then derive the evaluation records from them.

It NEVER edits the labels. Problems are reported back to the team as errors (must fix) or warnings (check).

Checks
  * required fields, unique target_vehicle_id, clip_id present in clips.csv
  * plate text: uppercase, no spaces, only A-Z 0-9 ?; Indian format with '?' as wildcard (flag, don't reject)
  * '?' agrees with unreadable_positions and plate_readability (full / partial / none)
  * colour / vehicle_type / in_registry in the allowed vocabularies
  * frames: integers, first <= last, inside the clip (if clips_meta.json from frame extraction is given)
  * bboxes: x1,y1,x2,y2 integers, x1<x2, y1<y2, inside the frame (if the size is known); plate box inside vehicle box
  * cross_camera_group_id: each group appears in >= 2 DIFFERENT clips
  * spec coverage: >= 2 vehicles with in_registry = no, >= 1 cross-camera group
  * registry seeding: in_registry = yes needs a full plate (plate_text_truth without '?', or registry_plate_full)

Outputs (only if there are no errors, or with --force-derive)
  evaluation/cross_camera_ground_truth.csv  group_id, clip_id, target_vehicle_id, frames  (from labels only)
  evaluation/multi_frame_sequences.json     one record per vehicle: frame refs + timestamps (from
      frames_index.csv when available), ground-truth visible characters and unknown positions, and EMPTY
      placeholders for plate crops, per-frame OCR, per-character confidence and the fused result (Phase 1-2)
Always: reports/test_label_validation.{md,json}

Deps  none beyond the standard library
Usage
  python TRACEVISION_DATA/scripts/validate_test_labels.py
  python TRACEVISION_DATA/scripts/validate_test_labels.py --labels ... --clips ... --frames-dir TRACEVISION_DATA/processed/test_video_frames --out-eval ... --out-report ...
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

COLOURS = {"white", "black", "silver", "grey", "red", "blue", "green", "yellow", "brown", "orange", "other", "unknown"}
TYPES = {"car", "SUV", "motorcycle", "scooter", "auto_rickshaw", "bus", "truck", "van", "bicycle", "other", "unknown"}
REQUIRED = ["clip_id", "target_vehicle_id", "first_frame", "last_frame", "vehicle_bbox_first_frame",
            "plate_readability", "colour", "vehicle_type", "in_registry"]
L, D = "[A-Z?]", "[0-9?]"
STANDARD = re.compile(rf"^{L}{{2}}{D}{{1,2}}{L}{{0,3}}{D}{{4}}$")
BH = re.compile(rf"^{D}{{2}}(BH|\?\?|B\?|\?H){D}{{4}}{L}{{1,2}}$")


def parse_box(s):
    try:
        v = [int(round(float(x))) for x in s.replace(" ", "").split(",")]
    except ValueError:
        return None
    return v if len(v) == 4 else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", default="TRACEVISION_DATA/evaluation/test_clip_labels.csv")
    ap.add_argument("--clips", default="TRACEVISION_DATA/evaluation/clips.csv")
    ap.add_argument("--frames-dir", default="TRACEVISION_DATA/processed/test_video_frames",
                    help="output of extract_test_video_frames.py (clips_meta.json, frames_index.csv)")
    ap.add_argument("--fps-setting", type=float, default=2.0, help="which sampled frame set to reference in sequences")
    ap.add_argument("--out-eval", default="TRACEVISION_DATA/evaluation")
    ap.add_argument("--out-report", default="TRACEVISION_DATA/reports")
    ap.add_argument("--force-derive", action="store_true", help="write derived files even if errors remain")
    a = ap.parse_args()

    issues = []
    add = lambda sev, vid, msg: issues.append({"severity": sev, "target_vehicle_id": vid, "issue": msg})
    if not Path(a.labels).exists():
        raise SystemExit(f"{a.labels} not found - copy test_clip_labels_TEMPLATE.csv to it and fill it in first")
    with open(a.labels, newline="", encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if any((v or "").strip() for v in r.values())]
    rows = [{k: (v or "").strip() for k, v in r.items()} for r in rows]
    clips = {}
    if Path(a.clips).exists():
        with open(a.clips, newline="", encoding="utf-8-sig") as f:
            clips = {r["clip_id"]: r for r in csv.DictReader(f)}
    meta = {}
    mp = Path(a.frames_dir) / "clips_meta.json"
    if mp.exists():
        meta = {c["clip_id"]: c for c in json.loads(mp.read_text(encoding="utf-8"))["clips"] if "error" not in c}
    frames = defaultdict(list)
    fi = Path(a.frames_dir) / "frames_index.csv"
    if fi.exists():
        with open(fi, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["kept"] == "1" and abs(float(r["fps_setting"]) - a.fps_setting) < 1e-6:
                    frames[r["clip_id"]].append((int(r["frame_index"]), float(r["timestamp_s"]), r["filename"]))

    seen = set()
    for r in rows:
        vid = r.get("target_vehicle_id") or f"(row with clip {r.get('clip_id', '?')})"
        for c in REQUIRED:
            if not r.get(c):
                add("error", vid, f"missing required field `{c}`")
        if vid in seen:
            add("error", vid, "duplicate target_vehicle_id")
        seen.add(vid)
        if clips and r.get("clip_id") and r["clip_id"] not in clips:
            add("error", vid, f"clip_id `{r['clip_id']}` not in clips.csv")
        clip_info = clips.get(r.get("clip_id"), {})
        for c in ("source", "licence"):
            if clips and not (r.get(c) or clip_info.get(c)):
                add("warning", vid, f"`{c}` empty in both the label row and clips.csv")

        plate, rd = r.get("plate_text_truth", ""), r.get("plate_readability", "")
        if plate:
            if plate != plate.upper() or " " in plate or not re.fullmatch(r"[A-Z0-9?]+", plate):
                add("error", vid, f"plate_text_truth `{plate}` must be uppercase A-Z 0-9 ? with no spaces")
            elif not (STANDARD.match(plate) or BH.match(plate)):
                add("warning", vid, f"plate `{plate}` does not fit the Indian format (flagged, not rejected) - double-check")
        q = [i + 1 for i, ch in enumerate(plate) if ch == "?"]
        up = [int(x) for x in re.split(r"[;, ]+", r.get("unreadable_positions", "")) if x.strip().isdigit()]
        if sorted(up) != q:
            add("error", vid, f"unreadable_positions {up or '(blank)'} does not match the `?` positions {q or '(none)'} in `{plate}`")
        if rd not in ("full", "partial", "none", ""):
            add("error", vid, f"plate_readability `{rd}` must be full / partial / none")
        if rd == "full" and (q or not plate):
            add("error", vid, "plate_readability is `full` but the plate is empty or contains `?`")
        if rd == "partial" and not q:
            add("error", vid, "plate_readability is `partial` but the plate has no `?`")
        if rd == "none" and plate.strip("?"):
            add("error", vid, "plate_readability is `none` but readable characters are given")
        if r.get("colour") and r["colour"] not in COLOURS:
            add("error", vid, f"colour `{r['colour']}` not in {sorted(COLOURS)}")
        if r.get("vehicle_type") and r["vehicle_type"] not in TYPES:
            add("error", vid, f"vehicle_type `{r['vehicle_type']}` not in {sorted(TYPES)}")
        if r.get("in_registry") and r["in_registry"] not in ("yes", "no"):
            add("error", vid, "in_registry must be `yes` or `no`")
        rpf = r.get("registry_plate_full", "")
        if r.get("in_registry") == "yes" and (not plate or q) and not rpf:
            add("warning", vid, "in_registry = yes but the full plate is unknown (has `?` / blank) and registry_plate_full is empty - it cannot be seeded into the registry")
        if rpf and plate and (len(rpf) != len(plate) or any(p != "?" and p != s for p, s in zip(plate, rpf))):
            add("error", vid, f"registry_plate_full `{rpf}` contradicts the readable characters of `{plate}`")
        if (r.get("make") or r.get("model")) and "verified" not in r.get("notes", "").lower():
            add("warning", vid, "make/model given - confirm it is verified (write 'verified: <how>' in notes)")

        try:
            f0, f1 = int(r.get("first_frame", "")), int(r.get("last_frame", ""))
            if f0 > f1:
                add("error", vid, f"first_frame {f0} > last_frame {f1}")
            m = meta.get(r.get("clip_id"))
            if m and (f0 < 0 or f1 >= m["frames_read"]):
                add("error", vid, f"frames {f0}-{f1} outside the clip (0-{m['frames_read'] - 1})")
        except ValueError:
            if r.get("first_frame") or r.get("last_frame"):
                add("error", vid, "first_frame / last_frame must be integers (original frame indices)")
        m = meta.get(r.get("clip_id"))
        vb = parse_box(r.get("vehicle_bbox_first_frame", "")) if r.get("vehicle_bbox_first_frame") else None
        for col in ("vehicle_bbox_first_frame", "plate_bbox_first_frame"):
            if not r.get(col):
                continue
            b = parse_box(r[col])
            if b is None:
                add("error", vid, f"{col} `{r[col]}` must be x1,y1,x2,y2"); continue
            if not (b[0] < b[2] and b[1] < b[3]):
                add("error", vid, f"{col} {b} needs x1<x2 and y1<y2")
            if m and (b[0] < 0 or b[1] < 0 or b[2] > m["width"] or b[3] > m["height"]):
                add("error", vid, f"{col} {b} is outside the {m['width']}x{m['height']} frame")
        pb = parse_box(r.get("plate_bbox_first_frame", "")) if r.get("plate_bbox_first_frame") else None
        if vb and pb and not (pb[0] >= vb[0] - 5 and pb[1] >= vb[1] - 5 and pb[2] <= vb[2] + 5 and pb[3] <= vb[3] + 5):
            add("warning", vid, "plate box is not inside the vehicle box")

    groups = defaultdict(list)
    for r in rows:
        if r.get("cross_camera_group_id"):
            groups[r["cross_camera_group_id"]].append(r)
    for g, members in groups.items():
        if len({m["clip_id"] for m in members}) < 2:
            add("error", g, f"cross_camera_group_id `{g}` appears in only one clip - it must link the same vehicle in >= 2 different clips")
        plates = {m["plate_text_truth"] for m in members if m.get("plate_text_truth") and "?" not in m["plate_text_truth"]}
        if len(plates) > 1:
            add("error", g, f"cross-camera group `{g}` has different full plates {sorted(plates)}")
    n_no = sum(r.get("in_registry") == "no" for r in rows)
    if n_no < 2:
        add("error", "(coverage)", f"only {n_no} vehicle(s) with in_registry = no; the spec requires >= 2")
    valid_groups = [g for g, m in groups.items() if len({x['clip_id'] for x in m}) >= 2]
    if not valid_groups:
        add("error", "(coverage)", "no cross-camera group spanning 2 clips; the spec requires >= 1")
    if not frames:
        add("warning", "(frames)", f"no frames_index.csv in {a.frames_dir} - run extract_test_video_frames.py first; sequences will have no frame list")

    n_err = sum(i["severity"] == "error" for i in issues)
    summary = {"labels": a.labels, "vehicles": len(rows), "clips": len({r.get('clip_id') for r in rows}),
               "errors": n_err, "warnings": len(issues) - n_err, "in_registry_no": n_no,
               "cross_camera_groups": valid_groups,
               "readability": {k: sum(r.get("plate_readability") == k for r in rows) for k in ("full", "partial", "none")},
               "vehicle_types": dict(sorted({t: sum(r.get("vehicle_type") == t for r in rows) for t in TYPES}.items())),
               "issues": issues}
    rep = Path(a.out_report); rep.mkdir(parents=True, exist_ok=True)
    (rep / "test_label_validation.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    md = [f"# Test-label validation\n", f"`{a.labels}`: **{len(rows)} vehicles in {summary['clips']} clips** - "
          f"**{n_err} errors, {summary['warnings']} warnings**. Labels were not modified.\n",
          f"- in_registry = no: {n_no} (need >= 2)\n- cross-camera groups spanning >= 2 clips: {valid_groups or 'none'} (need >= 1)\n"
          f"- readability: {summary['readability']}\n- types: { {k: v for k, v in summary['vehicle_types'].items() if v} }\n",
          "| Severity | Vehicle / group | Issue |\n|---|---|---|"]
    md += [f"| {i['severity']} | {i['target_vehicle_id']} | {i['issue']} |" for i in sorted(issues, key=lambda x: x["severity"])]
    (rep / "test_label_validation.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"{len(rows)} vehicles, {n_err} errors, {summary['warnings']} warnings -> {rep / 'test_label_validation.md'}")

    if n_err and not a.force_derive:
        print("errors found: derived files NOT written (fix the labels, or --force-derive)"); return
    ev = Path(a.out_eval); ev.mkdir(parents=True, exist_ok=True)
    with open(ev / "cross_camera_ground_truth.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["group_id", "clip_id", "target_vehicle_id", "camera_id", "first_frame", "last_frame", "source"])
        for g in valid_groups:
            for m in groups[g]:
                w.writerow([g, m["clip_id"], m["target_vehicle_id"], m.get("camera_id") or clips.get(m["clip_id"], {}).get("camera_id", ""),
                            m.get("first_frame"), m.get("last_frame"), "team label (manually verified)"])
    seqs = []
    for r in rows:
        plate = r.get("plate_text_truth", "")
        try:
            f0, f1 = int(r["first_frame"]), int(r["last_frame"])
        except (KeyError, ValueError):
            f0 = f1 = None
        fl = [{"frame_index": i, "timestamp_s": t, "frame_path": p, "plate_crop_path": None,
               "ocr_text": None, "ocr_char_probs": None}
              for i, t, p in frames.get(r["clip_id"], []) if f0 is not None and f0 <= i <= f1]
        seqs.append({
            "sequence_id": f"seq_{r['target_vehicle_id']}", "clip_id": r["clip_id"], "target_vehicle_id": r["target_vehicle_id"],
            "first_frame": f0, "last_frame": f1, "timestamp_first": r.get("timestamp_first"),
            "fps_setting": a.fps_setting, "frames": fl,
            "ground_truth": {"plate_text": plate or None,
                             "visible_characters": {str(i + 1): ch for i, ch in enumerate(plate) if ch != "?"},
                             "unknown_positions": [i + 1 for i, ch in enumerate(plate) if ch == "?"],
                             "plate_readability": r.get("plate_readability"), "colour": r.get("colour"),
                             "vehicle_type": r.get("vehicle_type"), "in_registry": r.get("in_registry")},
            "aggregated_result": {"plate_text": None, "per_position": None, "method": None,
                                  "note": "filled by the multi-frame fusion in Phase 2; unreadable positions stay '?'"},
        })
    (ev / "multi_frame_sequences.json").write_text(json.dumps({"generated_from": a.labels, "sequences": seqs}, indent=2), encoding="utf-8")
    print(f"wrote {ev / 'cross_camera_ground_truth.csv'} ({sum(len(groups[g]) for g in valid_groups)} rows) and "
          f"{ev / 'multi_frame_sequences.json'} ({len(seqs)} sequences, {sum(len(s['frames']) for s in seqs)} frame refs)")


if __name__ == "__main__":
    main()
