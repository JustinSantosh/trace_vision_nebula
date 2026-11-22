# Health check: everything built so far (2026-11-23)

Asked for by the owner before P4: "check once again if all the things are working till now properly". Every check below **actually ran**. Script outputs went to a scratch folder, so nothing in the repo was overwritten by the checks themselves.

## Result: ✅ everything works. 3 small fixes made, 2 open items (expected)

| Area | Check | Result |
|---|---|---|
| **Git** | Clean working tree, in sync with GitHub, other session's work committed (`9c8921b`, `b9a034d`, `21d641d`) | ✅ |
| **Plate data** | processed 2,069 / 336 / 169 images = labels; boxes 2,084 / 339 / 171; `name_map` 2,574 rows; leakage-free test 106; raw 5,152 files | ✅ matches the P0B report |
| **OCR set** | 1,709 rows, 965 primary, 0 missing crop files | ✅ |
| **Clips** | 11 files ↔ 11 `clips.csv` rows; real frame counts and durations match `clips.csv` (to within 0.04 s); sources and licences filled | ✅ |
| **Frames** | `frames_index.csv` matches the trimmed clips; no frames past any clip's end; every frame file is indexed | ✅ |
| **Contact sheets** | **6 were stale** (made before the trim, so they showed the doubled footage) | 🔧 **Regenerated** for clip01, 02, 04, 05, 06, 08 |
| **Registry** | 334 rows, unique plates, all `synthetic = true`, spec columns; every expected ID in the 124 cases exists; **regenerating gives byte-identical registry and cases** | ✅ reproducible |
| **Labels** | `test_clip_labels.csv`: 51 vehicles in 11 clips, owner-verified (commit `21d641d`). Validator: **0 field errors**, 0 warnings. 1 coverage error: no cross-camera group yet | ✅ (cross-camera pair is planned: A6) |
| **10 Phase 0 scripts** | Each run on a small sample: inspect, validate_plate, prepare_plate, build_ocr, awiros (GPU), extract_frames, template, validate_labels, degrade, registry | ✅ **10/10 pass** |
| **Awiros OCR** | GPU sample of 20: 80% exact, CER 3.2%, **14 ms median** (same as P0C) | ✅ |
| **torch + Paddle** | Two-process design: YOLO in the main process, OCR worker at about 15 ms per crop, YOLO still fine afterwards | ✅ |
| **Model files** | UVH-26 sha256 `12dbeb8f…` ✅, plate detector `3f8e0009…` ✅, UVH-26 loads with 14 classes | ✅ |
| **Plate detector** | Re-evaluated: leakage-free mAP50 **0.9945** / mAP50-95 **0.754**, identical to P2 | ✅ reproducible |
| **P2 on trimmed clips** | clip01/02/08: median plate height 14 / 9.5 / 14 px (was 13 / 9 / 13 on the doubled versions) | ✅ conclusions unchanged; note added to the P2 report |
| **P3 code** | 26 unit tests pass; calibration picks the same thresholds (67.5 / 5) with holdout 62/62 | ✅ |
| **Calibration report** | **Wasn't byte-reproducible:** the "before calibration" field recorded whatever `config.yaml` held at run time (75, then 67.5) | 🔧 **Fixed** (pinned to the original design values); now identical on rerun |
| **Docs** | All links and referenced file paths in the top-level docs, reports and the labelling guide exist | ✅ 0 broken |

## Open (known, not failures)
1. **No cross-camera pair yet (A6).** The owner will film one car from 2 positions. Until then the label validator reports 1 coverage error, which is expected.
2. **Label balance:** 42 of 51 labelled vehicles are `in_registry = no`, so only 9 vehicles can test a positive match on real clips. That's fine for no-match testing. More `yes` vehicles with readable plates would strengthen the match evaluation (P6).

## Lessons recorded
- On Windows, anything that starts PyTorch data loaders (training or `model.val`) must run from a `.py` file, not from stdin, or it hangs with the GPU idle. It happened twice (P2 and this check), so use the scripts in `scripts/smoke/`.
