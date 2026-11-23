# Dataset and evaluation integrity

Nothing in any dataset, manifest or ground-truth file was modified.

## VCoR (colour)
| Check | Result |
|---|---|
| Manifest records vs files | 10,295 in the embedding manifest; 10,373 files on disk (the 78 documented exclusions); **0 missing** |
| Corrupt images (`PIL.verify`) | **0** |
| Exact duplicate files (MD5) | **0** groups, so 0 across splits |
| Near-duplicates across splits (CLIP cosine ≥ 0.995 to any train image) | **0** val, **0** test; ≥ 0.98: 7 val, 3 test |
| Split sizes | train 7,208 · val 1,542 · test 1,545 |
| Class balance | `other` (beige, gold, pink, purple merged) is the largest class (≈ 23%); `silver`, `white`, `black` the smallest (≈ 5–6%). The probe uses inverse-frequency class weights; macro-F1 is reported next to accuracy for this reason |
| Label mapping | 15 VCoR colours → 11 active labels of the fixed 12-label vocabulary (`unknown` never a training target). Vocabulary unchanged |
| Embedding cache vs production inference | re-embedded sample: cosine 1.0000 |

Use of splits in this audit: train = fitting; val = choosing C; test = scored once afterwards.

## Team evaluation clips (`TRACEVISION_DATA/evaluation/`)
| Check | Result |
|---|---|
| `test_clip_labels.csv` | 67 rows, 19 clips, no duplicate (clip, vehicle) keys, every row has a first-frame box |
| Videos on disk | 17 of 19 (`clip10`, `clip11` are Pexels stock and not in Git); their stored `result.json` remain, so headline metrics still cover 19 clips while video-based checks cover 62 of 67 vehicles |
| Labels clip12–19 | AI-drafted then owner-verified (as stated in the README); kept as is |
| Use in this audit | **reporting only**: no threshold, model or default was chosen with them |

## Metric code reviewed
- `train_linear_probe.compute_metrics`: confusion-matrix based precision/recall/F1, macro over classes with support; top-2 from probabilities. Correct.
- Zero-shot comparison renormalises over the 11 VCoR labels, giving `other` zero mass; this is disclosed in the model audit because it disadvantages zero-shot on VCoR.
- `evaluate_cctv_clips.py` bypassed the production confidence gate for the probe and lower-cased vehicle types; both reasons why its numbers differ from the production-path check (see model audit).

## Not established
- That no physical vehicle appears in more than one VCoR split (only image-level duplicates were checked).
- Any leakage statement about the plate-detector split beyond the team's own `leakage_free_test.txt` process.
