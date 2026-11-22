# TRACEVISION AI

Hack-A-Sol 5.0, Track 02, AIML-01: vehicle identification and traceability from CCTV footage.

## Status: Phase 0A is done; D1/D2 have been replaced (Quobotic v3, zenitsu09) and the OCR eval set is built. Next: 0B validation. See the progress table in [PROBLEMS.md](PROBLEMS.md).

- `TRACEVISION_DATA/reports/`: audit, coverage matrix and licence report
- `TRACEVISION_DATA/models/model_dependencies.md`: pretrained models used (UVH-26, Awiros ANPR OCR, YOLOv8n)
- `TRACEVISION_DATA/scripts/`: Phase 0 scripts

## Current blocker: datasets to download (team action)

The original D1/D2 Hugging Face repos are empty; see [PROBLEMS.md](PROBLEMS.md) A1/A2. Replacements are chosen in [d1_d2_alternatives.md](TRACEVISION_DATA/reports/d1_d2_alternatives.md). Phase 0B/0C are waiting on these three downloads:

| # | Dataset | Put it in | How |
|---|---|---|---|
| 1 ✅ | [Roboflow Quobotic v3](https://universe.roboflow.com/quobotic/indian-number-plate/dataset/3) (b8iqo was rejected as synthetic; see PROBLEMS.md A14) | `TRACEVISION_DATA/raw/plate_detection/` | Download Dataset → **YOLOv8**. **Don't unzip with File Explorer** (paths over 260 characters fail); it was extracted with Python and verified against the zip CRC. Done. |
| 2 | [witvix/indian-truck-license-plates-sample](https://huggingface.co/datasets/witvix/indian-truck-license-plates-sample) | `TRACEVISION_DATA/raw/ocr_corpus/witvix/` | Fill in the HF access form, then download the repo. |
| 3 ✅ | [zenitsu09/indian-number-plate](https://huggingface.co/datasets/zenitsu09/indian-number-plate) | `TRACEVISION_DATA/raw/ocr_corpus/zenitsu09/` | Download `data/train-*.parquet` (6 MB) from the dataset's Files tab. |

After the downloads, the next steps are: re-run the audit → `validate_plate_dataset.py` (including the near-duplicate check across Quobotic's splits) → Colab `data.yaml` + OCR `ground_truth.csv` → Awiros feasibility check.

Raw data, video frames, plate crops and model weights are deliberately **not** committed. This is because of their size, their licences and the real number plates they contain.

### Run the audit
```
python TRACEVISION_DATA/scripts/inspect_datasets.py --root TRACEVISION_DATA/raw --out TRACEVISION_DATA/reports/dataset_audit.json
```
Requires Pillow, opencv-python and PyYAML.

Licence note: the Ultralytics-based models (YOLOv8, UVH-26 YOLOv11) are AGPL-3.0.
