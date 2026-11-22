# P5: Investigator app and per-clip reports

**Date:** 2026-11-23 · **Approved by the owner:** "approve all phases remaining" · **No new installs were needed**: fastapi 0.115, uvicorn 0.32, jinja2 3.1, python-multipart and reportlab were already present.

## Report: `tracevision/report.py`
```powershell
python -m tracevision.report              # all runs/clip*/ -> report.html + report.pdf, PDF also copied to evaluation/reports/
python -m tracevision.pipeline --report   # run the pipeline and build the reports in one go
```
Each clip report contains everything the problem statement asks for:
- clip info (camera type, resolution, timing)
- for every vehicle with plate evidence or a candidate:
  - **the frames used** (vehicle crop + plate crops)
  - **the characters read per frame, with OCR confidence** (colour-coded grid)
  - **the fused plate**, with `?` in red for unreadable positions
  - per-position confidence and vote share
  - **type and colour** with their confidence
  - the **decision and its reason**
  - the **top 5 registry candidates with match score and reasons**
- all other tracked vehicles in a compact table, with why there's no plate (too small, not detected, or belongs to an overlapping vehicle)
- the "match score is not a probability" and "synthetic registry" disclaimers on every report

**Deliverable:** `TRACEVISION_DATA/evaluation/reports/clip01_report.pdf` … `clip11_report.pdf` (41–431 KB each; images are downscaled to keep 4K clips small).

## App: `tracevision/api.py`
```powershell
python -m tracevision.api     # open http://127.0.0.1:8000
```
- **Upload page:** pick a video, then "Upload and analyse". It shows live progress (queued / analysing / done), then links to the HTML report, PDF and JSON. The page also lists the already-processed test clips.
- **Endpoints:** `POST /jobs`, `GET /jobs/{id}`, `/jobs/{id}/report`, `/report.pdf`, `/result`, `/runs/{clip}/report`.
- Models load **once** at start-up (OCR worker process first, then YOLO). A single background worker processes jobs in order on the GPU. Uploads are checked: only video extensions, max 500 MB.

## Tested (actually ran)
| Check | Result |
|---|---|
| Server start, models ready | ✅ |
| Upload clip02 → queued → running → done | ✅ 7.4 s, 31 vehicles (same as the batch run) |
| Report HTML / PDF / JSON download | ✅ 200 (6 KB / 44 KB / 33 KB) |
| Wrong file type | ✅ rejected (400) |
| Unknown job, path traversal in `/runs/..` | ✅ 404 |
| All 11 PDF reports built and checked visually (clip03, clip11) | ✅ |

## Limits
- Single user, local only (`127.0.0.1`), jobs kept in memory (a restart forgets job IDs; files stay in `runs/jobs/`).
- The UI is deliberately simple: upload, progress, report. The report itself is the investigator view.
