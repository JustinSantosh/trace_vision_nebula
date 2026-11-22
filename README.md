# TRACEVISION AI

Hack-A-Sol 5.0, Track 02, AIML-01: vehicle identification and traceability from CCTV footage.

## Status: Phase 0A (dataset audit) is complete. Several items are blocked; see [PROBLEMS.md](PROBLEMS.md).

- `TRACEVISION_DATA/reports/`: audit, coverage matrix and licence report
- `TRACEVISION_DATA/models/model_dependencies.md`: pretrained models used (UVH-26, Awiros ANPR OCR, YOLOv8n)
- `TRACEVISION_DATA/scripts/`: Phase 0 scripts

## Current blocker: datasets to download (team action)

The original D1/D2 Hugging Face repos are empty; see [PROBLEMS.md](PROBLEMS.md) A1/A2. Replacements are chosen in [d1_d2_alternatives.md](TRACEVISION_DATA/reports/d1_d2_alternatives.md). Phase 0B/0C are waiting on these three downloads:

| # | Dataset | Put it in | How |
|---|---|---|---|
| 1 | [Roboflow b8iqo](https://universe.roboflow.com/indian-number-plate-dataset/indian-number-plate-recognition-b8iqo) (optional extras: [Quobotic](https://universe.roboflow.com/quobotic/indian-number-plate), [Payals](https://universe.roboflow.com/payals-workspace-gz1ub/indian-number-plate-detection-g7voe)) | `TRACEVISION_DATA/raw/plate_detection/b8iqo/` (extras go in `quobotic/` and `payals/` alongside it) | Free Roboflow account → export as **YOLOv8** → unzip as-is. Don't rename anything or re-split. |
| 2 | [witvix/indian-truck-license-plates-sample](https://huggingface.co/datasets/witvix/indian-truck-license-plates-sample) | `TRACEVISION_DATA/raw/ocr_corpus/witvix/` | Fill in the HF access form, then download the repo. |
| 3 | [zenitsu09/indian-number-plate](https://huggingface.co/datasets/zenitsu09/indian-number-plate) | `TRACEVISION_DATA/raw/ocr_corpus/zenitsu09/` | Download `data/train-*.parquet` (6 MB) from the dataset's Files tab. |

After the downloads, the next steps are: re-run the audit → `validate_plate_dataset.py` (including duplicate checks between b8iqo and Quobotic, and between Payals and zenitsu09) → Colab `data.yaml` + OCR `ground_truth.csv` → Awiros feasibility check.

Raw data, video frames, plate crops and model weights are deliberately **not** committed. This is because of their size, their licences and the real number plates they contain.

### Run the audit
```
python TRACEVISION_DATA/scripts/inspect_datasets.py --root TRACEVISION_DATA/raw --out TRACEVISION_DATA/reports/dataset_audit.json
```
Requires Pillow, opencv-python and PyYAML.

Licence note: the Ultralytics-based models (YOLOv8, UVH-26 YOLOv11) are AGPL-3.0.
