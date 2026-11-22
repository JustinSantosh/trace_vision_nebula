# TRACEVISION AI

Hack-A-Sol 5.0, Track 02, AIML-01: vehicle identification and traceability from CCTV footage.

## Status: Phase 0 is done except the clip-dependent parts. 0A audit, 0B plate data (ready to train) and 0C Awiros OCR (81.5% exact, 15 ms/crop on GPU) are done; the 0D–0F tools and a starter synthetic registry are ready. **Waiting on the team's test clips and hand labels.** **Team: start with [TEAM_TASKS.md](TEAM_TASKS.md).** Also see [completions.md](completions.md) · [whatnext.md](whatnext.md) · [PROBLEMS.md](PROBLEMS.md) · [DECISIONS.md](DECISIONS.md) · **[PIPELINE.md](PIPELINE.md)** (Phase 1–3 design, awaiting approval).

Clone with `git config --global core.longpaths true`, `git lfs install` and then `git clone --recurse-submodules …`.

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

**Committed (team decision, 2026-11-22):**
- Quobotic v3 (`raw/plate_detection/`, CC BY 4.0, credit: [Quobotic on Roboflow Universe](https://universe.roboflow.com/quobotic/indian-number-plate/dataset/3))
- the zenitsu09 parquet, OCR crops and `ground_truth.csv` (no stated licence; internal evaluation only)
- the Awiros weights (Apache-2.0, Git LFS)

**Not committed:** test clips, video frames, other model weights and the rejected b8iqo set. See PROBLEMS.md E6.

### Run the audit
```
python TRACEVISION_DATA/scripts/inspect_datasets.py --root TRACEVISION_DATA/raw --out TRACEVISION_DATA/reports/dataset_audit.json
```
Requires Pillow, opencv-python and PyYAML.

Licence note: the Ultralytics-based models (YOLOv8, UVH-26 YOLOv11) are AGPL-3.0.
