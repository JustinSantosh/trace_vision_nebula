# Baseline (before any change in this audit)

Measured 2026-11-23 on this machine, branch `ui-redesign`, before editing.

## Environment
| Item | Found | Note |
|---|---|---|
| Python | 3.13.5 in `.venv` | the only Python on PATH for the project |
| torch | **2.15.0+cpu** | CUDA build not installed in this venv |
| GPU | **NVIDIA GeForce MX130, 2 GB** | not the RTX 3050 the README benchmarks were run on; unusable by the CPU torch build |
| Node | 24.18.0 | frontend is static HTML/JS served by FastAPI; no package manager, no build |
| Weights present | UVH-26 YOLOv11-S, YOLOv8n (COCO), plate YOLOv8n, Awiros OCR, VCoR probe v1, CLIP (cached) | |

## Git state
- HEAD `880e85b` **contains merge-conflict markers** in `frontend/index.html`, `frontend/assets/app.js`, `frontend/assets/styles.css`. The working copy is resolved.
- 10 modified and 25 untracked files of earlier work (parking/e-challan modules, VCoR probe scripts and reports). All preserved.

## Tests
| Suite | Result |
|---|---|
| `pytest tests` | **73 passed**, 0 failed (33 s) |
| `node --test frontend/tests/explain.test.js` | **11 passed** |
| `node --test frontend/tests/` (command in the test header) | fails on Node 24: a directory argument is not accepted. Tooling note, not a test failure |

## Stored-result evaluation (from `TRACEVISION_DATA/reports/p6_evaluation_baseline.json`, not re-run)
14/15 registered vehicles matched · 0/46 false confident matches · 0/252 wrong plate characters · 61/67 detected and tracked · 5/5 cross-camera groups. Re-running the full pipeline over all 19 clips was not done: on this CPU-only machine it would take far longer than the original RTX 3050 runs and would not change these stored figures (no detection/OCR code was modified).

## Colour (VCoR splits, from the shipped probe config)
Zero-shot CLIP test 60.1% · probe v1 test 60.8% (top-2 74.9%).

## Workflow baseline (manual API/UI inspection)
- Parking UI: "Authorize Towing" failed (wrong state name), "Send Warning" changed nothing, errors silent.
- E-challan UI: "Reject Draft" hit a missing route (405).
- No way to open a parking case or draft an e-challan from the UI; the only cases shown were 16 left behind by test runs.

## Blockers to a full baseline
- No CUDA torch → GPU latency/VRAM figures cannot be measured here.
- No labelled tracking (MOT) data → no ID-switch/MOTA figures.
- No labelled plate-detection data from CCTV beyond the Roboflow test split.
- clip10, clip11 videos are not on disk (stock footage not in Git), so CCTV colour checks cover 62 of 67 vehicles.
