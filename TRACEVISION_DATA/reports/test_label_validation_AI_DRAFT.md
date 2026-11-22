# Test-label validation: AI DRAFT labels (NOT ground truth)

> This report checks `evaluation/test_clip_labels_AI_DRAFT.csv`, 51 rows all marked "AI DRAFT - verify". These are **not** human labels. The team must check every row against the clip and save the verified result as `evaluation/test_clip_labels.csv` (DECISIONS E11, PROBLEMS A23).

`TRACEVISION_DATA/evaluation/test_clip_labels_AI_DRAFT.csv`: **51 vehicles in 11 clips** - **1 errors, 0 warnings**. Labels were not modified.

- in_registry = no: 42 (need >= 2)
- cross-camera groups spanning >= 2 clips: none (need >= 1)
- readability: {'full': 11, 'partial': 8, 'none': 32}
- types: {'SUV': 12, 'auto_rickshaw': 6, 'car': 24, 'motorcycle': 5, 'scooter': 1, 'truck': 3}

| Severity | Vehicle / group | Issue |
|---|---|---|
| error | (coverage) | no cross-camera group spanning 2 clips; the spec requires >= 1 |
