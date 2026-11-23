# TRACEVISION AI — Local UI Setup Report

**Date:** 2026-11-23 · **Machine:** Windows 11, GeForce MX130 2 GB, no CUDA PyTorch

## Status at a glance
| Area | Status |
|---|---|
| UI / backend (FastAPI server, pages, routes) | **Working**. The server responds on 127.0.0.1:8000 |
| Stored-result demo (11 clips: dashboard, viewer, HTML/PDF reports) | **Working**, with gaps listed in §14 |
| Live AI inference (upload → analyse) | **Unavailable on this laptop.** Disabled on purpose in UI-only mode; uploads return HTTP 503 with a clear message |

## 1. Repository
`C:\Users\PC-01\trace_vision_nebula`. `tracevision/api.py` and `tracevision/static/viewer.html` are present. The incomplete copy in `C:\Users\PC-01\hackasol\` was not used.
Git state is unchanged since the audit: `.git/index` is still missing, so `git status` shows all files as deleted. That is not caused by this setup. See CURRENT_PROJECT_AUDIT.md §2 for the fix.

## 2. Python
Python **3.13.5** (`C:\Users\PC-01\AppData\Local\Programs\Python\Python313\python.exe`). Python 3.14.3 (default) and 3.10.0 are also installed. 3.10 can also run the UI with no installs.

## 3. Virtual environment
`C:\Users\PC-01\trace_vision_nebula\.venv`, created with `py -3.13 -m venv .venv`. It is already in `.gitignore`. Global packages were not modified.

## 4. Dependencies already present
There is no `requirements.txt` or `pyproject.toml`, and no frontend build step: the UI is inline HTML/JS served by FastAPI, with no npm and no CDN. The global Python 3.13 already had opencv 5.1, jinja2, numpy and pandas. These are not used in UI-only mode and are not visible inside the venv.

## 5. Dependencies installed (into `.venv` only)
`fastapi 0.165.0`, `uvicorn 0.54.0`, `python-multipart`, `pyyaml 6.0.4`, plus their sub-dependencies (starlette, pydantic, and so on).
Not installed, because they aren't needed to serve stored results: torch, ultralytics, paddle, open_clip, rapidfuzz, reportlab. No models or datasets were downloaded.

## 6. Startup command
```powershell
cd C:\Users\PC-01\trace_vision_nebula
$env:TRACEVISION_UI_ONLY = "1"
.\.venv\Scripts\python.exe -m tracevision.api
```
Entry point: `tracevision/api.py` → `main()` → `uvicorn.run(app, host="127.0.0.1", port=8000)`.

## 7. Server status
Running. Log line: `Uvicorn running on http://127.0.0.1:8000`. No model loading was attempted.

## 8–11. URLs
| Page | URL |
|---|---|
| Dashboard / investigator home (upload form and list of stored clips) | http://127.0.0.1:8000/ |
| API docs (Swagger) | http://127.0.0.1:8000/docs |
| Video viewer (stored clip) | http://127.0.0.1:8000/viewer/runs/clip03 (clip01–clip11) |
| HTML report | http://127.0.0.1:8000/runs/clip03/report |
| PDF report | http://127.0.0.1:8000/runs/clip03/report.pdf |
| Raw result | http://127.0.0.1:8000/data/runs/clip03/result.json |

The app has no separate "dashboard" or "vehicle search" page. The home page is the investigator interface. Per-vehicle results, with plate reads, top-5 candidates and the decision, appear in the viewer side panel and in the reports.

## 12. Pages tested
**HTTP checks (automated):**
- All 33 links on the home page return 200: 11 viewers, 11 HTML reports and 11 PDFs.
- `/docs` and `/openapi.json` return 200.
- `result.json` returns 200 for all 11 clips.
- Video returns 206 (seekable) for clip01–09.
- Upload is refused with 503 and the UI-only message.

**Browser:** the dashboard and `/viewer/runs/clip03` were opened in your default browser. The server log confirms the browser loaded both pages and that the viewer's JavaScript fetched `result.json`, `files` and the video. The only 404 was `/favicon.ico`.

## 13. Not tested
- **I did not see the rendered pages myself.** No browser-automation tool was available, so layout, the JS console, live-playback mode and interactions were not checked visually.
- Swagger UI's own assets load from a CDN in the browser. Only the HTML shell was checked.

## 14. Remaining frontend issues
1. **No plate or vehicle crop images** in the viewer for any clip (`/files` returns `[]`), because `runs/**/vehicles/` is git-ignored. The viewer shows blank space instead. Fix: re-run the pipeline on the GPU machine, or commit or share the crops.
2. **clip10 and clip11 have no video file** (Pexels clips, not in the repo). The viewer's player stays blank and there's no "video unavailable" message.
3. No favicon (cosmetic 404).
4. The upload form is still visible in UI-only mode. Uploading shows "Upload failed: … UI-only mode …". It's honest, but the form could be hidden or disabled in that mode.
5. Startup warning: `on_event` is deprecated in FastAPI 0.165 (harmless).
6. A PowerShell quirk: when stderr is redirected, PowerShell shows that warning as a red `NativeCommandError`. It isn't an error.

## 15. Files modified
- `tracevision/api.py` (small, opt-in change): `import os`, plus a `TRACEVISION_UI_ONLY` env flag. When it is `1`, the startup hook doesn't start the model thread, the home page says *"Live analysis is disabled (UI-only mode): models are not loaded, stored results only."*, and `POST /jobs` returns 503. **Without the flag, behaviour is unchanged.** No routes, response shapes or algorithms were changed.
- New: `.venv/` (git-ignored) and `LOCAL_UI_SETUP_REPORT.md`.

## Stop / restart
- **Stop:** press Ctrl+C in the terminal running the server. Or run `Get-NetTCPConnection -LocalPort 8000 -State Listen | % { Stop-Process -Id $_.OwningProcess }`.
- **Restart:** run the three commands in §6, then open http://127.0.0.1:8000/.
