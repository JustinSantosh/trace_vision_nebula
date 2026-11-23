# Test-label validation

`TRACEVISION_DATA/evaluation/test_clip_labels.csv`: **67 vehicles in 19 clips** - **0 errors, 6 warnings**. Labels were not modified.

- in_registry = no: 46 (need >= 2)
- cross-camera groups spanning >= 2 clips: ['X1', 'X2', 'X3', 'X5', 'X4', 'X6', 'X7'] (need >= 1)
- readability: {'full': 19, 'partial': 12, 'none': 36}
- types: {'SUV': 16, 'auto_rickshaw': 6, 'bicycle': 1, 'car': 27, 'motorcycle': 9, 'scooter': 5, 'truck': 3}

| Severity | Vehicle / group | Issue |
|---|---|---|
| warning | clip14_v01 | in_registry = yes but the full plate is unknown (has `?` / blank) and registry_plate_full is empty - it cannot be seeded into the registry |
| warning | clip15_v01 | in_registry = yes but the full plate is unknown (has `?` / blank) and registry_plate_full is empty - it cannot be seeded into the registry |
| warning | clip16_v01 | in_registry = yes but the full plate is unknown (has `?` / blank) and registry_plate_full is empty - it cannot be seeded into the registry |
| warning | clip17_v01 | in_registry = yes but the full plate is unknown (has `?` / blank) and registry_plate_full is empty - it cannot be seeded into the registry |
| warning | clip18_v01 | in_registry = yes but the full plate is unknown (has `?` / blank) and registry_plate_full is empty - it cannot be seeded into the registry |
| warning | clip19_v01 | in_registry = yes but the full plate is unknown (has `?` / blank) and registry_plate_full is empty - it cannot be seeded into the registry |
