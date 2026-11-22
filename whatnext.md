# TRACEVISION AI — What Next

**Last updated:** 2026-11-23 · Done work: [completions.md](completions.md) · Problems: [PROBLEMS.md](PROBLEMS.md) · Decisions: [DECISIONS.md](DECISIONS.md) · Pipeline design: [PIPELINE.md](PIPELINE.md) · Team workstreams: [TEAM_TASKS.md](TEAM_TASKS.md)

**Where we are:**
- **Phase 0 (data):** done, except the **cross-camera pair** (A6) and the Phase 0 runs that need final labels (0E variants, 0F registry re-seed, final report).
- **Built and tested:** the vision stack (P1), the plate detector (P2) and the two judged algorithms (P3). The health check passed on 2026-11-23.
- **Next build step:** P4, the end-to-end pipeline. It **waits for the owner's approval.**

## 0. Team and owner actions

| Priority | Action | Status / unblocks |
|---|---|---|
| ✅ | **Test clips:** 11 Indian clips (clip01–11). 2 fixed CCTV-style (clip02, 06), 9 moving, including a night clip (clip11) and trucks (clip10). No more raised clips by team decision (E10, risk E7). | Done |
| ✅ | **Hand labels:** owner verified all 51 vehicles → `evaluation/test_clip_labels.csv`. 0 field errors (E11, A23). | Done |
| 🟠 1 | **Cross-camera pair:** film one car (yours) from **2 different spots** as 2 clips (send the original files, not WhatsApp). Label it in both with the same `cross_camera_group_id`, `in_registry = yes` and the real plate in `registry_plate_full`. | Clears the last label error. Needed for the cross-camera bonus and the Phase 0 report (A6). |
| 🟡 2 | **More `in_registry = yes` vehicles** with readable plates: only 9 of 51 are `yes`, so positive-match evaluation on real clips is thin. | Stronger P6 match metrics |
| 🟠 3 | **Repo visibility:** the repo is public and holds real plates and clips (E6 / D10). | Privacy decision |
| 🟡 4 | `~/Downloads/DS.mp4` and `original-5adf….mp4` were never checked (A11). | Optional |
| ⚪ 5 | witvix access form for a harder OCR test (A2) | Optional |

## 1. Phase 0 (data): status
- [x] 0A audit · 0B plate data (validated, short-name copy, `data.yaml`) · 0C Awiros check (81.5% exact, GPU 15 ms per crop)
- [x] 0D: 11 clips, frames, contact sheets, template, guide; labels verified (51 vehicles)
- [x] All 10 spec scripts exist and pass a smoke run (health check 2026-11-23)
- [ ] **0E:** run `degrade_clips.py` on the labelled clips, then the team marks `readable_after_degradation` for the ~25% review sample. *Can run now.*
- [ ] **0F:** regenerate the registry from the real labels (`generate_synthetic_registry.py`), so the 9 `yes` vehicles become `evaluation_seed` rows with decoys. *Can run now; re-run after the car pair.*
- [ ] **0D/0E:** `multi_frame_sequences.json` and `cross_camera_ground_truth.csv` are written once the label validator shows 0 errors (needs the car pair).
- [ ] **Final Phase 0 report** (after the car pair)

## 2. Build steps (PIPELINE.md §10)
- [x] **P1** vision stack: torch + ultralytics on GPU, UVH-26 (14 classes) + `class_mapping.json`, OCR in a separate worker process (C5). `reports/p1_vision_stack.md`
- [x] **P2** plate detector: YOLOv8n, **leakage-free mAP50 0.995**; plates under 16 px are reported unreadable (M8). `reports/p2_plate_detector.md`
- [x] **P3** judged algorithms: **multi-frame fusion** (`?` instead of guesses) + **registry matching** (match score, reasons, match / ambiguous / no-match), 26 tests, calibrated (held-out 62/62 on synthetic cases). `reports/p3_fusion_and_matching.md`
- [ ] **P4 (needs approval):** `tracevision/pipeline.py`, running clip → detect → track (with re-linking, C6) → best frames → plate detect → OCR worker → fuse → colour → match → `runs/<job>/result.json`, on all 11 clips. Includes the **colour estimator** (PIPELINE §5).
- [ ] **P5 (needs approval for installs):** FastAPI + investigator UI + **HTML/PDF report for every clip** (`fastapi`, `uvicorn`, `jinja2`, an HTML→PDF tool).
- [ ] **P6:** evaluation on the labels, split by camera type (E10): plate character accuracy, **`?` rate against wrong-character rate**, type and colour accuracy, top-1/top-5, no-match precision, robustness on degraded variants, speed. Re-check the matcher thresholds on clip cases.

## 3. Submission
- [ ] README: architecture diagram, how to run, models and licences (Quobotic CC BY 4.0 credit, AGPL for Ultralytics: B6), honest note on camera types (E7)
- [ ] Demo video (include one CCTV-style clip showing "no confident match") and slides
- [ ] Stretch: cross-camera re-ID (A6), make/model (only with verified labels)

## Installs still needed
`fastapi`, `uvicorn`, `jinja2`, an HTML→PDF tool (P5). Optional: FFmpeg (C1). *(Done: torch 2.14.1+cu126, ultralytics, lap, paddlepaddle-gpu, pyarrow.)*

## What remains to finish the project (summary)

| # | Remaining piece | Blocked by | Size |
|---|---|---|---|
| 1 | **P4 end-to-end pipeline** (+ colour, track re-linking) on all clips | Owner approval | Large |
| 2 | **P5 app + per-clip PDF reports** | P4; install approval | Medium |
| 3 | **P6 evaluation** (headline metrics from our clips) | P4 | Medium |
| 4 | Phase 0 finish: 0E variants, 0F registry re-seed, final Phase 0 report | Can start now; the car pair for the final version | Small |
| 5 | Cross-camera pair (film + label) | Team | Small |
| 6 | README, demo video, slides | P4–P6 | Medium |
| 7 | Stretch: cross-camera re-ID, make/model | Car pair; verified labels | Optional |
