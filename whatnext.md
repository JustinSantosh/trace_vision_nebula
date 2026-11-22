# TRACEVISION AI — What Next

**Last updated:** 2026-11-22 · What is already done is in [completions.md](completions.md). Problem IDs (A5, B1, …) refer to [PROBLEMS.md](PROBLEMS.md). Decisions are in [DECISIONS.md](DECISIONS.md).

**Where we are:** Phase 0 is done except the parts that need clips. The only blocker is **the team's test clips and hand labels**. Every script that processes them is built and tested.

## 0. Team actions — unblock these first

| Priority | Action | Unblocks |
|---|---|---|
| 🔴 1 | **Film 6–8 clips of 8–15 s** (5 s minimum) into `TRACEVISION_DATA/raw/test_videos/` as `clip01.mp4`, `clip02.mp4`, … Film from a high, distant, CCTV-like angle (balcony or stairs, 5–15 m from the road), in landscape at 1080p, held steady. Cover: a clear daylight plate, a blurred or moving plate, a partly blocked plate, a motorcycle or scooter, an auto-rickshaw, a truck or bus, several vehicles in one frame, and dusk or night if possible. Then follow TEAM_TASKS WS1 steps 1–6 (DECISIONS E2, A5). **Status 2026-11-23:** 6 clips in (2 fixed CCTV-style, 4 moving). Moving and dashcam clips are fine, but **most new clips should be fixed and raised** to stay true to the CCTV problem statement (DECISIONS E10). | Every clip-based phase, the demo and the per-clip reports |
| 🔴 2 | **Include at least 2 vehicles that will NOT be in the registry**, to test no-match handling. | No-match must-have |
| 🟠 3 | **Cross-camera pair:** film the same vehicle from two phone positions (A6). | Bonus: cross-camera tracking |
| 🟠 3b | **Hand-label the clips** using `evaluation/LABELING_GUIDE.md`: about 5 minutes per clip. Only humans write labels (DECISIONS E3). | 0D–0F, all clip metrics |
| 🟠 3c | **Decide on the repo's visibility.** It is public and holds real plates (E6 / DECISIONS D10). | Privacy |
| 🟡 4 | Check the two `.mp4` files in `~/Downloads` (`DS.mp4` and `original-5adf….mp4`). If they are test clips, move them into `raw/test_videos/` (A11). | A5 |
| ⚪ 5 | Optional: fill in the witvix Hugging Face access form for a harder OCR test (A2). | Out-of-domain OCR score |

## 1. Phase 0B: plate-detection data prep (✅ done)

- [x] `scripts/validate_plate_dataset.py`: integrity, boxes against polygons, plate sizes, leakage across splits (built-in dHash, so `imagehash` was not needed)
- [x] `scripts/prepare_plate_detection.py` → `processed/plate_detection/`: short names, `name_map.csv`, boxes only, `data.yaml`, leakage-free eval lists
- [x] `reports/plate_dataset_validation.md`
- [ ] First step of Phase 1: open `data.yaml` with Ultralytics (not installed yet)

## 2. Phase 0C: Awiros OCR check (✅ done)

- [x] Install works on Windows CPU; card samples reproduced
- [x] **B1:** per-character probabilities plus top-3 alternatives come from the CTC head
- [x] **B8:** official preprocessing bug found; we use `prep_paddle`
- [x] Full 965-plate benchmark: 81.5% exact / 4.4% CER (86.0% / 3.1% on standard labels), with splits by layout, height and confidence
- [x] Latency measured: about 3.8 s per crop on CPU (backbone-bound)
- [x] Report: `reports/awiros_feasibility.md`
- [x] **B7:** `paddlepaddle-gpu` installed. 15 ms per crop on the RTX 3050, same accuracy. **Always run with `--device gpu`.**

## 2b. Phase 0D–0F tooling (✅ built and tested on a fixture; waiting for clips)

- [x] `extract_test_video_frames.py`, `create_test_clip_template.py`, `validate_test_labels.py`, `degrade_clips.py`, `generate_synthetic_registry.py`, so all 10 spec scripts now exist
- [x] Blank template plus `LABELING_GUIDE.md` in `evaluation/`
- [x] Starter synthetic registry (334 records) and 124 registry test cases, so the matcher can be built now
- [ ] **Team:** clips → labels → validate → degrade → regenerate the registry (TEAM_TASKS WS1 steps 1–6)
- [ ] Final Phase 0 report, after the clips are labelled

## 3. Phase 1 — models

- [ ] Fine-tune the **YOLOv8n plate detector** on `processed/plate_detection` (Colab, or the local RTX 3050)
- [ ] Load **UVH-26** and build `class_mapping.json` from the model's real class names (B3). Map Two-wheeler → `motorcycle/scooter` and Three-wheeler → `auto_rickshaw` (B4).
- [ ] **Colour classifier:** HSV / k-means on the vehicle body crop (excluding glass and road), mapped to about 10 named colours, with a confidence score
- [ ] Vehicle tracking across frames (ByteTrack via ultralytics)

## 4. Phase 2 — our own algorithm (judged deliverable)

- [ ] **Multi-frame plate fusion:** pick the sharpest frames → OCR each one → align to the Indian plate pattern (`SS NN XX NNNN`, plus BH series) → confidence-weighted vote per position → below the threshold, output `?`. **Never fill in a guess.**
- [ ] **Synthetic registry** in `TRACEVISION_DATA/registry/` (CSV with ~500–2,000 rows): plate, colour, type, make/model, synthetic owner. Include the vehicles from our clips that should match, plus near-miss decoys (same partial plate, different colour or type).
- [ ] **Scorer:** a wildcard-aware plate similarity with partial credit for look-alike characters (0/O/D, 8/B, 1/I, 5/S, 2/Z), weighted with colour and type scores into one confidence. Each candidate gets a **human-readable reasons list**.
- [ ] **No-match threshold:** calibrate it on the clips. If the top score is below the threshold, output "no confident match".
- [ ] Unit tests for the scorer (wildcards, look-alikes, ties, empty plate)

## 5. Phase 3 — app and report

- [ ] Backend (FastAPI): upload clip → pipeline → JSON result
- [ ] Investigator UI: upload, progress, the frames used, the per-frame characters, and a top-5 table with reasons
- [ ] **Report** (HTML → PDF): the frames used, the characters per frame with confidence, the fused plate, the top 5 with confidence and reasons, or "no confident match"
- [ ] Generate a report for **every** test clip into `evaluation/reports/`

## 6. Phase 4 — evaluation and submission

- [ ] Hand-label the clips (plate text, colour, type; boxes on the first frame only, E2)
- [ ] Metrics on our clips (the headline numbers, A13): plate character accuracy, `?` rate vs wrong-character rate, colour and type accuracy, top-1 and top-5 hit rate, and no-match precision
- [ ] README: architecture diagram, how to run, models and licences (B6)
- [ ] Demo video and slides
- [ ] Stretch goals: cross-camera re-identification (A6), make/model recognition (only if labels can be verified)

## Environment installs still needed (C1, C2)

`ultralytics`, `torch` (CUDA build for the RTX 3050), `imagehash`, `fastapi`, `uvicorn`, `jinja2`, an HTML→PDF tool (e.g. `weasyprint` or `playwright`), and FFmpeg (`winget install Gyan.FFmpeg`).

## What remains to finish the project (summary)

| # | Remaining piece | Blocked by | Size |
|---|---|---|---|
| 1 | **Test clips (5–8, including no-match vehicles and a cross-camera pair)** | Team filming (A5, A6) | 🔴 Blocks everything clip-based |
| 4 | Phase 1: plate detector fine-tune, UVH-26 vehicle type, colour classifier, tracking | Installs (C2), 0B | Medium |
| 5 | **Phase 2 (judged): multi-frame fusion with `?`, synthetic registry, scorer with reasons, no-match threshold** | Clips for calibration | Large |
| 6 | Phase 3: FastAPI backend, investigator UI, HTML/PDF report per clip | Phases 1–2 | Medium |
| 7 | Phase 4: hand-labels for the clips, headline metrics, README, demo video, slides | Clips | Medium |
| 8 | Stretch: cross-camera re-ID, make/model | A6; verified labels | Optional |

Phase 0 is complete apart from 0D–0F (clips, degraded variants, registry), which wait on the clips. **Phase 1 starts only after approval.**
