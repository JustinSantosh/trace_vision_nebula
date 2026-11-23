# TRACEVISION AI — Team Tasks

**Updated:** 2026-11-23 · Problem: **AIML-01 Vehicle Identification and Traceability from CCTV Footage**
**Summary PDF to share with the team: [TRACEVISION_Team_Handoff.pdf](TRACEVISION_Team_Handoff.pdf)** · Pipeline design: [PIPELINE.md](PIPELINE.md) · See also: [completions.md](completions.md) (what's done) · [whatnext.md](whatnext.md) (full plan) · [PROBLEMS.md](PROBLEMS.md) (problem IDs like A5, B1)

> Write your name next to a workstream, work on a branch named `ws<N>-<topic>` (e.g. `ws4-scorer`), and open a PR into `main`. Tick boxes as you go.

---

## 0. Setup (everyone, once)

```powershell
git config --global core.longpaths true      # dataset paths reach 280 characters on Windows
git lfs install                              # Awiros weights (143 MB) are stored in Git LFS
git clone --recurse-submodules https://github.com/JustinSantosh/trace_vision_nebula.git
cd trace_vision_nebula
python -m pip install pillow opencv-python pyyaml pyarrow numpy safetensors paddlepaddle
```

Already cloned without these? Run `git lfs pull` and `git submodule update --init`. `git lfs pull` also fetches the test clips and the wrong-side clip `TRACEVISION_DATA/raw/wrongside/ws01.mp4`.

**Pulled new code? Restart the app** (`Ctrl+C`, then `python -m tracevision.api`) and hard-refresh the browser (`Ctrl+F5`). An old server answers the new lookups with "Not Found".

**What's in the repo:**

| Path | Contents |
|---|---|
| `TRACEVISION_DATA/processed/plate_detection/` | **Train from here.** Short names, boxes only, `data.yaml`, `name_map.csv` and leakage-free eval lists. |
| `TRACEVISION_DATA/raw/plate_detection/` | Quobotic v3 YOLO plate dataset, 2069 / 336 / 169 images (CC BY 4.0). **Do not open it in File Explorer and do not rename it.** It is byte-identical to the source zip. |
| `TRACEVISION_DATA/raw/ocr_corpus/zenitsu09/` | OCR source parquet |
| `TRACEVISION_DATA/processed/ocr_evaluation/zenitsu09/` | 1,709 plate crops, `ground_truth.csv` (965 unique plates), and the Awiros smoke-test outputs |
| `TRACEVISION_DATA/models/awiros/` | Awiros ANPR OCR weights (LFS) and `test.py` |
| `third_party/PaddleOCR` | PaddleOCR (submodule), needed by Awiros |
| `TRACEVISION_DATA/scripts/` | All 10 Phase 0 scripts (audit, plate data, OCR, clip frames, labels, degradation, registry) |
| `TRACEVISION_DATA/evaluation/`, `registry/` | Label template and guide, registry test cases, synthetic registry, **synthetic owner records and e-challans** (enforcement add-on) |
| `TRACEVISION_DATA/cameras/camera_rules.json` | Wrong-side rules: fixed-camera zones and moving-camera / upload road layouts ([ENFORCEMENT.md](ENFORCEMENT.md) §4) |
| `TRACEVISION_DATA/raw/wrongside/` | `ws01.mp4`, the wrong-side test clip (LFS), with its source note |

Don't commit test clips, frames or `.pt` weights (`.gitignore` blocks them). Share clips via the team drive instead.

---

## Current facts that shape the work (2026-11-23)

- **Built and tested** (health check passed, `TRACEVISION_DATA/reports/health_check_2026-11-23.md`):
  - P1: vehicle detection and tracking (UVH-26) on the GPU
  - P2: plate detector, **leakage-free mAP50 0.995**
  - P3: **multi-frame fusion + registry matching** in `tracevision/`, 26 tests (`python -m pytest tests`)
- **Awiros OCR:** 81.5% exact / 4.4% CER on 965 plates. **Run it on the GPU** (15 ms per crop). It must run in a **separate process** from torch/YOLO on Windows (C5).
- **19 test clips and 67 owner-verified labelled vehicles** are in (clip12–19: cross-camera parking pairs). Most plates in the WhatsApp-quality and CCTV-style clips are under 16 px, so they're reported unreadable (C7).
- **Windows:** anything that trains or validates with ultralytics must run from a `.py` file, not from stdin (it hangs otherwise).
- **All phases P1–P6 done (2026-11-23):** pipeline, app (`python -m tracevision.api`), reports for all clips, evaluation. **What's left: [NEEDS.md](NEEDS.md).**
- **Since then:** video viewer with live playback and a cross-camera panel; phantom-box fix (C11); CLIP colour (C8, 59% exact on 19 clips); two-detector ensemble UVH-26 + COCO YOLOv8n (C13); declared cross-angled pairs linked jointly (M16). Install `open_clip_torch` too (README install line); the CLIP weights (~580 MB) download on first run.
- **Current results (19 clips, 67 vehicles):** 14/15 registered matched, 0/46 false identifications, 0/252 wrong plate characters, 61/67 found; cross-camera 5/5 checkable groups, 0 wrong.
- **Enforcement add-on (merged, PR #3):** synthetic vehicle records and e-challans for confident matches, simulated challans, wrong-side driving with a review queue, audit log. **Read [ENFORCEMENT.md](ENFORCEMENT.md)** before demoing or changing it.

---

## WS1: Test clips and ground truth · Owner: ________

- [x] 11 Indian clips (clip01–11), frames and contact sheets (`processed/test_video_frames/clipNN/contact_sheet_fps2.jpg`). clip01–09 via Git LFS; clip10–11 from the Pexels links in `clips.csv`.
- [x] 51 vehicles labelled and **owner-verified** → `evaluation/test_clip_labels.csv` (validator: 0 field errors)
- [ ] **Cross-camera pair:** film one car from 2 different spots (original files), label it in both clips with the same `cross_camera_group_id`, `in_registry = yes` and `registry_plate_full` (A6)
- [ ] Optional: more `in_registry = yes` vehicles with readable plates (only 9 of 51 now)
- [ ] After the pair: run `validate_test_labels.py` (writes `multi_frame_sequences.json` and `cross_camera_ground_truth.csv`), `degrade_clips.py`, then `generate_synthetic_registry.py`

**Done when:** the validator shows 0 errors, including the cross-camera group.

## WS2 — Plate detector data and training (Phase 0B → 1) · Owner: ________

- [x] Validation + processed copy done (Phase 0B). See `reports/plate_dataset_validation.md`.
- [x] YOLOv8n fine-tuned (P2): `models/weights/plate_yolov8n_quobotic.pt` (LFS). Leakage-free test mAP50 0.995. See `reports/p2_plate_detector.md`.
- [x] Reported on both the official and the leakage-free test (A15)
- [ ] Never crop train plates for OCR: train contains mirrored copies (A21).

**Done when:** `best.pt` is on the team drive and the mAP is recorded in `reports/`.

## WS3 — Vehicle type, colour, tracking, OCR · Owner: ________

- [x] Awiros benchmark and GPU build (15 ms per crop). Install: `pip install paddlepaddle-gpu==3.3.1 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/`
- [x] UVH-26 loaded, `models/class_mapping.json` built from the real 14 classes (B3, B4, M6)
- [x] ByteTrack smoke-tested on clip01/02 (`reports/p1_vision_stack.md`)
- [x] **Colour** estimator (`tracevision/colour.py`): now CLIP zero-shot: 59% exact on 19 clips (was 27% with the hue rule). Still the best next task (C8).
- [x] **Track re-linking** (position + plate + same-object rule) and the edge-box rule (C6, M10, M11)

**Done:** `tracevision/pipeline.py` (P4).

## WS4 — Matching algorithm (judged deliverable) · Owner: ________

- [x] Synthetic registry (334 records) + 124 expected-outcome cases. The answer key was fixed: 20 cases relabelled ambiguous (A24).
- [x] **Multi-frame fusion** `tracevision/fuse.py`: aligned, confidence-weighted vote per position, `?` instead of guesses
- [x] **Matcher** `tracevision/match.py`: wildcard and look-alike aware **match score** (not a probability) + reasons + match / ambiguous / no-match
- [x] 26 unit tests; thresholds calibrated with a split by anchor (`python -m tracevision.calibrate`, held-out 62/62). See `reports/p3_fusion_and_matching.md`.
- [x] Checked on real clips (P6, 19 clips): 14/15 registered matched, 0/46 false matches

**Done.**

## WS5 — App and report · Owner: ________

- [x] FastAPI app `tracevision/api.py`: `POST /jobs` (upload) → progress → report / PDF / JSON. Run `python -m tracevision.api` → http://127.0.0.1:8000
- [x] Investigator view = the clip report: frames used, characters per frame with confidence, fused plate with `?`, top 5 with match scores and reasons
- [x] HTML + PDF report (`tracevision/report.py`, reportlab; no extra installs)
- [x] Batch: one report per test clip in `TRACEVISION_DATA/evaluation/reports/`

**Done** (P5, `reports/p5_app_and_reports.md`).

---

## WS6 — Enforcement add-on · Owner: ________

Guide: **[ENFORCEMENT.md](ENFORCEMENT.md)** (how to run, demo, add clips, troubleshoot).
- [x] Synthetic owner records + e-challans (`generate_vehicle_intel.py`), lookup only for confident matches (E17)
- [x] Issue / cancel simulated challans; audit log; review queue
- [x] Wrong-side driving, fixed cameras (zones + camera-pan removal, E18) and moving cameras (front-then-rear head-on pass, E19)
- [x] Cross-camera view shows the record for a confident pooled match
- [ ] **Film 2–3 wrong-side clips** (ideally a fixed camera, plus a moving camera on a road you *know* is two-way) and add rules for them in `camera_rules.json` (ENFORCEMENT.md §4). This turns "one example" into a measured result.
- [ ] Before a demo on a new machine: upload `ws01.mp4` once on the GPU machine **under that name** (uploaded results are not in git)
- [ ] Optional: two-wheeler support for the moving-camera check; other violations on the same tracks (triple riding, illegal parking) — whatnext.md §4

---

## Integration milestones

| # | Milestone | Needs |
|---|---|---|
| M1 ✅ | Clip → tracks → per-frame plate text | P4 |
| M2 ✅ | Plus fusion and ranking → top 5 / no-match | P4 |
| M3 ✅ | Plus UI and report for every clip | P5 |
| M4 🟡 | Metrics on our clips ✅ (P6), README ✅, **demo video: owner (NEEDS.md)** | P6 |

Data licences and privacy: Quobotic is CC BY 4.0 (credit it in the README). zenitsu09 states no licence (internal evaluation only). Awiros is Apache-2.0. The Ultralytics models are AGPL-3.0 (B6).
