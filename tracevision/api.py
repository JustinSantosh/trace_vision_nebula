"""Investigator app (P5): upload a clip -> progress -> report (HTML + PDF) and result.json.

    python -m tracevision.api            # then open http://127.0.0.1:8000

Endpoints
  GET  /                      upload page + list of processed clips
  POST /jobs                  multipart upload (field "video") -> {"job_id": ...}
  GET  /jobs/{id}             status JSON (queued | running | done | error)
  GET  /jobs/{id}/report      HTML report      GET /jobs/{id}/report.pdf     GET /jobs/{id}/result
  GET  /runs/{clip}/report    report of a clip already in runs/ (demo)
One background worker processes jobs in order on the local GPU. Models load once at start-up.
"""
from __future__ import annotations

import queue
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from . import ROOT
from .report import build

JOBS_DIR = ROOT / "runs" / "jobs"
RUNS = ROOT / "runs"
ALLOWED = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm"}
MAX_BYTES = 500 * 1024 * 1024

app = FastAPI(title="TRACEVISION AI")
jobs: dict[str, dict] = {}
q: "queue.Queue[str]" = queue.Queue()
state = {"engine": None, "ready": False, "error": None}


def _worker():
    from .pipeline import Engine
    try:
        eng = Engine().__enter__()
        state.update(engine=eng, ready=True)
    except Exception as e:  # pragma: no cover - surfaced on the page
        state["error"] = repr(e)
        return
    while True:
        jid = q.get()
        job = jobs[jid]
        job.update(status="running", started=time.time())
        try:
            res = eng.run(job["video"], job["dir"])
            build(Path(job["dir"]), deliver=False)
            job.update(status="done", summary=res["summary"], timing=res["timing"], finished=time.time())
        except Exception as e:
            job.update(status="error", error=repr(e))


@app.on_event("startup")
def _start():
    threading.Thread(target=_worker, daemon=True).start()


PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TRACEVISION AI</title><style>
:root{--ink:#1f2933;--muted:#5f6b7a;--line:#d5dbe3;--bg:#fff;--accent:#1d4ed8}
@media (prefers-color-scheme: dark){:root{--ink:#e5e9f0;--muted:#a3adbb;--line:#3b4252;--bg:#14171c;--accent:#7aa2ff}}
body{font-family:Segoe UI,system-ui,sans-serif;color:var(--ink);background:var(--bg);max-width:820px;margin:0 auto;padding:16px}
.card{border:1px solid var(--line);border-radius:8px;padding:14px;margin:14px 0}button{background:var(--accent);color:#fff;border:0;border-radius:6px;padding:8px 14px;font-size:15px;cursor:pointer}
a{color:var(--accent)}.muted{color:var(--muted)}#status{margin-top:10px;font-weight:600}</style></head><body>
<h1>TRACEVISION AI</h1><div class="muted">Vehicle identification from CCTV / dashcam footage: plate read over many frames (unreadable characters shown as ?), type, colour, ranked registry candidates with reasons, or "no confident match".</div>
<div class="card"><h3>Analyse a clip</h3><div id="eng" class="muted">MODEL_STATE</div>
<input type="file" id="f" accept="video/*"> <button onclick="go()">Upload and analyse</button><div id="status"></div></div>
<div class="card"><h3>Processed test clips</h3>RUNS</div>
<script>
async function go(){const f=document.getElementById('f').files[0];if(!f){alert('Choose a video first');return}
const s=document.getElementById('status');s.textContent='Uploading…';const fd=new FormData();fd.append('video',f);
const r=await fetch('/jobs',{method:'POST',body:fd});if(!r.ok){s.textContent='Upload failed: '+(await r.text());return}
const {job_id}=await r.json();poll(job_id)}
async function poll(id){const s=document.getElementById('status');const r=await (await fetch('/jobs/'+id)).json();
if(r.status==='done'){s.innerHTML='Done in '+r.timing.total_s+' s: '+r.summary.vehicles_after_relink+' vehicles. <a href="/jobs/'+id+'/report">Open report</a> · <a href="/jobs/'+id+'/report.pdf">PDF</a> · <a href="/jobs/'+id+'/result">JSON</a>';return}
if(r.status==='error'){s.textContent='Error: '+r.error;return}
s.textContent=(r.status==='queued'?'Queued (position '+r.position+')…':'Analysing… ')+(r.elapsed_s?Math.round(r.elapsed_s)+' s':'');setTimeout(()=>poll(id),1500)}
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    runs = sorted(p.parent.name for p in RUNS.glob("clip*/report.html"))
    links = " · ".join(f'<a href="/runs/{c}/report">{c}</a> (<a href="/runs/{c}/report.pdf">pdf</a>)' for c in runs) or "none yet"
    st = "Models ready." if state["ready"] else (f"Model start-up failed: {state['error']}" if state["error"] else "Loading models… (about 20 s)")
    return PAGE.replace("RUNS", links).replace("MODEL_STATE", st)


@app.post("/jobs")
async def create_job(video: UploadFile = File(...)):
    ext = Path(video.filename or "").suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(400, f"unsupported file type {ext!r}; use one of {sorted(ALLOWED)}")
    jid = uuid.uuid4().hex[:12]
    d = JOBS_DIR / jid
    d.mkdir(parents=True)
    dst = d / f"upload{ext}"
    size = 0
    with open(dst, "wb") as f:
        while chunk := await video.read(1 << 20):
            size += len(chunk)
            if size > MAX_BYTES:
                raise HTTPException(413, "file too large (max 500 MB)")
            f.write(chunk)
    jobs[jid] = {"status": "queued", "video": str(dst), "dir": str(d), "name": video.filename, "created": time.time()}
    q.put(jid)
    return {"job_id": jid}


def _job(jid):
    if jid not in jobs:
        raise HTTPException(404, "unknown job")
    return jobs[jid]


@app.get("/jobs/{jid}")
def job_status(jid: str):
    j = _job(jid)
    out = {k: v for k, v in j.items() if k in ("status", "name", "summary", "timing", "error")}
    if j["status"] == "queued":
        out["position"] = list(q.queue).index(jid) + 1 if jid in q.queue else 1
    if j["status"] == "running":
        out["elapsed_s"] = time.time() - j["started"]
    return JSONResponse(out)


def _file(d: Path, name: str, media=None):
    p = d / name
    if not p.exists():
        raise HTTPException(404, f"{name} not ready")
    return FileResponse(p, media_type=media)


@app.get("/jobs/{jid}/report", response_class=HTMLResponse)
def job_report(jid: str):
    return _file(Path(_job(jid)["dir"]), "report.html", "text/html")


@app.get("/jobs/{jid}/report.pdf")
def job_pdf(jid: str):
    return _file(Path(_job(jid)["dir"]), "report.pdf", "application/pdf")


@app.get("/jobs/{jid}/result")
def job_result(jid: str):
    return _file(Path(_job(jid)["dir"]), "result.json", "application/json")


@app.get("/runs/{clip}/report", response_class=HTMLResponse)
def run_report(clip: str):
    if not clip.startswith("clip") or "/" in clip or "\\" in clip or ".." in clip:
        raise HTTPException(404)
    return _file(RUNS / clip, "report.html", "text/html")


@app.get("/runs/{clip}/report.pdf")
def run_pdf(clip: str):
    if not clip.startswith("clip") or "/" in clip or "\\" in clip or ".." in clip:
        raise HTTPException(404)
    return _file(RUNS / clip, "report.pdf", "application/pdf")


def main():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
