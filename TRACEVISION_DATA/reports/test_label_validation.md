# Test-label validation

`TRACEVISION_DATA/evaluation/test_clip_labels.csv`: **36 vehicles in 11 clips** - **1 errors, 0 warnings**. Labels were not modified.

- in_registry = no: 27 (need >= 2)
- cross-camera groups spanning >= 2 clips: none (need >= 1)
- readability: {'full': 11, 'partial': 7, 'none': 18}
- types: {'SUV': 9, 'auto_rickshaw': 5, 'car': 15, 'motorcycle': 4, 'scooter': 1, 'truck': 2}

| Severity | Vehicle / group | Issue |
|---|---|---|
| error | (coverage) | no cross-camera group spanning 2 clips; the spec requires >= 1 |
