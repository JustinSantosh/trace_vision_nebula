#!/usr/bin/env python
"""P2 - fine-tune YOLOv8n on the processed Quobotic plate set (approved 2026-11-23).

Smoke:  python TRACEVISION_DATA/scripts/smoke/p2_train_plate_detector.py --epochs 1 --fraction 0.1 --name smoke_1ep
Full:   python TRACEVISION_DATA/scripts/smoke/p2_train_plate_detector.py --epochs 60 --name yolov8n_plates
Windows note: must run as a file (not stdin) so DataLoader worker processes can re-import it.
"""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--fraction", type=float, default=1.0)
    ap.add_argument("--name", default="yolov8n_plates")
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--patience", type=int, default=15)
    a = ap.parse_args()
    from ultralytics import YOLO
    base = ROOT / "TRACEVISION_DATA/models/weights/yolov8n.pt"
    m = YOLO(str(base) if base.exists() else "yolov8n.pt")
    m.train(data=str(ROOT / "TRACEVISION_DATA/processed/plate_detection/data.yaml"), epochs=a.epochs, fraction=a.fraction,
            imgsz=640, batch=a.batch, device=0, workers=a.workers, patience=a.patience, seed=0, deterministic=True,
            project=str(ROOT / "TRACEVISION_DATA/models/plate_detector_runs"), name=a.name, exist_ok=True,
            plots=True, verbose=True)


if __name__ == "__main__":
    main()
