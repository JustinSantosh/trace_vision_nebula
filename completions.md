# TRACEVISION AI — What Is Done

Hack-A-Sol 5.0 · Track 02 AIML · **AIML-01 Vehicle Identification and Traceability from CCTV Footage**
**Last updated:** 2026-11-23

Open problems are in [PROBLEMS.md](PROBLEMS.md). Next steps are in [whatnext.md](whatnext.md). Decisions are in [DECISIONS.md](DECISIONS.md).

**Phase 0 status:**

| Step | State |
|---|---|
| 0A Audit | ✅ |
| 0B Plate-detection data | ✅ |
| 0C Awiros OCR check | ✅ |
| 0D Clips + labels | 🟡 Tools ready; waiting for clips |
| 0E Variants + sequences | 🟡 Tools ready; waiting for labels |
| 0F Registry | 🟡 Starter ready; re-seed after labels |
| Final Phase 0 report | ⏳ After labels |

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

## 4b. Phase 1, step P1: vision stack (done 2026-11-23, approved)

Full report: `TRACEVISION_DATA/reports/p1_vision_stack.md`.
- torch 2.14.1+cu126, ultralytics 8.4.216 and lap are installed, and CUDA runs on the RTX 3050.
- **UVH-26 YOLOv11-S** is downloaded and its checksum verified. Its **real classes are 14** (the card omits `Others`), so B3 is resolved. `models/class_mapping.json` maps them to our vocabulary (DECISIONS M6).
- **torch and Paddle can't share a process on Windows** because their cuDNN DLLs differ. The OCR worker-process design is tested (about 15 ms per crop on the same GPU) (C5, M7).
- **Smoke test** on clip02 and clip01: dense detection and tracking work (96 and 52 tracks). Two issues are found and planned for: track fragmentation and wrong types on edge-cut vehicles (C6).
- Test clips clip01–09 are on GitHub (LFS) with contact sheets. The labelling guide is step by step, and PIPELINE.md is written.

## 4c. Phase 1, step P2: plate detector (done 2026-11-23, approved)

Full report: `TRACEVISION_DATA/reports/p2_plate_detector.md`.
- YOLOv8n fine-tuned on Quobotic: 60 epochs in 24 min on the RTX 3050.
- **Leakage-free test: P 0.991, R 0.980, mAP50 0.995, mAP50-95 0.754** (official test: 0.995 / 0.788). Leakage barely affects detection.
- On our clips: close plates are found and cropped cleanly (day, night, two-wheelers). Far plates are found but only 5–14 px tall, so they're unreadable (C7). False detections are all low-confidence, so the threshold is 0.5 and plates under 16 px aren't OCR'd (M8).
- Weights `models/weights/plate_yolov8n_quobotic.pt` are shared via Git LFS.

## 4d. Phase 2, step P3: the judged algorithms (done 2026-11-23, approved)

Full report: `TRACEVISION_DATA/reports/p3_fusion_and_matching.md`. Code in `tracevision/`, tests in `tests/`.
- **Multi-frame fusion** (`fuse.py`): aligns reads (a dropped character doesn't shift the rest), takes quality × probability votes per position, and writes `?` below the share or confidence bar. Never guesses. Handles BH plates and warns on unknown state codes.
- **Registry matching** (`match.py`): wildcard- and look-alike-aware match score, reasons for every candidate, and match / ambiguous / no-confident-match decisions.
- **26 unit tests pass.** Thresholds calibrated with a split by anchor: **held-out 62/62**, top-1 32/32. The cases are synthetic designed traps, not real-world accuracy.
- Found and fixed **20 wrong expected outcomes** in the generated answer key (A24).

## 4e. Health check (2026-11-23)

Full report: `TRACEVISION_DATA/reports/health_check_2026-11-23.md`. **All 10 Phase 0 scripts, all 3 models, the 26 tests, the data and the docs check out.** Fixed along the way: 6 stale contact sheets (after the clip trim) and a reproducibility bug in the calibration report. **Owner-verified labels are in** (`test_clip_labels.csv`, 51 vehicles, 0 field errors); only the cross-camera pair is missing (A6).

## 5. Decisions

All decisions, with the reason for each and their status, are in **[DECISIONS.md](DECISIONS.md)** (D1–D10 data, M1–M6 models, E1–E9 evaluation, P1–P3 process).

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
| 097c073 | Phase 0D–0F scripts, blank label template, starter synthetic registry and test cases |
| 4b6bd57 | DECISIONS.md, status docs refreshed |
| 74994ff | P1: vision stack, UVH-26 class mapping, two-process OCR, smoke test |
| 1fcaf35 | P2: plate detector trained and evaluated; weights via LFS |
| 2a29749 | P3: fusion + matching + tests + calibration; answer-key fix |
| 4cbbc07 | Health check; contact sheets regenerated; calibration report reproducible |
| (this push) | Project docs synced to the current state (README, whatnext, TEAM_TASKS) |
