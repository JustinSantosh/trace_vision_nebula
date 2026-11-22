# TRACEVISION AI — What Next

**Last updated:** 2026-11-23 · Done work: [completions.md](completions.md) · Problems: [PROBLEMS.md](PROBLEMS.md) · Decisions: [DECISIONS.md](DECISIONS.md) · Pipeline design: [PIPELINE.md](PIPELINE.md) · Team workstreams: [TEAM_TASKS.md](TEAM_TASKS.md)

**Where we are:**
- **Phase 0 (data):** done, except the **cross-camera pair** (A6) and the Phase 0 runs that need final labels (0E variants, 0F registry re-seed, final report).
- **Built and tested:** the vision stack (P1), the plate detector (P2) and the two judged algorithms (P3). The health check passed on 2026-11-23.
- **All build phases P1–P6 are done** (2026-11-23 overnight). **What's left is owner actions: [NEEDS.md](NEEDS.md)** (car pair, repo visibility, demo video and slides).

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
- [x] **0E:** degraded variants made for all 11 clips (77 videos, local) and used in the robustness test. **Owner:** fill `readable_after_degradation` for the review sample (NEEDS 5).
- [x] **0F:** registry regenerated from the real labels (9 `evaluation_seed` rows plus decoys). *Re-run after the car pair.*
- [x] **0D/0E:** `multi_frame_sequences.json` written (51 sequences). `cross_camera_ground_truth.csv` is empty until the car pair is filmed.
- [ ] **Final Phase 0 report** (after the car pair)

## 2. Build steps (PIPELINE.md §10)
- [x] **P1** vision stack: torch + ultralytics on GPU, UVH-26 (14 classes) + `class_mapping.json`, OCR in a separate worker process (C5). `reports/p1_vision_stack.md`
- [x] **P2** plate detector: YOLOv8n, **leakage-free mAP50 0.995**; plates under 16 px are reported unreadable (M8). `reports/p2_plate_detector.md`
- [x] **P3** judged algorithms: **multi-frame fusion** (`?` instead of guesses) + **registry matching** (match score, reasons, match / ambiguous / no-match), 26 tests, calibrated (held-out 62/62 on synthetic cases). `reports/p3_fusion_and_matching.md`
- [x] **P4 done** (`reports/p4_pipeline.md`): ~~ `tracevision/pipeline.py`, running clip → detect → track (with re-linking, C6) → best frames → plate detect → OCR worker → fuse → colour → match → `runs/<job>/result.json`, on all 11 clips. Includes the **colour estimator** (PIPELINE §5).~~ 8/9 registered vehicles matched, 0 false matches.
- [x] **P5 done:** report (HTML + PDF) for every clip in `evaluation/reports/`, and the FastAPI app (`python -m tracevision.api`). See `reports/p5_app_and_reports.md`.
- [x] **P6 done:** evaluation vs labels + robustness sweep (`reports/p6_evaluation.md`): 8/9 matched, 0/42 false matches, 0/132 wrong plate characters.

## 3. Submission
- [ ] README: architecture diagram, how to run, models and licences (Quobotic CC BY 4.0 credit, AGPL for Ultralytics: B6), honest note on camera types (E7)
- [ ] Demo video (include one CCTV-style clip showing "no confident match") and slides
- [ ] Stretch: cross-camera re-ID (A6), make/model (only with verified labels)

## Installs still needed
`fastapi`, `uvicorn`, `jinja2`, an HTML→PDF tool (P5). Optional: FFmpeg (C1). *(Done: torch 2.14.1+cu126, ultralytics, lap, paddlepaddle-gpu, pyarrow.)*

## What remains to finish the project (summary)

| # | Remaining piece | Who | Size |
|---|---|---|---|
| 1 | Film and label the cross-camera car pair; then Claude re-runs validation, registry, pipeline, reports, evaluation, and the final Phase 0 report | Owner → Claude | Small |
| 2 | Repo visibility decision | Owner | 1 min |
| 3 | Demo video and slides (demo flow in NEEDS.md) | Owner (Claude can draft slides) | Medium |
| 4 | Optional: more `in_registry = yes` vehicles; originals instead of WhatsApp copies; review the degraded sample; check 2 unverifiable plate reads | Owner | Small |
| 5 | Optional improvements: a trained colour classifier (C8), better car/SUV typing (C9), more CCTV-style clips (E7) | Team | Medium |
