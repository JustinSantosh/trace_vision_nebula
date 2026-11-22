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

## 3b. Phase 0B: plate-detection set validated and prepared (done)

Report: `TRACEVISION_DATA/reports/plate_dataset_validation.md`.
- **Integrity is clean:** 2,069 / 336 / 169 images, every image has a label, 2,084 / 339 / 171 boxes, 0 malformed or out-of-range lines, 1 genuine background image.
- **`processed/plate_detection/` is ready to train:**
  - byte-identical images (SHA-1 checked) under short names, which fixes A18
  - 275 polygons converted to boxes (A19)
  - `name_map.csv`
  - `data.yaml` with relative paths
- **Leakage measured, not fixed (A15):** every source video spans all 3 splits, so 37% of test comes from train videos, and dHash finds at least 18 near-duplicates. The official split is kept, and `leakage_free_{valid,test}.txt` (205 / 106) give an honest second score.

## 3c. Phase 0D–0F tooling (done; waiting for clips)

All 10 scripts named in the spec now exist and have run. The 5 new ones were tested end-to-end on a throwaway 2-clip fixture built from Quobotic video frames (kept in the scratchpad, never committed):
- **`extract_test_video_frames.py`** streams one clip at a time at 1 and 2 FPS. It keeps the original frame index and timestamp and skips near-duplicate samples.
- **`create_test_clip_template.py`** writes `clips.csv`, a **blank** `test_clip_labels_TEMPLATE.csv` (the spec's columns plus an optional `registry_plate_full`) and `LABELING_GUIDE.md`. It never fills in labels.
- **`validate_test_labels.py`** caught all 6 planted errors. It never edits labels. Once there are 0 errors, it writes `multi_frame_sequences.json` (frame references, ground-truth visible characters and unknown positions, and empty OCR/fusion placeholders) and `cross_camera_ground_truth.csv`.
- **`degrade_clips.py`** makes 7 seeded variants (Gaussian/motion blur, 480p/360p, JPEG q10, night, noise) into `difficult_cases.csv`. About 25% of rows are marked for a team readability check.
- **`generate_synthetic_registry.py`** is seeded and reproducible (byte-identical reruns). Records are fictional, with random IDs. Labelled `in_registry = yes` vehicles become `evaluation_seed` rows, and `in_registry = no` vehicles are provably absent. There are decoys for all 9 spec scenarios. **The current version has no labels yet: 334 records and 124 test cases.**

## 4. Phase 0C: Awiros OCR feasibility (done)

Full report: `TRACEVISION_DATA/reports/awiros_feasibility.md`. Script: `TRACEVISION_DATA/scripts/awiros_feasibility_check.py`.

- **Install:** PaddlePaddle 3.3.1 (CPU) and the PaddleOCR clone (`third_party/PaddleOCR`, a submodule) run Awiros on Windows (B2 ✅).
- **Per-character probabilities are available (B1 ✅).** For every plate, `char_probs.jsonl` holds each character with its probability, its CTC timestep and the top-3 alternatives. Multi-frame fusion and the `?` rule can be built directly on this.
- **We found a bug in the official preprocessing (B8 ✅).** Awiros `test.py` pads before normalising, which drops characters. Their own `sample_results.json` contains these errors. With PaddleOCR-style padding, the 7 labelled card samples go from 3/7 to 7/7 correct. **The app must reuse `prep_paddle`.**
- **Full benchmark, 965 unique zenitsu09 plates (`--preprocess paddle`):**
  - **81.5% exact, 4.4% CER**
  - standard-format labels only: **86.0%, 3.1% CER**
  - two-row plates: 60.5%
  - when the mean char prob is at least 0.99, reads are **97.1% exact** (61% of plates)
  - nothing below a mean prob of 0.8 was correct, so **confidence is usable for the `?` rule and the no-match rule**
- **Latency (B7 ✅):** CPU took about 3.8 s per crop, with the Windows CPU build's backbone as the bottleneck. With `paddlepaddle-gpu` 3.3.1 on the RTX 3050 it is **15 ms median / 53 ms p95**. Accuracy is the same, and the full 965-plate run takes about 20 s instead of 61 min.

## 5. Decisions made so far

1. `raw/` is read-only. All renaming (short hashed names plus a name map) and polygon-to-box conversion happen in `processed/` via `prepare_plate_detection.py`.
2. Look at sample images before adopting any dataset (lesson from b8iqo).
3. zenitsu09 is used **only** for the standalone OCR benchmark and never for end-to-end evaluation, because its crops come from the same images as Quobotic (A16).
4. Headline metrics will come from **our own CCTV test clips**, not from the still-photo datasets (A13).
5. ~~Raw data, crops, weights and real plates stay out of git.~~ **Changed:** datasets, crops and weights are now in the repo so the team can use them (see PROBLEMS E6, which covers the public-repo risk). The registry stays synthetic.
7. Awiros is always run with PaddleOCR-style preprocessing (`prep_paddle`), never with the official `test.py` preprocessing (B8).
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
| 246d631 | completions.md / whatnext.md plan; problem log for Awiros progress |
| 8c10105 | Share datasets and Awiros weights with the team (LFS, submodule); TEAM_TASKS.md |
| 05633d6 | Phase 0C: Awiros feasibility report, full 965-plate benchmark, B7/B8 diagnosis, status docs |
| 2ffccc7 | GPU Paddle build: 15 ms per crop, full benchmark re-run on GPU, B7 resolved |
| dfc44a5 | Phase 0B: plate-dataset validation + processed training copy |
| (this push) | Phase 0D–0F scripts, blank label template, starter synthetic registry and test cases |
