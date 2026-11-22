# P6: Evaluation on our clips

**Date:** 2026-11-23 · **Approved by the owner:** "approve all phases remaining" · Code: `tracevision/evaluate.py`, `tracevision/robustness.py` · Raw: `p6_evaluation_baseline.json`, `p6_robustness.json`

**Ground truth:** `evaluation/test_clip_labels.csv`, 51 vehicles in 11 clips, **owner-verified** (commit `21d641d`).
**Association:** each labelled vehicle is linked to the pipeline vehicle whose box overlaps the labelled first-frame box best (IoU ≥ 0.3, ±4 frames). **Plate text is never used to associate**, so the plate metrics aren't circular.
**Split by camera type** (DECISIONS E10): `fixed_cctv_style` = clip02, clip06; `moving_camera` = the other 9.

## Headline results
| Metric | All | Moving camera | Fixed CCTV-style |
|---|---|---|---|
| Labelled vehicles | 51 | 37 | 14 |
| Detected and tracked | 44 (86%) | 30 (81%) | 14 (100%) |
| **Registered vehicles matched to the right record** (decision `match` + correct rank 1) | **8/9 (89%)** | 8/9 | n/a |
| Registered: correct record in the top 5 | 8/9 | 8/9 | n/a |
| **Unregistered vehicles given a false confident match** | **0/42** | 0/28 | 0/14 |
| No-match correct on detected unregistered vehicles | 35/35 | 21/21 | 14/14 |
| **Plate characters: correct** | **112/132 (85%)** | 112/132 | n/a: no plate ≥ 16 px |
| **Plate characters: `?` (not read, honestly)** | 20/132 (15%) | | |
| **Plate characters: WRONG** | **0/132 (0%)** | | |
| Exact plate (labels with no `?`) | 7/10 (70%) | | |
| Readable labelled plates the system didn't read | 2/16 (12%) | | |
| Plates humans marked unreadable but the system read | 2/28 (7%): **unverifiable**, see below | | |
| Type exact / compatible | 30/44 (68%) / 41/44 (93%) | 60% / 93% | 86% / 93% |
| Colour exact / near | 11/44 (25%) / 24/44 (55%) | | |
| Colour answered `unknown` | 4/44 (9%) | | |

### What the numbers mean
1. **The system never wrote a wrong plate character (0/132).** Where unsure, it wrote `?`. This is the property the problem statement asks for: *never fill in a guess*.
2. **No unregistered vehicle was "identified" (0/42).** Wildcard matching plus the thresholds and the "≥ 5 readable characters" rule keep false identifications at zero on this set.
3. **8 of 9 registered vehicles were identified**, one of them from a partial plate (`UP1?FT?44?` → `UP16FT9444`). The miss (clip07 `DL8CAH1004`) never shows a plate taller than 13 px, so it's below the 16 px bar (M8) and correctly not read.
4. **CCTV-style clips:** every vehicle is found and typed (86% exact), but **no plate is large enough to read**, so every answer is "no confident match". That's correct behaviour, and it's why the split matters (E7).

## Error analysis
- **Missed vehicles (7):** 4 have plates humans also marked `none`: far, tiny vehicles (about 30–60 px boxes, under the 0.4% minimum-area filter) or trucks cut off at the 4K frame edge. The other 3 are partly visible (an SUV behind others, a corner scooter, an edge truck).
- **Type (14 wrong):** 9 are **car → SUV** and 3 are SUV → car. UVH-26 separates Hatchback / Sedan / SUV / MUV, and compact SUVs and MPVs seen from behind confuse it. Since car and SUV are *compatible* in matching, these cost half credit, not a match. 1 truck → auto, 1 car → truck, 1 SUV → truck (at night).
- **Colour (19 wrong, plus 4 unknown):** mostly **white read as grey (6) or blue (3)** in haze or dusk light, and black read as grey. The heuristic has no white balance. It's the weakest component; a small colour classifier would be the next step.
- **Human-unreadable plates that the system read:** clip08_v02 (`UP37P1176`) and clip08_v03 (`DL3SS5192`). These may be correct, since the system reads the sharpest frames, but they can't be verified from the labels. **Owner check** (NEEDS.md).

## Speed
- In P4 the pipeline took **4–18 s per clip** (clips 4–30 s long) on an RTX 3050 laptop GPU with the machine otherwise idle. That's faster than real time for most clips.
- In the evaluation run (made while the degradation job was using the same GPU) it took 3.5–29 s. The 4K clips are the slowest.

## Robustness on degraded variants
*(clips with registered vehicles: clip01, 03, 04, 08, 11 × 7 variants; filled in by `python -m tracevision.robustness`)*

ROBUSTNESS_TABLE

## How these numbers were (and weren't) obtained, honestly
- **Some pipeline rules were diagnosed on these clips:** class-agnostic NMS, plate-based re-linking, the same-object containment rule, "too few characters → no confident match", and the colour band. Each fixes a specific, visible failure; none tunes a threshold to a label value. Still, with 51 vehicles (9 registered) **the numbers are probably optimistic** for new footage.
- **Matcher thresholds** were calibrated on synthetic cases only (held-out 41/41), not on these labels.
- **The test set is small and mostly ground-level footage.** A larger CCTV-style set is the most valuable next step.
