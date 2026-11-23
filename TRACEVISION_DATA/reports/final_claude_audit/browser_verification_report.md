# Browser verification

**How:** headless Google Chrome on this machine, driven two ways: (1) `--screenshot` captures per route; (2) a small
DevTools-protocol script (Node 24 WebSocket) that navigates, clicks, types, reads the DOM, and records console
errors, uncaught exceptions, HTTP ≥ 400 responses and failed network loads. Screenshots were inspected visually.
No interactive (headed) browser control was available in this session.

Server: `.venv/Scripts/python.exe -m uvicorn tracevision.api:app --host 127.0.0.1 --port 8001` (full engine;
status reached "Engine ready" on CPU). Port 8000 was already held by an older `python -m tracevision.api` process
started before this audit (old code); it was left running.

## Routes
| Route | HTTP | Rendered | Console / network errors |
|---|---|---|---|
| `/#` Cases | 200 | 19 cases, totals, outcome tags, "Engine ready" | none |
| `/#case/runs/clip03` | 200 | video with tracked boxes, vehicle list, per-character plate evidence, frame reads, registry match | none |
| `/#crosscam` | 200 | pair selector, per-camera details, combined table, link reasons | none (videos black in headless capture until buffered) |
| `/#performance` | 200 | 7 headline metrics, robustness bars, data-driven colour table | none |
| `/#enforcement` (1440 px and 390 px) | 200 | tabs, officer field, banner, wrong-side summary, registry lookup | none; no horizontal overflow at 390 px |
| `/viewer/runs/clip03` | 200 | legacy viewer page | none |
| 13 API routes (`/api/overview`, `/api/review`, `/api/violations`, `/api/enforcement/meta`, `/api/colour/model_info`, parking/echallan lists, audit, intel meta, scan, result/report files) | all 200, 5–240 ms | — | — |

## Interactions verified by clicking
1. Enforcement → Parking tab → open case row → side panel shows steps, evidence link, owner warning, allowed next moves only.
2. "Record vehicle towed" with no reason → message "Write the reason for this decision in the note field first."; nothing sent.
3. Typed officer name, wrote a reason, clicked again → case moved to **Towed**; only "Close case" remains.
4. "Open a parking case" → form lists 19 stored analyses and that clip's vehicles; zone-scan result shown.
5. E-challans tab → case row → steps Draft/Verified/Approved & issued/Paid, evidence copied from analysis, dispute outcome, simulated payment reference.
6. "Draft an e-challan" → vehicle list contains only confident matches (e.g. `T3 · DL3CCK2475`); 8 violation categories with fines.
7. Audit log tab renders.

**Result: 0 console errors, 0 uncaught exceptions, 0 failed requests across all steps.**

## Bug found only by the live run
`warning_sent` returned HTTP 500 for a case opened from an officer observation (no measured dwell). Fixed, regression
test added, server restarted, re-verified (execution log #14).

## Records created during verification
Attributed to officer `AUDIT_DEMO` so they are easy to recognise: parking case `PRK-20261123-B5E3E6` (taken to
*Towed*) and e-challan `ECH-20261123-A48C77` (taken to *Paid (simulated)* through a dismissed dispute), both on
clip03 vehicle T1, plus one analysis job from uploading clip13. They live in `runs/` (git-ignored) and can be
removed by moving `runs/enforcement/*.json` aside.
