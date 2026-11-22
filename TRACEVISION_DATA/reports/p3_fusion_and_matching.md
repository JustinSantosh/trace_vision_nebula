# P3: Multi-frame fusion and registry matching (the judged algorithms)

**Date:** 2026-11-23 · **Approved by the owner:** "Approve P3" · Code: `tracevision/` · Tests: `tests/` (26 passing) · Calibration: `python -m tracevision.calibrate`, raw output in `p3_match_calibration.json`

## What was built
| File | What |
|---|---|
| `tracevision/plates.py` | Indian plate rules: state codes, standard and BH formats, letter/digit layout per position, look-alike groups (0/O/D/Q, 1/I, 2/Z, 5/S, 8/B, 6/G) |
| `tracevision/fuse.py` | **Multi-frame fusion:** medoid reference read → edit-distance alignment of every read (a dropped character doesn't shift the rest) → quality × probability votes per position (top-3 alternatives vote too) → `?` unless **vote share ≥ 0.6 and confidence ≥ 0.8**. A wrong-class character (e.g. `8` where a letter must be) is folded to its look-alike (`B`) at half weight. On its own that's not enough to emit the character. Unknown state codes give a warning and are never "corrected". |
| `tracevision/match.py` | **Ranking:** weighted edit distance where `?` matches anything for free and look-alikes cost 0.4. Plate similarity is squared and scaled by √coverage, then combined: **match score = 100 × (0.70·plate + 0.15·colour + 0.15·type)**. Unknown colour or type are dropped from the weighting, not penalised. Every candidate gets **reasons in plain English**. **Decision:** `no_confident_match` if the top score is under `t_abs` or fewer than 5 characters are readable; `ambiguous` if #1 − #2 < `t_margin`; otherwise `match`. The scorer never reads the answer key. |
| `tracevision/calibrate.py` | Threshold calibration with a split by anchor vehicle (below) |
| `tracevision/config.yaml` | All thresholds and weights in one place |

## Design decisions made while testing (not fitted to the test cases)
1. **Plate similarity is squared.** Before the change, an exact plate with a colour conflict (85.0) only just beat a *different* vehicle whose plate was wrong in 2 characters but whose colour matched (84.4). Two wrong characters should outweigh a colour difference. With squaring, the scores are 85.0 against 72.3.
2. **Fusion confidence averages only the reads that agree.** Disagreement is already measured by the vote share; counting it twice turned 2-of-3 agreeing reads at 0.98 into a `?`.
3. **A lone cross-class character becomes `?`.** One read of `8` in a letter position gives `?`, with `B` recorded as the best candidate for the report. When other reads support `B`, it is emitted.

## Answer-key bug found and fixed (in the generator, not the matcher)
The matcher returned **ambiguous** for `CG13B?28?` (a blue van) where the key said `match`. Registry check: `CG13B0287` and `CG13B6287` are both blue vans of the same model and differ only at position 6, **which the query hides**. A confident single answer would be wrong, so the matcher was right. `generate_synthetic_registry.py` now checks every synthetic `match` case and relabels it `ambiguous` when another vehicle fits every readable character, the colour and the type. **20 of 124 cases were relabelled**, mostly partial-plate cases where a decoy differed only in the hidden last 3 characters. The registry rows didn't change.

## Calibration (`t_abs`, `t_margin`)
- **Split by anchor vehicle:** 6 anchors (62 cases) for calibration, 6 anchors (62 cases) held out. No anchor is used for both.
- **Grid:** `t_abs` 50–90 (step 2.5) × `t_margin` 0–20, scored by balanced accuracy over match / ambiguous / no-match.
- 120 grid points tie at 100% on calibration, so I took the **centre of that range: `t_abs = 67.5`, `t_margin = 5`**. Written to `config.yaml`.

| Split | Match (top-1 correct and decided) | Ambiguous (no false confident match) | No match | Top-1 / Top-5 on match cases |
|---|---|---|---|---|
| Calibration | 32/32 | 28/28 | 2/2 | 32/32 · 32/32 |
| **Holdout** | **32/32** | **28/28** | **2/2** | **32/32 · 32/32** |

All 11 scenarios score 100% on the holdout: exact, partial plate, unknown characters (with and without colour), cross-class OCR confusion, confusable candidates, conflicting colour, similar colour but different type, similar-looking vehicles, multiple plausible, and no matching entry.

## Honest limits
- **These cases are synthetic and built around known decoy types.** 100% here means the logic handles the designed traps; **it is not a measure of real-world accuracy.** A wide range of thresholds works, so the cases don't constrain the thresholds tightly.
- **Only 4 no-match cases** (2 per split). Real no-match evidence will come from the clip vehicles labelled `in_registry = no`.
- Thresholds must be **re-checked on the clip cases** once human labels exist (P6), with real OCR noise from the pipeline.
- Fusion is unit-tested on synthetic reads; it hasn't yet run on real Awiros reads from the clips (P4).
- Limitation: if *every* read drops the same character, fusion can't recover it, because the reference has no slot for it.
