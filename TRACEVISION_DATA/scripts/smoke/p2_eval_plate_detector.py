#!/usr/bin/env python
"""P2 - evaluate the fine-tuned plate detector.

1. mAP on the official Quobotic test split and on leakage_free_test.txt (PROBLEMS A15)
2. Clip check: UVH-26 vehicles -> plate detector on each (upscaled) vehicle crop -> contact sheet of plate crops

Usage: python TRACEVISION_DATA/scripts/smoke/p2_eval_plate_detector.py --weights <best.pt> --out <dir> --clips clip01 clip03 clip10 clip11
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PD = ROOT / "TRACEVISION_DATA/processed/plate_detection"


def map_eval(model, out):
    res = {}
    lf = out / "data_leakage_free.yaml"
    lf.write_text(f"path: {PD.as_posix()}\ntrain: train/images\nval: valid/images\ntest: leakage_free_test.txt\nnc: 1\nnames: ['IndianNumberPlate']\n")
    off = out / "data_official.yaml"
    off.write_text(f"path: {PD.as_posix()}\ntrain: train/images\nval: valid/images\ntest: test/images\nnc: 1\nnames: ['IndianNumberPlate']\n")
    for tag, y in (("official_test", off), ("leakage_free_test", lf)):
        m = model.val(data=str(y), split="test", imgsz=640, device=0, batch=16, plots=False, verbose=False,
                      project=str(out), name=tag, exist_ok=True)
        n_img = len(list((PD / "test/images").glob("*.jpg"))) if tag == "official_test" else \
            sum(1 for l in (PD / "leakage_free_test.txt").read_text().splitlines() if l.strip())
        res[tag] = {"images": n_img,
                    "precision": round(float(m.box.mp), 4), "recall": round(float(m.box.mr), 4),
                    "mAP50": round(float(m.box.map50), 4), "mAP50_95": round(float(m.box.map), 4)}
        print(tag, res[tag], flush=True)
    return res


def clip_check(plate_model, out, clips, every=15):
    import cv2
    import numpy as np
    from ultralytics import YOLO
    veh = YOLO(str(ROOT / "TRACEVISION_DATA/models/weights/UVH-26-MV-YOLOv11-S.pt"))
    stats = {}
    for cid in clips:
        cap = cv2.VideoCapture(str(ROOT / f"TRACEVISION_DATA/raw/test_videos/{cid}.mp4"))
        idx, crops, nveh, nplate, heights = -1, [], 0, 0, []
        while True:
            ok, f = cap.read()
            if not ok:
                break
            idx += 1
            if idx % every:
                continue
            H, W = f.shape[:2]
            for b in veh.predict(f, device=0, imgsz=640, conf=0.3, verbose=False)[0].boxes.xyxy.cpu().numpy().astype(int):
                x1, y1, x2, y2 = b
                if (x2 - x1) * (y2 - y1) < 0.004 * W * H:   # skip tiny far vehicles
                    continue
                nveh += 1
                vc = f[y1:y2, x1:x2]
                s = 640 / max(vc.shape[:2])
                vcu = cv2.resize(vc, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC) if s > 1 else vc
                pr = plate_model.predict(vcu, device=0, imgsz=640, conf=0.25, verbose=False)[0]
                for pb, pc in zip(pr.boxes.xyxy.cpu().numpy(), pr.boxes.conf.cpu().numpy()):
                    nplate += 1
                    px1, py1, px2, py2 = (pb / (s if s > 1 else 1)).astype(int)
                    heights.append(py2 - py1)
                    pcrop = vc[max(0, py1):py2, max(0, px1):px2]
                    if pcrop.size and len(crops) < 40:
                        c = cv2.resize(pcrop, (240, max(20, int(240 * pcrop.shape[0] / max(1, pcrop.shape[1])))))
                        c = cv2.copyMakeBorder(c, 18, 0, 0, 0, cv2.BORDER_CONSTANT, value=(0, 0, 0))
                        cv2.putText(c, f"f{idx} h={py2 - py1}px c={pc:.2f}", (3, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
                        crops.append(c)
        stats[cid] = {"vehicles_checked": nveh, "plates_found": nplate,
                      "plate_height_px_median": float(np.median(heights)) if heights else None}
        if crops:
            hmax = max(c.shape[0] for c in crops)
            crops = [cv2.copyMakeBorder(c, 0, hmax - c.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(255, 255, 255)) for c in crops]
            while len(crops) % 5:
                crops.append(np.full_like(crops[0], 255))
            cv2.imwrite(str(out / f"plates_{cid}.jpg"), np.vstack([np.hstack(crops[i:i + 5]) for i in range(0, len(crops), 5)]))
        print(cid, stats[cid], flush=True)
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--clips", nargs="*", default=[])
    a = ap.parse_args()
    from ultralytics import YOLO
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    pm = YOLO(a.weights)
    res = {"weights": a.weights, "map": map_eval(pm, out)}
    if a.clips:
        res["clips"] = clip_check(pm, out, a.clips)
    (out / "p2_eval.json").write_text(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
