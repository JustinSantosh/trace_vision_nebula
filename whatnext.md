# TRACEVISION AI — What Next

**Last updated:** 2026-11-22 · What is already done is in [completions.md](completions.md). Problem IDs (A5, B1, …) refer to [PROBLEMS.md](PROBLEMS.md).

## 0. Team actions — unblock these first

| Priority | Action | Unblocks |
|---|---|---|
| 🔴 1 | **Get 5–8 test clips** into `TRACEVISION_DATA/raw/test_videos/`. The fastest way is to film short phone clips from a high, distant, CCTV-like angle: parked and passing cars, two-wheelers, autos and trucks. Include some blurred or partly hidden plates. Record the source and licence for each clip in a `clips.csv` (A5). | Every clip-based phase, the demo and the per-clip reports |
| 🔴 2 | **Include at least 2 vehicles that will NOT be in the registry**, to test no-match handling. | No-match must-have |
| 🟠 3 | **Cross-camera pair:** film the same vehicle from two phone positions (A6). | Bonus: cross-camera tracking |
| 🟡 4 | Check the two `.mp4` files in `~/Downloads` (`DS.mp4` and `original-5adf….mp4`). If they are test clips, move them into `raw/test_videos/` (A11). | A5 |
| ⚪ 5 | Optional: fill in the witvix Hugging Face access form for a harder OCR test (A2). | Out-of-domain OCR score |

## 1. Phase 0B — plate-detection data prep (next coding step)

- [ ] `scripts/validate_plate_dataset.py`: label sanity checks, box vs polygon line counts (A19), near-duplicate frames across splits (A15, needs `imagehash`), and plate-size distribution
- [ ] `scripts/prepare_plate_detection.py`: copy `raw/plate_detection` → `processed/plate_detection` with **short hashed filenames plus `name_map.csv`** (A18), polygons converted to boxes, and a Colab-ready `data.yaml` with relative paths (A4)
- [ ] Write the results to `reports/plate_dataset_validation.md`

## 2. Phase 0C — finish the Awiros OCR check

- [x] Install works on Windows CPU; 9/9 card samples reproduced
- [ ] **B1:** check whether the CTC head exposes **per-character probabilities**. Multi-frame fusion and the `?` rule depend on this. Fallback: use per-position agreement across frames as the confidence signal.
- [ ] Run Awiros on the zenitsu09 965-plate set. Report CER and exact-match accuracy, with and without the `nonstandard_review` rows, and split by crop height (A20).
- [ ] Measure CPU latency per crop
- [ ] Write the results to `reports/ocr_feasibility.md`

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
