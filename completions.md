# TRACEVISION AI — What Is Done

Hack-A-Sol 5.0 · Track 02 AIML · **AIML-01 Vehicle Identification and Traceability from CCTV Footage**
**Last updated:** 2026-11-22

Open problems are in [PROBLEMS.md](PROBLEMS.md). Next steps are in [whatnext.md](whatnext.md).

---

## 1. Problem statement understood (AIML-01)

What the judges will check, from the official PDF:

| Must-have | What it means for us |
|---|---|
| Multi-frame plate recovery | Fuse characters across frames. **Unreadable characters are written as `?` and never guessed.** |
| Attribute extraction | Vehicle colour and body type (car, SUV, two-wheeler, auto-rickshaw, truck, …) |
| Registry matching and ranking | Top 5 candidates from a sample registry, each with a confidence score and reasons |
| No-match handling | Output "no confident match" when nothing fits, rather than forcing a result |
| Investigator UI and report | Upload a clip and review the results. A PDF/HTML report shows the frames used, the characters read per frame with confidence, and the reasoning for each match. |

**Bonus:** make/model recognition and cross-camera tracking.
**Deliverables:** the working app, **our own** matching and ranking algorithm, and an analysis report for **every** test clip.

## 2. Phase 0A — dataset audit (done)

- `TRACEVISION_DATA/scripts/inspect_datasets.py`: audits images, labels and videos
- `TRACEVISION_DATA/reports/dataset_audit.{json,md}`, `dataset_coverage_matrix.md`, `license_report.md`
- `TRACEVISION_DATA/models/model_dependencies.md`: chosen models are UVH-26 (vehicle type), Awiros ANPR OCR and YOLOv8n (plate detector)
- Problem log started ([PROBLEMS.md](PROBLEMS.md))

## 3. Replacing the empty datasets (done)

The original D1/D2 Hugging Face repos contained no data (PROBLEMS A1–A3). Replacement candidates are in `TRACEVISION_DATA/reports/d1_d2_alternatives.md`.

| Role | Dataset | State |
|---|---|---|
| Plate detection (D1) | Roboflow **Quobotic v3** (CC BY 4.0) in `raw/plate_detection/` | ✅ 2069 / 336 / 169 images+labels. All 5,151 zip entries checked against the zip CRC. Rechecked 2026-11-22: 0 missing, 0 size mismatches. |
| Rejected D1 | Roboflow b8iqo | ❌ Synthetic (whole-frame rendered plates), moved to `raw/_rejected/` (A14) |
| OCR benchmark (D2) | **zenitsu09** parquet in `raw/ocr_corpus/zenitsu09/` | ✅ `build_ocr_eval_set.py` built 1,709 crops covering 965 unique plates, plus `processed/ocr_evaluation/zenitsu09/ground_truth.csv` (local only). Bad labels are flagged as `nonstandard_review` (A20). |

Notes:
- **Quobotic must not be unzipped with File Explorer.** Its paths reach 280 characters and Explorer reports "Path too long" (A18). The copy in `raw/` was extracted with Python and is complete. One empty label (`valid/labels/BR9_jpg…txt`) is also empty in the zip, so it is a genuine background image.
- `raw/` is kept byte-identical to the source zips. Renaming and cleaning happen only in `processed/`.

## 4. Phase 0C — Awiros OCR feasibility (part done)

- Awiros weights (`model.safetensors`, 143 MB), `test.py` and the 9 card sample images are in `TRACEVISION_DATA/models/awiros/`. The PaddleOCR repo is cloned into `third_party/PaddleOCR`.
- PaddlePaddle is installed and **inference runs on CPU on Windows** (resolves the main install risk in B2).
- **Reproduction check:** our run (`samples_ours.json`) gives **9/9 the same plate text** as the published `sample_results.json`. Confidences agree to within about 0.03.
- Weights and the PaddleOCR clone are git-ignored (size and licence).

**Not done yet:** per-character probabilities (B1), the full benchmark on the zenitsu09 965-plate set, and CPU latency.

## 5. Decisions made so far

1. `raw/` is read-only. All renaming (short hashed names plus a name map) and polygon-to-box conversion happen in `processed/` via `prepare_plate_detection.py`.
2. Look at sample images before adopting any dataset (lesson from b8iqo).
3. zenitsu09 is used **only** for the standalone OCR benchmark and never for end-to-end evaluation, because its crops come from the same images as Quobotic (A16).
4. Headline metrics will come from **our own CCTV test clips**, not from the still-photo datasets (A13).
5. Raw data, crops, weights and real plates stay out of git. The registry is synthetic.
6. The AGPL-3.0 licence of the Ultralytics models is accepted for the hackathon and disclosed in the README (B6).

## 6. Commit history

| Commit | What |
|---|---|
| e56a43c | Phase 0A: audit, coverage matrix, licence report, problem log |
| e7709f2 | D1/D2 replacement candidates |
| 175d1ad | README dataset download hand-off |
| 4666f19 | Reject synthetic b8iqo; switch D1 to Quobotic v3 |
| 0b0acd8 | README cleanup |
| ea37873 | zenitsu09 OCR eval set builder; Quobotic verified |
| 845d4ed / 92aa219 | Problem log and README progress updates |
