# TRACEVISION AI — Team Tasks

**Updated:** 2026-11-22 · Problem: **AIML-01 Vehicle Identification and Traceability from CCTV Footage**
See also: [completions.md](completions.md) (what's done) · [whatnext.md](whatnext.md) (full plan) · [PROBLEMS.md](PROBLEMS.md) (problem IDs like A5, B1)

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

Already cloned without these? Run `git lfs pull` and `git submodule update --init`.

**What's in the repo:**

| Path | Contents |
|---|---|
| `TRACEVISION_DATA/raw/plate_detection/` | Quobotic v3 YOLO plate dataset, 2069 / 336 / 169 images (CC BY 4.0). **Do not open it in File Explorer and do not rename it.** It is byte-identical to the source zip. |
| `TRACEVISION_DATA/raw/ocr_corpus/zenitsu09/` | OCR source parquet |
| `TRACEVISION_DATA/processed/ocr_evaluation/zenitsu09/` | 1,709 plate crops, `ground_truth.csv` (965 unique plates), and the Awiros smoke-test outputs |
| `TRACEVISION_DATA/models/awiros/` | Awiros ANPR OCR weights (LFS) and `test.py` |
| `third_party/PaddleOCR` | PaddleOCR (submodule), needed by Awiros |
| `TRACEVISION_DATA/scripts/` | Audit, OCR eval-set builder, Awiros feasibility check |

Don't commit test clips, frames or `.pt` weights (`.gitignore` blocks them). Share clips via the team drive instead.

---

## Current facts that shape the work

- **Awiros OCR works:** 9/9 model-card samples reproduced. Full benchmark on 965 unique plates: **81.5% exact / 4.4% CER**, or 86.0% / 3.1% on standard-format labels (`--preprocess paddle`; the official `test.py` preprocessing drops characters, B8). Latency: **15 ms per crop on the GPU** (`paddlepaddle-gpu` 3.3.1 cu126), against about 3.8 s on the CPU (B7 ✅). See `reports/awiros_feasibility.md`.
- **Per-character probabilities ARE available** from the CTC head, so multi-frame fusion can use real per-character confidence (B1 resolved).
- ⚠️ **CPU latency is about 4 s per crop (median), with p95 at 11 s.** That is too slow for video. Run OCR on a GPU (local RTX 3050 or Colab), OCR only the best 3–5 frames per track, or both.
- **There are no test clips yet (A5).** Everything clip-based is blocked on WS1.

---

## WS1 — Test clips and ground truth 🔴 start today  · Owner: ________

- [ ] Film 5–10 phone clips (10–30 s each) from a high, distant, CCTV-like angle: cars, SUVs, two-wheelers, autos, trucks
- [ ] Include blurred, partly hidden and dirty plates, plus **at least 2 vehicles that will not be put in the registry** (no-match test)
- [ ] Film **one vehicle from two positions** (cross-camera bonus, A6)
- [ ] Check `~/Downloads/DS.mp4` and `original-5adf….mp4` (A11)
- [ ] Put the clips on the team drive and in your local `TRACEVISION_DATA/raw/test_videos/` (not in git). Create `raw/test_videos/clips.csv` with: `clip_id, file, source, licence, notes`
- [ ] Create `evaluation/clip_ground_truth.csv` with: `clip_id, vehicle_id, plate_text (use ? for unreadable), colour, type, in_registry (y/n)`

**Done when:** at least 5 clips are on the drive, both CSVs are committed, and at least 2 vehicles are marked `in_registry = n`.

## WS2 — Plate detector data and training (Phase 0B → 1) · Owner: ________

- [ ] `scripts/validate_plate_dataset.py`: box vs polygon counts (A19), near-duplicates across splits (A15, `pip install imagehash`), plate-size histogram → `reports/plate_dataset_validation.md`
- [ ] `scripts/prepare_plate_detection.py`: write `processed/plate_detection/` with short hashed names plus `name_map.csv` (A18), polygons converted to boxes, and a relative-path `data.yaml` (A4)
- [ ] Fine-tune YOLOv8n on Colab or the RTX 3050 (`pip install ultralytics`). Report mAP50 on test.

**Done when:** `best.pt` is on the team drive and the mAP is recorded in `reports/`.

## WS3 — OCR, vehicle type and colour (Phase 0C → 1) · Owner: ________

- [x] Full Awiros benchmark (CPU) and report `reports/awiros_feasibility.md`. Done.
- [x] GPU build installed and benchmarked: 15 ms median per crop. Install it with `pip install paddlepaddle-gpu==3.3.1 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/` (uninstall `paddlepaddle` first).
- [ ] Load UVH-26 and build `class_mapping.json` from the real class names (B3, B4)
- [ ] Colour: HSV / k-means on the body crop → ~10 colour names plus a confidence score
- [ ] Vehicle tracking with ByteTrack

**Done when:** one function takes a clip and returns, per track, the vehicle type, colour and per-frame plate crops.

## WS4 — Matching algorithm (judged deliverable; no clips needed) · Owner: ________

- [ ] `registry/registry.csv`: ~1,000 synthetic Indian vehicles (`plate, colour, type, make, model, owner_synthetic`), with near-miss decoys (same partial plate, different colour or type)
- [ ] **Multi-frame fusion:** align each frame's OCR to the plate pattern (`SS NN X(XX) NNNN` and the BH series) → confidence-weighted vote per position using the Awiros per-character probabilities → output `?` below the threshold. **Never fill in a guess.**
- [ ] **Scorer:** wildcard-aware plate match with partial credit for look-alike characters (0/O/D, 8/B, 1/I, 5/S, 2/Z), combined with colour and type weights into one confidence, plus a **reasons list** for each candidate
- [ ] Top 5 output, and **"no confident match"** below a calibrated threshold
- [ ] Unit tests (wildcards, look-alikes, ties, all-`?` plate, empty registry)

**Done when:** `match(partial_plate, colour, type) → top5 | no_match` passes its tests.

## WS5 — App and report (no clips needed to start) · Owner: ________

- [ ] FastAPI backend: `POST /analyze` (clip upload) → job → JSON result. Use stub pipeline outputs until WS2–WS4 land.
- [ ] Investigator UI: upload, progress, the frames used, the characters per frame with confidence, and the top-5 table with reasons (or "no confident match")
- [ ] HTML → PDF report (Jinja2 plus WeasyPrint or Playwright) containing every field the problem statement asks for
- [ ] Batch mode: one report per test clip into `evaluation/reports/`

**Done when:** a stub clip produces a full report end to end.

---

## Integration milestones

| # | Milestone | Needs |
|---|---|---|
| M1 | Clip → tracks → per-frame plate text | WS1, WS2, WS3 |
| M2 | Plus fusion and ranking → top 5 / no-match | M1, WS4 |
| M3 | Plus UI and report for every clip | M2, WS5 |
| M4 | Metrics on our clips, README architecture diagram, demo video | M3 |

Data licences and privacy: Quobotic is CC BY 4.0 (credit it in the README). zenitsu09 states no licence (internal evaluation only). Awiros is Apache-2.0. The Ultralytics models are AGPL-3.0 (B6).
