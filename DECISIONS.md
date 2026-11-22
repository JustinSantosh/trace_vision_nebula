# TRACEVISION AI — Decision Log

**Last updated:** 2026-11-22 · One line per decision: what was decided, why, and where the evidence lives. Problem IDs (A5, B7, …) refer to [PROBLEMS.md](PROBLEMS.md). Done work is in [completions.md](completions.md) and the plan in [whatnext.md](whatnext.md).

**Status:** ✅ in force · 🔁 changed (the old version is kept and struck through) · ⏳ waiting on someone

## Data

| # | Date | Decision | Why | Ref | Status |
|---|---|---|---|---|---|
| D1 | 2026-11-22 | Replace the empty D1 repo with **Roboflow Quobotic v3** (CC BY 4.0) as the plate-detection set | The original HF repo had no data. Quobotic is real scenes with real plates (checked visually). | A1, `reports/d1_d2_alternatives.md` | ✅ |
| D2 | 2026-11-22 | **Reject Roboflow b8iqo.** It was moved to `raw/_rejected/`, not deleted. | It is synthetic: rendered plates fill the whole frame. | A14 | ✅ |
| D3 | 2026-11-22 | **View sample images before recommending any dataset** | Card metadata alone led to b8iqo | A14 | ✅ |
| D4 | 2026-11-22 | Replace the empty D2 repo with **zenitsu09** (965 unique plates) for the standalone OCR benchmark only. Use it internally, since it states no licence. witvix stays optional. | The original HF repo had no data. zenitsu09 is available now. | A2, A12 | ✅ |
| D5 | 2026-11-22 | **zenitsu09 is never used for end-to-end detector + OCR evaluation** | Its crops come from the same images as Quobotic | A16 | ✅ |
| D6 | 2026-11-22 | Treat `raw/` as read-only. All renaming (short hashed names plus `name_map.csv`) and polygon-to-box conversion happen in `processed/`. | Preserve originals. Windows long paths break tools. | A18, A19 | ✅ |
| D7 | 2026-11-22 | Keep the **official Quobotic splits** despite leakage. Report it, and add `leakage_free_{valid,test}.txt` as a second, honest score. | The spec says to keep official splits and report leakage rather than silently fix it. 37% of test comes from train videos. | A15 | ✅ |
| D8 | 2026-11-22 | Flag the 82 doubtful zenitsu09 labels as `nonstandard_review`, but keep them. Score with and without them. | The spec says flag, don't reject. Some labels are clearly wrong (`TERRANO`). | A20 | ✅ |
| D9 | 2026-11-22 | **Never crop Quobotic train plates for OCR** | Train contains mirrored (flip-augmented) plates | A21 | ✅ |
| D10 | 2026-11-22 | ~~Raw data, crops, weights and real plates stay out of git~~ → **The datasets, crops and Awiros weights (via LFS) are pushed to the repo for the team.** | Team hand-off. **Risk: the repo is PUBLIC, so real plates are published.** Make it private unless that is intended. | E6 | 🔁 |

## Models and OCR

| # | Date | Decision | Why | Ref | Status |
|---|---|---|---|---|---|
| M1 | 2026-11-22 | Models: **UVH-26** (vehicle type), **Awiros ANPR OCR** (plates), **YOLOv8n** fine-tuned on Quobotic (plate detector) | Fit to Indian roads. Listed in `models/model_dependencies.md`. | B3–B6 | ✅ |
| M2 | 2026-11-22 | **Always run Awiros with PaddleOCR-style preprocessing** (`prep_paddle`: normalise, then zero-pad). Never use the official `test.py` preprocessing. | The official version drops characters: 3/7 against 7/7 on the card samples. The app must copy `prep_paddle`. | B8 | ✅ |
| M3 | 2026-11-22 | **Install `paddlepaddle-gpu` 3.3.1 (cu126)** in place of the CPU build, and always run OCR with `--device gpu` | The CPU build took 3.8 s per crop, the GPU 15 ms, with the same accuracy. Approved by the user. | B7 | ✅ |
| M4 | 2026-11-22 | Use the **mean / min per-character probability** as the OCR confidence for the `?` rule and for no-match | Mean ≥ 0.99 gives 97.1% exact; below 0.8 nothing was correct | `reports/awiros_feasibility.md` | ✅ |
| M5 | 2026-11-22 | Accept the AGPL-3.0 licence of the Ultralytics models for the hackathon and disclose it in the README | The non-AGPL alternatives cost time | B6 | ✅ |
| M6 | 2026-11-22 | Map UVH-26 Two-wheeler → `motorcycle/scooter` (ambiguous) and Three-wheeler → `auto_rickshaw`. Don't invent a split. | The model can't separate them | B4 | ⏳ applied in Phase 1 |

## Evaluation, clips and registry

| # | Date | Decision | Why | Ref | Status |
|---|---|---|---|---|---|
| E1 | 2026-11-22 | **Headline metrics come from our own CCTV-like clips**, not from the still-photo datasets | No replacement dataset is CCTV footage | A13 | ✅ |
| E2 | 2026-11-22 | The team films its own clips: **6–8 clips of 8–15 s** (5 s is the minimum), from a high, distant, CCTV-like angle, in landscape at 1080p. Include ≥ 2 vehicles not in the registry and 1 vehicle from two positions. | Plate reading across frames needs several clear frames per vehicle, and a 5 s clip gives only 5–10 samples | A5, A6 | ⏳ team |
| E3 | 2026-11-22 | **Ground-truth labels are written by humans only.** Claude never fills in plate text, colour, type, identity or cross-camera links. `?` marks unreadable characters, never a guess. | They are the answer key, so machine guesses would grade the system against itself | Spec | ✅ |
| E4 | 2026-11-22 | Add an optional `registry_plate_full` label column (the full plate known from **outside** the clip) | Needed to seed a partly readable vehicle into the registry, without inferring characters from video | A22 | ✅ |
| E5 | 2026-11-22 | Bounding boxes only on the first frame of each target vehicle | The spec requires this, and it saves labelling time | Spec | ✅ |
| E6 | 2026-11-22 | The registry is **fully synthetic** (`synthetic = true`). Clip vehicles go in only as `evaluation_seed` rows. **No owner fields at all.** | Privacy | Spec | ✅ |
| E7 | 2026-11-22 | Registry IDs are **random**, rows are shuffled, and the answer key (`registry_decoy_map.csv`) is kept in `evaluation/`. The scorer must never read it. | Stops anchor or decoy status leaking into the matcher | `generate_synthetic_registry.py` | ✅ |
| E8 | 2026-11-22 | A starter registry (334 records, 124 test cases) is generated **before** the clips exist, and re-seeded after labelling | The matching algorithm can be built and tested now | `reports/synthetic_registry_stats.json` | ✅ |
| E9 | 2026-11-22 | Call scores **"match score"** and never "probability" unless calibrated. Keep detector, OCR-character and match scores separate. | Spec convention | Spec | ✅ |

## Process

| # | Date | Decision | Why | Ref | Status |
|---|---|---|---|---|---|
| P1 | 2026-11-22 | Every script is tested on a small sample or fixture before the full run. Smoke-test fixtures stay in the scratchpad and are never committed. | Spec rule. No claims without a run. | All scripts | ✅ |
| P2 | 2026-11-22 | Installs need approval each time. So far approved: Awiros dependencies, pyarrow, paddlepaddle-gpu. | Spec rule | C1, C2 | ✅ |
| P3 | 2026-11-22 | **Phase 1 starts only after the user approves** | Spec: stop after Phase 0 | — | ⏳ user |
