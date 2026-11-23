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
| Colour exact / near | **28/44 (64%) / 33/44 (75%)** with CLIP (was 12/44 / 25/44 with the hue rule) | | |
| Colour answered `unknown` | 4/44 (9%) | | |

### What the numbers mean
1. **The system never wrote a wrong plate character (0/132).** Where unsure, it wrote `?`. This is the property the problem statement asks for: *never fill in a guess*.
2. **No unregistered vehicle was "identified" (0/42).** Wildcard matching plus the thresholds and the "≥ 5 readable characters" rule keep false identifications at zero on this set.
3. **8 of 9 registered vehicles were identified**, one of them from a partial plate (`UP1?FT?44?` → `UP16FT9444`). The miss (clip07 `DL8CAH1004`) never shows a plate taller than 13 px, so it's below the 16 px bar (M8) and correctly not read.
4. **CCTV-style clips:** every vehicle is found and typed (86% exact), but **no plate is large enough to read**, so every answer is "no confident match". That's correct behaviour, and it's why the split matters (E7).

### Update 2026-11-23: phantom-box fix (PROBLEMS C11, DECISIONS M12)
UVH-26 sometimes reports a frame-wide "Truck" over empty road, sky, sign boards or barriers. Large tracks are now cross-checked with COCO YOLOv8n; **13 phantom tracks were removed from 6 of the 11 clips** (every one checked by eye: road, sky, signs, barriers; real trucks such as the clip10 tanker are kept). Re-evaluated: **every detection, plate and matching metric is unchanged** (44/51 detected, 8/9 matched, 0/42 false matches, 0/132 wrong characters). Colour moved from 11 to 12 exact (one labelled vehicle is no longer linked to a phantom box). The robustness table below was produced before this fix and was not re-run.

### Update 2026-11-23: CLIP colour (PROBLEMS C8, DECISIONS M13)
The hue/k-means colour rule was replaced by **CLIP ViT-B/32 zero-shot** (OpenAI weights via open_clip): each vehicle's best crops are compared with fixed prompts ("a photo of a white car", "a gray SUV seen from behind", …) over the 10 colour names; the "too dark → unknown" rule is kept. **Nothing was tuned on these labels** (the prompts, colour list and night rule were fixed before evaluating).
| | Hue rule | CLIP |
|---|---|---|
| Colour exact | 12/44 (27%) | **28/44 (64%)** |
| Colour near | 25/44 (57%) | **33/44 (75%)** |
| Moving / fixed CCTV-style (exact) | 30% / 21% | 67% / 57% |
Remaining 12 errors are scattered (black→white ×2, black→red, black→green, white→silver/green/yellow, silver→grey/white/yellow, yellow→brown, grey→white); no systematic haze failure any more. Detection, plate and matching metrics are unchanged (8/9 matched, 0/42 false matches, 0/132 wrong characters). Cost: ~15 ms per vehicle on the RTX 3050. The colour lines of the robustness table below are from the old rule.

### Update 2026-11-23: 19 clips (clip12–19 added: cross-camera parking pairs)
67 owner-verified vehicles (clip12–19 drafted by Claude from the frames, verified by the owner). Registry re-seeded (3 new seeds: `CG04NL3024`, `CG14MW3529`, `CG04DK1578`); matcher thresholds recalibrated to the same values (67.5 / 4.0, holdout 36/36).
**Evaluation change (DECISIONS E13):** vehicles labelled `in_registry = yes` whose full plate nobody knows cannot be in the registry, so they are reported separately (6: dark SUV `CG04?S9584`, Activa behind a tag, plate-less scooter, each in 2 clips) and still checked for false matches; the registry lookup now runs for every labelled vehicle (a not-found registered vehicle counts as a miss).
| | 11 clips | **19 clips** |
|---|---|---|
| Registered matched | 8/9 | **11/15** |
| False confident matches (unregistered) | 0/42 | **0/46** (+ 0/6 on the plate-unknown ones) |
| Wrong plate characters | 0/132 | **0/181** |
| Detected and tracked at the labelled frame | 44/51 | 52/67 |
| Type compatible / colour exact | 93% / 64% | 90% / 60% |
New misses: clip15 white SUV (plate unreadable there), clip17 motorcycle (plate read as `???????`), clip16 motorcycle (tracked only from about frame 126; the label is at frame 0). Close-up parked two-wheelers (clip16–19) are tracked late or not at all at the labelled frame: 5 of 9 not found (C12).

### Update 2026-11-23 (later): two-detector ensemble (M15) and one-to-one evaluation (E14)
Owner-reported failures on the parking clips (Honda Amaze typed "truck", hidden-plate Activa not boxed, plate-less scooter "truck") came from **UVH-26 being out of domain on close-up, ground-level footage** (confidence 0.1–0.3, wrong classes) while COCO YOLOv8n saw them at 0.7–0.9 (C13). A COCO tracking pass now adds type votes / missed frames to UVH-26 tracks and adds confident COCO-only tracks; COCO overrides the type only when UVH-26 is unsure (< 0.5; set after an override turned a clip02 CCTV SUV into "bus").
The evaluation now links labels to system vehicles **one-to-one** (E14): before, one system vehicle could be counted for two labels, which turned 2 correct identifications (clip07 `DL8CAH1004`, clip17 `CG04DK1578`) into fake "false matches" for the neighbouring labelled vehicle.
| | Before (19 clips) | **After** |
|---|---|---|
| Detected and tracked | 52/67 | **61/67** |
| Type exact / compatible | 67% / 90% | **77% / 95%** |
| Registered matched | 11/15 | **14/15** |
| False confident matches | 0/46 | **0/46** |
| Wrong plate characters | 0/181 | **0/234** |
| Colour exact | 60% | 59% |
Colour: centre-cropped variants were tested (full 69% / shrink10 65% / shrink20 59% / shrink30 53% exact on 51 vehicles) and rejected.

### Note 2026-11-23: clip08_v02 / clip08_v03 relabelled
The owner checked the two plates the system read where the labels said "unreadable" (`UP37P1176`, `DL3SS5192`) and confirmed both are correct, so they are now `full` labels. Caveat: these two labels were confirmed *after* seeing the system's read, so they are not independent evidence; they add 18 correctly-read characters to the plate score.

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

Clips with registered vehicles (clip01, 03, 04, 08, 11): 21 labelled vehicles, 8 registered.

| Variant | Registered matched | False confident matches | Plate chars correct | Plate chars `?` | **Plate chars WRONG** | Detected | Type compatible | Colour near |
|---|---|---|---|---|---|---|---|---|
| **original clips** | 8/8 (100%) | 0/13 (0%) | 98/104 (94%) | 6/104 (6%) | 0/104 (0%) | 18/21 (86%) | 17/18 (94%) | 9/18 (50%) |
| gaussian blur | 1/8 (12%) | 0/13 (0%) | 23/39 (59%) | 11/39 (28%) | 5/39 (13%) | 15/21 (71%) | 13/15 (87%) | 8/15 (53%) |
| motion blur | 1/8 (12%) | 0/13 (0%) | 10/19 (53%) | 8/19 (42%) | 1/19 (5%) | 15/21 (71%) | 14/15 (93%) | 9/15 (60%) |
| down 480p | 1/8 (12%) | 0/13 (0%) | 19/29 (66%) | 10/29 (34%) | 0/29 (0%) | 17/21 (81%) | 16/17 (94%) | 6/17 (35%) |
| down 360p | 1/8 (12%) | 0/13 (0%) | 14/30 (47%) | 11/30 (37%) | 5/30 (17%) | 17/21 (81%) | 15/17 (88%) | 10/17 (59%) |
| jpeg q10 | 1/8 (12%) | 0/13 (0%) | 23/84 (27%) | 55/84 (65%) | 6/84 (7%) | 14/21 (67%) | 13/14 (93%) | 5/14 (36%) |
| night | 1/8 (12%) | 0/13 (0%) | 27/39 (69%) | 7/39 (18%) | 5/39 (13%) | 10/21 (48%) | 9/10 (90%) | 0/10 (0%) |
| noise | 5/8 (62%) | 0/13 (0%) | 68/94 (72%) | 26/94 (28%) | 0/94 (0%) | 16/21 (76%) | 14/16 (88%) | 9/16 (56%) |

- **The safety property holds under every degradation: 0 false confident matches** (0/13 unregistered vehicles in each variant).
- **Identification collapses on heavily degraded footage:** 1/8 registered vehicles under blur, 480p, 360p, JPEG q10 and night (5/8 with noise). Most plates fall under the 16 px or confidence bars and come out as `?` or unread, which is the honest outcome.
- **But wrong characters do appear (up to 17% at 360p, 13% blur and night)**: on very degraded crops the OCR is sometimes *confidently* wrong, so the `?` rule (confidence ≥ 0.8) no longer catches everything. Next steps: raise the confidence bar when plate quality is low, or require agreement from ≥ 2 frames per character. Not tuned here, to avoid fitting the test set.
- Night: detection drops to about half; colour is always `unknown` or wrong (the night rule says "too dark" or picks up tail-light glare).
- These degradations are applied **on top of** WhatsApp-compressed copies (about 1.5 Mbit/s), so they're harsher than the same effect on original footage.


## How these numbers were (and weren't) obtained, honestly
- **Some pipeline rules were diagnosed on these clips:** class-agnostic NMS, plate-based re-linking, the same-object containment rule, "too few characters → no confident match", and the colour band. Each fixes a specific, visible failure; none tunes a threshold to a label value. Still, with 51 vehicles (9 registered) **the numbers are probably optimistic** for new footage.
- **Matcher thresholds** were calibrated on synthetic cases only (held-out 41/41), not on these labels.
- **The test set is small and mostly ground-level footage.** A larger CCTV-style set is the most valuable next step.
