# TRACEVISION AI — Team Tasks

**Updated:** 2026-11-22 · Problem: **AIML-01 Vehicle Identification and Traceability from CCTV Footage**
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

Already cloned without these? Run `git lfs pull` and `git submodule update --init`.

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
| `TRACEVISION_DATA/evaluation/`, `registry/` | Label template and guide, registry test cases, synthetic registry |

Don't commit test clips, frames or `.pt` weights (`.gitignore` blocks them). Share clips via the team drive instead.

---

## Current facts that shape the work

- **Awiros OCR works:** 9/9 model-card samples reproduced. Full benchmark on 965 unique plates: **81.5% exact / 4.4% CER**, or 86.0% / 3.1% on standard-format labels (`--preprocess paddle`; the official `test.py` preprocessing drops characters, B8). Latency: **15 ms per crop on the GPU** (`paddlepaddle-gpu` 3.3.1 cu126), against about 3.8 s on the CPU (B7 ✅). See `reports/awiros_feasibility.md`.
- **Per-character probabilities ARE available** from the CTC head, so multi-frame fusion can use real per-character confidence (B1 resolved).
- **Run OCR with `--device gpu`** (15 ms per crop). The CPU build takes about 3.8 s per crop, which is too slow for video.
- **There are no test clips yet (A5).** Everything clip-based is blocked on WS1.

---

## WS1: Test clips and ground truth 🔴 start today · Owner: ________

Read `TRACEVISION_DATA/evaluation/LABELING_GUIDE.md` first. All scripts are built and tested; the team only provides clips and labels.

- [ ] Film 5–8 phone clips (10–30 s each) from a high, distant, CCTV-like angle: cars, SUVs, two-wheelers, autos, trucks/buses, and ideally one at night
- [ ] Include blurred, partly hidden and dirty plates, plus **at least 2 vehicles that will NOT be in the registry** (no-match test)
- [ ] Film **one vehicle from two positions** (cross-camera, A6). For your own vehicles, note the full plate (`registry_plate_full`)
- [ ] Check `~/Downloads/DS.mp4` and `original-5adf….mp4` (A11)
- [ ] Put the clips in `TRACEVISION_DATA/raw/test_videos/` (videos are git-ignored, so also share them on the team drive), then run:
  1. `python TRACEVISION_DATA/scripts/extract_test_video_frames.py --videos TRACEVISION_DATA/raw/test_videos --out TRACEVISION_DATA/processed/test_video_frames --fps 1 2`
  2. `python TRACEVISION_DATA/scripts/create_test_clip_template.py` → fill in `evaluation/clips.csv` (source, licence, country, camera_id)
  3. Copy `evaluation/test_clip_labels_TEMPLATE.csv` → `evaluation/test_clip_labels.csv` and label **by hand** (`?` for unreadable characters, never guess)
  4. `python TRACEVISION_DATA/scripts/validate_test_labels.py`, then fix what `reports/test_label_validation.md` lists until there are 0 errors. This writes `multi_frame_sequences.json` and `cross_camera_ground_truth.csv`.
  5. `python TRACEVISION_DATA/scripts/degrade_clips.py` → fill in `readable_after_degradation` (yes / partial / no) for the rows marked `review_sample = yes` in `evaluation/difficult_cases.csv`
  6. `python TRACEVISION_DATA/scripts/generate_synthetic_registry.py` (re-seeds the registry with the labelled vehicles)
- [ ] Commit the CSV / JSON files and reports (not the videos)

**Done when:** at least 5 clips are labelled, the validation shows 0 errors, at least 2 vehicles are `in_registry = no`, there is at least 1 cross-camera group, and the registry has been regenerated.

## WS2 — Plate detector data and training (Phase 0B → 1) · Owner: ________

- [x] Validation + processed copy done (Phase 0B). See `reports/plate_dataset_validation.md`.
- [ ] Fine-tune YOLOv8n with **`data=<absolute path>/TRACEVISION_DATA/processed/plate_detection/data.yaml`** (never `raw/`). Use Colab or the RTX 3050 (`pip install ultralytics`, and the CUDA build of torch).
- [ ] Report mAP50 on the **official test** AND on **`leakage_free_test.txt`** (106 images). 37% of the official test comes from videos that are also in train (A15).
- [ ] Never crop train plates for OCR: train contains mirrored copies (A21).

**Done when:** `best.pt` is on the team drive and the mAP is recorded in `reports/`.

## WS3 — OCR, vehicle type and colour (Phase 0C → 1) · Owner: ________

- [x] Full Awiros benchmark (CPU) and report `reports/awiros_feasibility.md`. Done.
- [x] GPU build installed and benchmarked: 15 ms median per crop. Install it with `pip install paddlepaddle-gpu==3.3.1 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/` (uninstall `paddlepaddle` first).
- [ ] Load UVH-26 and build `class_mapping.json` from the real class names (B3, B4)
- [ ] Colour: HSV / k-means on the body crop → ~10 colour names plus a confidence score
- [ ] Vehicle tracking with ByteTrack

**Done when:** one function takes a clip and returns, per track, the vehicle type, colour and per-frame plate crops.

## WS4 — Matching algorithm (judged deliverable; no clips needed) · Owner: ________

- [x] Registry: `TRACEVISION_DATA/registry/synthetic_vehicle_registry.csv` (334 fictional records, seeded) plus `evaluation/registry_test_cases.csv` (124 cases with the expected outcome across all 9 spec scenarios). **Build and test the scorer against these now.** It is re-seeded with the real clip vehicles after WS1 step 6. The scorer must never read `registry_decoy_map.csv`, which is the answer key. No owner fields exist, by design (privacy).
- [ ] **Multi-frame fusion:** align each frame's OCR to the plate pattern (`SS NN X(XX) NNNN` and the BH series) → confidence-weighted vote per position using the Awiros per-character probabilities → output `?` below the threshold. **Never fill in a guess.**
- [ ] **Scorer:** wildcard-aware plate match with partial credit for look-alike characters (0/O/D, 8/B, 1/I, 5/S, 2/Z), combined with colour and type weights into one **match score** (not a probability), plus a **reasons list** for each candidate
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
