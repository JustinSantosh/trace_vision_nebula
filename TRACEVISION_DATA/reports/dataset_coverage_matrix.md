# Dataset Coverage Matrix (Phase 0A, 2026-11-22)

Status legend: Ready · Partial · Missing · Blocked. Nothing is marked Ready, because no input is present locally.

| Requirement | Data source | Status | Evaluation method | Notes |
|---|---|---|---|---|
| Vehicle detection | UVH-26 model + test clips | Partial | Manual check of the first-frame vehicle boxes against detections on the labelled clips | The model is available (YOLOv11-S, 57 MB, not gated). There are no clips yet. |
| Vehicle type | UVH-26 + labelled clips | Partial | Per-class accuracy against hand-labelled `vehicle_type` | UVH-26 uses 13 classes (Hatchback, Sedan, SUV, MUV, Bus, Truck, Three-wheeler, Two-wheeler, LCV, Mini-bus, Tempo-traveller, Bicycle, Van). The model card says 14 classes, which is unresolved. Two-wheeler cannot be split into motorcycle and scooter, so it maps to `motorcycle/scooter` as ambiguous. |
| Indian plate detection | D1 | **Blocked** | mAP50 on the official D1 test split | The D1 repo contains no images or labels. A replacement dataset is needed. |
| Indian OCR | Awiros + D2 test split | **Blocked** for the benchmark, Partial for the smoke test | CER and exact-plate accuracy | The D2 repo contains no data. Awiros can be smoke-tested on its 10 sample crops. Fallback: crops from our own clips. |
| Multi-frame recovery | Test clips + optional UFPR | Missing | Per-plate exact match and CER after aggregation, compared with the single best frame | Needs labelled clips. UFPR-ALPR is gated and takes days to obtain. |
| Vehicle colour | Heuristic + labelled clips | Missing | Accuracy against hand labels, with the `unknown` rate reported | Needs labelled clips. |
| Registry ranking | Synthetic registry | Missing | Top-1 and top-5 against `registry_test_cases.csv` | Generated after labels exist (Phase 0F). |
| No-match handling | Synthetic negative cases | Missing | Rejection rate for `in_registry = no` vehicles | Needs at least 2 no-match vehicles in the labelled clips. |
| Cross-camera tracking | Two manually associated clips | Missing | Association accuracy against `cross_camera_ground_truth.csv` | Needs at least 1 vehicle seen in 2 clips. This is the hardest clip to find in stock footage, so it may need to be filmed by the team. |
| Make/model (bonus) | Optional CLIP experiment | Missing | Qualitative only | No verified labels. Make no claims about make or model. |
