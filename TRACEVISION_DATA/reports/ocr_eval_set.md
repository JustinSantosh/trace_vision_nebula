# OCR Evaluation Set: zenitsu09 (Phase 0C, part 1)

**Built by:** `scripts/build_ocr_eval_set.py`, tested on 50 rows first, then run on all 1,709. The crops and `ground_truth.csv` stay local and are excluded from git (real plates, source licence unstated).

```
python TRACEVISION_DATA/scripts/build_ocr_eval_set.py --parquet TRACEVISION_DATA/raw/ocr_corpus/zenitsu09/train-00000-of-00001.parquet --out TRACEVISION_DATA/processed/ocr_evaluation/zenitsu09
```

| | Count |
|---|---|
| Crops (all decoded, 0 corrupt) | 1,709 |
| Unique image hashes | 1,708 (1 exact duplicate) |
| Unique normalised plates (`eval_primary = 1`) | **965** |
| Format: standard / BH / flagged for review | 1,597 / 0 / 112 (primary rows: 883 / 0 / 82) |
| Layout guess (derived, w/h ≥ 2.2): single-row / two-row (primary rows) | 879 / 86 |
| Primary crops under 20 px tall | 364 (median height 23 px) |

The dataset has only one split, `train`, so there is no official test split to keep. The whole set is **evaluation-only**: Awiros is pretrained and is never tuned on it.

**By sub-source**
- `plates`: 38 rows, 10 plates (Roboflow augmented copies)
- `plates1`: 654 rows, 137 plates (consecutive video frames, so also usable for multi-frame tests)
- `plates2`: 417 rows, 230 plates
- `plates3`: 600 rows, 598 plates (small state-wise crops)

**Caveats:**
- The crops come from the same upstream images as the Quobotic detector data (PROBLEMS.md A16).
- Label errors are flagged as `nonstandard_review` rather than corrected (A20).
- Report headline CER and exact-match accuracy on `eval_primary == 1`, split by layout and crop height.
