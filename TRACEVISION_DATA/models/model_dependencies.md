# Model Dependencies

**Status 2026-11-23:** Awiros (in the repo, LFS) and UVH-26 YOLOv11-S (in `models/weights/`, git-ignored; sha256 `12dbeb8f6fa207d1…`) are downloaded and running on GPU. YOLOv8n will be fetched by ultralytics in P2. torch and Paddle must run in **separate processes** (PROBLEMS C5).

| Model | Repo / file | Size | Install deps | Notes |
|---|---|---|---|---|
| UVH-26 YOLOv11-S (recommended for CPU) | `iisc-aim/UVH-26` → `weights/YOLOv11-S/UVH-26-MV-YOLOv11-S.pt` | 57.1 MB | `ultralytics` (needs torch) | Other variants: YOLOv11-X, RT-DETRv2-S/X, DAMO-YOLO-T/L. Input resolution is not stated on the card. |
| Awiros ANPR OCR | `Awiros/anpr-ocr` → `model.safetensors`, `test.py`, `en_dict.txt` | 149.4 MB | PaddleOCR repo (git clone), `paddlepaddle` (CPU), `safetensors`, `opencv-python`, `pyyaml`, `pillow` | PP-OCRv5 (PPHGNetV2_B4) with a multi-head CTC+NRTR decoder. 37.3M parameters, input 3×48×320, 63-character charset. The card does not document per-character probabilities, so this must be checked in the code. |
| YOLOv8n base | Ultralytics `yolov8n.pt` | ~6 MB | `ultralytics` | Used only for fine-tuning the plate detector on Colab in Phase 1. |

Keep the downloaded weights in `TRACEVISION_DATA/models/weights/`. Do not put them in any `raw/` or `processed/` dataset folder.
