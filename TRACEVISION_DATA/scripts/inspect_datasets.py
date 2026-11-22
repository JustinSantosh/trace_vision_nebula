#!/usr/bin/env python
"""Phase 0A - rapid, read-only audit of the inputs present under TRACEVISION_DATA/raw.

Never modifies or copies source data. Writes a JSON report and prints a summary.

Detects per input folder:
  * YOLO detection sets  (images/ + labels/ per split, or data.yaml)
  * OCR crop sets        (gt.txt / labels.txt / *.csv with filename,text; LMDB dirs)
  * Video clips          (mp4/avi/mov/mkv/webm) - FFprobe if installed, else OpenCV
  * Loose images

Usage:
  python scripts/inspect_datasets.py --root TRACEVISION_DATA/raw --out TRACEVISION_DATA/reports/dataset_audit.json
  python scripts/inspect_datasets.py --root <dir> --max-images 200   # sample-limited (fast)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

try:  # hard requirements - fail loudly rather than misreport files as corrupt
    import cv2
    import yaml
    from PIL import Image
except ImportError as _e:
    sys.exit(f"missing dependency: {_e}. pip install pillow opencv-python pyyaml")

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
VID_EXT = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v", ".mpg", ".mpeg"}
SPLIT_ALIASES = {"train": "train", "val": "val", "valid": "val", "validation": "val", "test": "test"}


def image_info(path: Path):
    """Return (w, h, None) or (None, None, error). Uses PIL verify + load."""
    try:
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            im.load()
            return im.size[0], im.size[1], None
    except Exception as e:  # corrupt / truncated / unsupported
        return None, None, f"{type(e).__name__}: {e}"


def video_info(path: Path):
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        try:
            out = subprocess.run(
                [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                 "stream=codec_name,width,height,r_frame_rate,nb_frames:format=duration",
                 "-of", "json", str(path)],
                capture_output=True, text=True, timeout=60)
            d = json.loads(out.stdout or "{}")
            s = (d.get("streams") or [{}])[0]
            num, _, den = (s.get("r_frame_rate") or "0/1").partition("/")
            fps = float(num) / float(den or 1) if float(den or 1) else 0.0
            if not s:
                return {"error": out.stderr.strip() or "no video stream", "probe": "ffprobe"}
            return {"probe": "ffprobe", "codec": s.get("codec_name"), "width": s.get("width"),
                    "height": s.get("height"), "fps": round(fps, 3),
                    "duration_s": float(d.get("format", {}).get("duration") or 0),
                    "nb_frames": s.get("nb_frames")}
        except Exception as e:
            return {"error": f"ffprobe failed: {e}", "probe": "ffprobe"}
    # Fallback: OpenCV (header only, does not decode the whole video)
    try:
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            return {"error": "OpenCV could not open", "probe": "opencv"}
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fourcc = int(cap.get(cv2.CAP_PROP_FOURCC) or 0)
        codec = "".join(chr((fourcc >> 8 * i) & 0xFF) for i in range(4)).strip("\x00") or None
        ok, _ = cap.read()  # decode one frame to confirm readability
        info = {"probe": "opencv", "codec": codec,
                "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "fps": round(fps, 3), "nb_frames": n,
                "duration_s": round(n / fps, 2) if fps else None,
                "first_frame_decodes": bool(ok)}
        cap.release()
        return info
    except Exception as e:
        return {"error": f"opencv failed: {e}", "probe": "opencv"}


def find_split(parts):
    for p in parts:
        if p.lower() in SPLIT_ALIASES:
            return SPLIT_ALIASES[p.lower()]
    return "unsplit"


def inspect_yolo(root: Path, max_images: int | None):
    """Audit a YOLO dataset: counts per split, label sanity, image readability."""
    res = {"type": "yolo_detection", "splits": {}, "class_ids": Counter(), "issues": Counter(),
           "examples": {}}
    yaml_files = list(root.rglob("data.yaml")) + list(root.rglob("*.yaml"))
    if yaml_files:
        try:
            res["yaml"] = {str(yaml_files[0].relative_to(root)): yaml.safe_load(yaml_files[0].read_text())}
        except Exception as e:
            res["yaml_error"] = str(e)
    imgs = [p for p in root.rglob("*") if p.suffix.lower() in IMG_EXT and "images" in [x.lower() for x in p.parts]]
    by_split = {}
    for p in imgs:
        by_split.setdefault(find_split(p.relative_to(root).parts), []).append(p)
    for split, files in sorted(by_split.items()):
        st = {"images": len(files), "checked": 0, "sizes": Counter(), "boxes": 0,
              "empty_labels": 0, "missing_labels": 0}
        for i, img in enumerate(sorted(files)):
            parts = list(img.parts)
            idx = max(j for j, x in enumerate(parts) if x.lower() == "images")
            parts[idx] = "labels"
            lbl = Path(*parts).with_suffix(".txt")
            if not lbl.exists():
                st["missing_labels"] += 1
                res["examples"].setdefault("missing_label", []).append(str(img.relative_to(root)))
            else:
                lines = [l for l in lbl.read_text(errors="replace").splitlines() if l.strip()]
                if not lines:
                    st["empty_labels"] += 1
                for l in lines:
                    f = l.split()
                    if len(f) != 5:
                        res["issues"]["bad_field_count"] += 1
                        continue
                    try:
                        c = int(float(f[0])); xs = [float(v) for v in f[1:]]
                    except ValueError:
                        res["issues"]["non_numeric"] += 1
                        continue
                    res["class_ids"][c] += 1
                    st["boxes"] += 1
                    x, y, w, h = xs
                    if w <= 0 or h <= 0:
                        res["issues"]["non_positive_wh"] += 1
                    if x - w / 2 < -1e-3 or y - h / 2 < -1e-3 or x + w / 2 > 1 + 1e-3 or y + h / 2 > 1 + 1e-3:
                        res["issues"]["box_out_of_bounds"] += 1
            if max_images is None or i < max_images:
                w, h, err = image_info(img)
                st["checked"] += 1
                if err:
                    res["issues"]["corrupt_image"] += 1
                    res["examples"].setdefault("corrupt_image", []).append(str(img.relative_to(root)))
                else:
                    st["sizes"][f"{w}x{h}"] += 1
        st["sizes"] = dict(st["sizes"].most_common(5))
        res["splits"][split] = st
    res["class_ids"] = dict(res["class_ids"]); res["issues"] = dict(res["issues"])
    res["examples"] = {k: v[:10] for k, v in res["examples"].items()}
    return res


def inspect_ocr(root: Path, max_images: int | None):
    res = {"type": "ocr_crops", "gt_files": {}, "lmdb_dirs": [], "issues": Counter(), "examples": {}}
    res["lmdb_dirs"] = [str(p.parent.relative_to(root)) for p in root.rglob("data.mdb")]
    gts = [p for p in root.rglob("*") if p.is_file() and p.name.lower() in {"gt.txt", "labels.txt", "gt.csv", "labels.csv"}]
    for gt in gts:
        rows, missing, checked, sizes, chars = 0, 0, 0, Counter(), Counter()
        for line in gt.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            sep = "\t" if "\t" in line else ("," if "," in line else None)
            if sep is None:
                res["issues"]["unparseable_line"] += 1
                continue
            fn, _, text = line.partition(sep)
            if fn.lower() in {"filename", "file", "image"}:
                continue
            rows += 1
            chars.update(text.strip())
            img = gt.parent / fn.strip()
            if not img.exists():
                missing += 1
                res["examples"].setdefault("missing_image", []).append(str(img.relative_to(root)))
            elif max_images is None or checked < max_images:
                w, h, err = image_info(img); checked += 1
                if err:
                    res["issues"]["corrupt_image"] += 1
                else:
                    sizes[f"{w}x{h}"] += 1
        res["gt_files"][str(gt.relative_to(root))] = {
            "split": find_split(gt.relative_to(root).parts), "rows": rows, "missing_images": missing,
            "checked_images": checked, "top_sizes": dict(sizes.most_common(5)),
            "charset": "".join(sorted(chars))}
    res["issues"] = dict(res["issues"]); res["examples"] = {k: v[:10] for k, v in res["examples"].items()}
    return res


def inspect_videos(root: Path):
    vids = sorted(p for p in root.rglob("*") if p.suffix.lower() in VID_EXT)
    out = {"type": "videos", "count": len(vids), "probe_tool": "ffprobe" if shutil.which("ffprobe") else "opencv",
           "clips": []}
    for v in vids:
        info = video_info(v)
        info.update({"file": str(v.relative_to(root)), "size_mb": round(v.stat().st_size / 1e6, 2)})
        out["clips"].append(info)
    out["total_duration_s"] = round(sum((c.get("duration_s") or 0) for c in out["clips"]), 1)
    out["unreadable"] = [c["file"] for c in out["clips"] if c.get("error") or c.get("first_frame_decodes") is False]
    return out


def inspect_dir(d: Path, max_images: int | None):
    files = [p for p in d.rglob("*") if p.is_file()]
    summary = {"path": str(d), "files": len(files),
               "bytes": sum(p.stat().st_size for p in files),
               "extensions": dict(Counter(p.suffix.lower() for p in files).most_common(10)),
               "sources_note": [str(p.relative_to(d)) for p in files if p.name.lower() in
                                {"readme.md", "license", "license.txt", "license.md", "source.txt", "sources.csv"}],
               "components": []}
    if not files:
        summary["status"] = "EMPTY"
        return summary
    if any("labels" in [x.lower() for x in p.parts] and p.suffix == ".txt" for p in files):
        summary["components"].append(inspect_yolo(d, max_images))
    if any(p.name.lower() in {"gt.txt", "labels.txt", "gt.csv", "labels.csv", "data.mdb"} for p in files):
        summary["components"].append(inspect_ocr(d, max_images))
    if any(p.suffix.lower() in VID_EXT for p in files):
        summary["components"].append(inspect_videos(d))
    if not summary["components"]:
        loose = [p for p in files if p.suffix.lower() in IMG_EXT]
        summary["components"].append({"type": "loose_images", "count": len(loose)})
    summary["status"] = "PRESENT"
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default="TRACEVISION_DATA/raw")
    ap.add_argument("--out", default="TRACEVISION_DATA/reports/dataset_audit.json")
    ap.add_argument("--max-images", type=int, default=None, help="cap images decoded per split (labels always fully checked)")
    a = ap.parse_args()
    root = Path(a.root)
    if not root.is_dir():
        sys.exit(f"root not found: {root}")
    report = {"root": str(root.resolve()), "tools": {"ffprobe": shutil.which("ffprobe"), "python": sys.version.split()[0]},
              "inputs": {}}
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        report["inputs"][d.name] = inspect_dir(d, a.max_images)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(report, indent=2))
    for name, s in report["inputs"].items():
        print(f"{name:20s} {s['status']:8s} files={s['files']:<7d} {s['bytes']/1e6:9.1f} MB  "
              + ", ".join(c["type"] for c in s["components"]))
    print(f"report -> {a.out}")


if __name__ == "__main__":
    main()
