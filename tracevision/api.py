"""Investigator app (P5): upload a clip -> progress -> report (HTML + PDF) and result.json.

    python -m tracevision.api            # then open http://127.0.0.1:8000

Endpoints
  GET  /                      investigator workspace
  GET  /api/overview          engine state, stored clips, and evaluation headlines
  GET  /api/review            directional cross-camera, evaluation, and robustness data
  POST /jobs                  multipart upload (field "video") -> {"job_id": ...}
  GET  /jobs/{id}             status JSON (queued | running | done | error)
  GET  /jobs/{id}/report      HTML report      GET /jobs/{id}/report.pdf     GET /jobs/{id}/result
  GET  /runs/{clip}/report    report of a clip already in runs/ (demo)
  GET  /data/{kind}/{id}/violations   wrong-side driving check for one run (fixed cameras only)
  GET  /api/violations        all suspected violations + review status + simulated challans raised
  POST /api/violations/review officer confirms / rejects a suspected violation
  GET  /api/intel/meta        roles and lookup reasons       GET /api/intel/{registration}   role-gated vehicle record
  GET  /api/audit             lookup + review audit log (officer)
Vehicle records and challans are SYNTHETIC demo data (intel.py). Roles come from the X-TV-Role header and are not
authenticated: this demonstrates the access model, it is not access control.
One background worker processes jobs in order on the local GPU. Models load once at start-up.
"""
from __future__ import annotations

import json
import os
import queue
import re
import threading
import time
import uuid
from pathlib import Path

from fastapi import Body, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import ROOT, intel, violations
from .report import build

FRONTEND_DIR = ROOT / "frontend"
JOBS_DIR = ROOT / "runs" / "jobs"
RUNS = ROOT / "runs"
ALLOWED = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm"}
MAX_BYTES = 500 * 1024 * 1024

app = FastAPI(title="TRACEVISION AI")
app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR / "assets"), name="frontend")
jobs: dict[str, dict] = {}
q: "queue.Queue[str]" = queue.Queue()
state = {"engine": None, "ready": False, "error": None}
# UI-only mode (TRACEVISION_UI_ONLY=1): no model is imported or loaded and no new clip is analysed; stored results,
# reports and the viewer are served as usual. For machines without the GPU / model stack (e.g. a CPU-only laptop).
UI_ONLY = os.environ.get("TRACEVISION_UI_ONLY") == "1"
UI_ONLY_MSG = "Live analysis is disabled (UI-only mode): models are not loaded; stored results only."


def _worker():
    try:
        from .pipeline import Engine
        eng = Engine().__enter__()
        state.update(engine=eng, ready=True)
    except Exception as e:  # pragma: no cover - surfaced on the page
        error = repr(e)
        state.update(engine=None, ready=False, error=error)
        while True:
            try:
                jid = q.get_nowait()
            except queue.Empty:
                break
            if jid in jobs:
                jobs[jid].update(status="error", phase="error", failed_at="startup",
                                  error=f"Analysis engine could not start: {error}")
        return
    while True:
        jid = q.get()
        job = jobs[jid]
        job.update(status="running", phase="analysis", started=time.time())
        try:
            res = eng.run(job["video"], job["dir"])
            job.update(phase="report")
            build(Path(job["dir"]), deliver=False)
            job.update(status="done", phase="complete", summary=res["summary"], timing=res["timing"], finished=time.time())
        except Exception as e:
            job.update(status="error", phase="error", failed_at=job.get("phase", "analysis"), error=repr(e))


@app.on_event("startup")
def _start():
    if UI_ONLY:
        return
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
if(r.status==='done'){s.innerHTML='Done in '+r.timing.total_s+' s: '+r.summary.vehicles_after_relink+' vehicles. <a href="/viewer/jobs/'+id+'">▶ Open video viewer</a> · <a href="/jobs/'+id+'/report">Open report</a> · <a href="/jobs/'+id+'/report.pdf">PDF</a> · <a href="/jobs/'+id+'/result">JSON</a>';return}
if(r.status==='error'){s.textContent='Error: '+r.error;return}
s.textContent=(r.status==='queued'?'Queued (position '+r.position+')…':'Analysing… ')+(r.elapsed_s?Math.round(r.elapsed_s)+' s':'');setTimeout(()=>poll(id),1500)}
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse((FRONTEND_DIR / "index.html").read_text(encoding="utf-8"))


def _evaluation_headlines():
    """Headline metrics for the dashboard.

    Primary source: p6_evaluation_baseline.json, written by `python -m tracevision.evaluate` from runs/*/result.json and
    the owner-verified labels. The Markdown report is only a fallback: it holds several historical tables and is
    edited by hand, so parsing it can pick up superseded figures.
    """
    from_json = _evaluation_headlines_json()
    return from_json if from_json["metrics"] else _evaluation_headlines_markdown()


def _evaluation_headlines_json():
    path = ROOT / "TRACEVISION_DATA" / "reports" / "p6_evaluation_baseline.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        summary = data["summary"]["all"]
    except (OSError, ValueError, KeyError, TypeError):
        return {"source": path.name, "clip_count": None, "metrics": []}

    def value(key):
        raw = summary.get(key)
        return str(raw).split(" (")[0] if raw not in (None, "", "n/a") else None   # "14/15 (93%)" -> "14/15"

    wanted = [
        ("registered_matches", "Registered vehicles matched", "registered_vehicles_matched_correctly"),
        ("false_confident_matches", "False confident matches", "unregistered_with_false_confident_match"),
        ("wrong_plate_characters", "Wrong plate characters", "plate_chars_WRONG"),
        ("detected_and_tracked", "Detected and tracked", "detected_and_tracked"),
        ("plate_characters_correct", "Plate characters read correctly", "plate_chars_correct"),
        ("type_compatible", "Vehicle type compatible", "type_compatible"),
    ]
    per_vehicle = data.get("per_vehicle") if isinstance(data.get("per_vehicle"), list) else []
    clips = {str(row.get("clip_id")) for row in per_vehicle if isinstance(row, dict) and row.get("clip_id")}
    scope = f"{len(clips)} clips · {summary.get('labelled_vehicles')} labelled vehicles" if clips else "labelled set"

    def detail(key):
        pct = re.search(r"\((\d+%)\)", str(summary.get(key)))
        return f"{pct.group(1)} · {scope}" if pct else scope

    metrics = [{"key": k, "label": label, "value": value(src), "detail": detail(src)}
               for k, label, src in wanted if value(src) is not None]
    return {"source": path.name, "clip_count": len(clips) or None, "labelled_vehicles": summary.get("labelled_vehicles"),
            "metrics": metrics}


def _evaluation_headlines_markdown():
    path = ROOT / "TRACEVISION_DATA" / "reports" / "p6_evaluation.md"
    if not path.exists():
        return {"source": path.name, "clip_count": None, "metrics": []}

    lines = path.read_text(encoding="utf-8").splitlines()
    report_header = None
    for i, line in enumerate(lines):
        if line.startswith("|") and re.search(r"\*\*\d+\s+clips\*\*", line):
            report_header = i
    if report_header is None:
        return {"source": path.name, "clip_count": None, "metrics": []}

    header_match = re.search(r"\*\*(\d+)\s+clips\*\*", lines[report_header])
    clip_count = int(header_match.group(1)) if header_match else None
    wanted = {
        "Registered matched": ("registered_matches", "Registered vehicles matched"),
        "False confident matches (unregistered)": ("false_confident_matches", "False confident matches"),
        "Wrong plate characters": ("wrong_plate_characters", "Wrong plate characters"),
        "Detected and tracked at the labelled frame": ("detected_and_tracked", "Detected and tracked"),
    }
    values = {}
    for line in lines[report_header + 1:]:
        if not line.startswith("|"):
            if values:
                break
            continue
        cells = [re.sub(r"[*" + chr(96) + "]", "", cell).strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        label = cells[0]
        if label in wanted:
            key, title = wanted[label]
            values[key] = {"key": key, "label": title, "value": cells[-1]}
    order = ("registered_matches", "false_confident_matches", "wrong_plate_characters", "detected_and_tracked")
    return {"source": path.name, "clip_count": clip_count, "metrics": [values[k] for k in order if k in values]}


def _overview_data():
    clips = []
    result_files = list(RUNS.glob("clip*/result.json"))
    result_files.sort(key=lambda p: (int(re.search(r"\d+", p.parent.name).group()) if re.search(r"\d+", p.parent.name) else 0, p.parent.name))
    for result_path in result_files:
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        clip_id = str(result.get("clip_id") or result_path.parent.name)
        if not re.fullmatch(r"clip\d+", clip_id):
            continue
        vehicles = result.get("vehicles") if isinstance(result.get("vehicles"), list) else []
        decisions = result.get("summary", {}).get("decisions", {})
        video_path = ROOT / "TRACEVISION_DATA" / "raw" / "test_videos" / f"{clip_id}.mp4"
        clips.append({
            "clip_id": clip_id,
            "camera_type": result.get("camera_type") or "unknown",
            "vehicle_count": len(vehicles),
            "match_count": int(decisions.get("match", 0)),
            "no_match_count": int(decisions.get("no_confident_match", 0)),
            "ambiguous_count": int(decisions.get("ambiguous", 0)),
            "plates_read": result.get("summary", {}).get("plates_read"),
            "processed_at": result.get("processed_at"),
            "has_video": video_path.exists(),
            "has_report": (result_path.parent / "report.html").exists(),
            "has_report_pdf": (result_path.parent / "report.pdf").exists(),
        })

    crosscam_path = ROOT / "TRACEVISION_DATA" / "reports" / "crosscam_evaluation.json"
    try:
        crosscam = json.loads(crosscam_path.read_text(encoding="utf-8")) if crosscam_path.exists() else None
    except (OSError, json.JSONDecodeError):
        crosscam = None
    if UI_ONLY:
        engine = {"status": "disabled", "error": None, "message": UI_ONLY_MSG}
    else:
        engine = {"status": "ready" if state["ready"] else ("error" if state["error"] else "starting"), "error": state["error"]}
    return {
        "engine": engine,
        "clips": clips,
        "evaluation": _evaluation_headlines(),
        "crosscam_evaluation": crosscam.get("summary") if isinstance(crosscam, dict) else None,
        "limits": {"allowed_extensions": sorted(ALLOWED), "max_bytes": MAX_BYTES},
    }


@app.get("/api/overview")
def api_overview():
    return JSONResponse(_overview_data())


def _review_data():
    pairs = {}
    crosscam_dir = RUNS / "crosscam"
    for path in sorted(crosscam_dir.glob("*.json")) if crosscam_dir.exists() else []:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        clip_a = document.get("clip_a") if isinstance(document, dict) else None
        clip_b = document.get("clip_b") if isinstance(document, dict) else None
        if not (isinstance(clip_a, str) and re.fullmatch(r"clip\d+", clip_a)
                and isinstance(clip_b, str) and re.fullmatch(r"clip\d+", clip_b)
                and isinstance(document.get("links"), list)):
            continue
        key = tuple(sorted((clip_a, clip_b), key=lambda clip: int(re.search(r"\d+", clip).group())))
        pair = pairs.setdefault(key, {"clip_a": key[0], "clip_b": key[1], "directions": []})
        # Owner-declared same-scene pairs also carry the joint links (M16) that crosscam_evaluation.json scores.
        if isinstance(document.get("pair_linking"), dict) and isinstance(document["pair_linking"].get("links"), list):
            pair["same_scene"] = document["pair_linking"]
        pair["directions"].append({
            "source_clip": clip_a,
            "target_clip": clip_b,
            "links": document["links"],
            "note": document.get("note"),
        })

    pair_list = sorted(pairs.values(), key=lambda pair: (
        int(re.search(r"\d+", pair["clip_a"]).group()),
        int(re.search(r"\d+", pair["clip_b"]).group()),
    ))
    for pair in pair_list:
        pair["directions"].sort(key=lambda direction: (
            int(re.search(r"\d+", direction["source_clip"]).group()),
            int(re.search(r"\d+", direction["target_clip"]).group()),
        ))

    reports = ROOT / "TRACEVISION_DATA" / "reports"
    try:
        crosscam = json.loads((reports / "crosscam_evaluation.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        crosscam = None
    try:
        robustness = json.loads((reports / "p6_robustness.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        robustness = None
    return {
        "crosscam_pairs": pair_list,
        "crosscam_evaluation": crosscam if isinstance(crosscam, dict) else None,
        "robustness": robustness if isinstance(robustness, dict) else None,
    }


@app.get("/api/review")
def api_review():
    return JSONResponse(_review_data())


@app.post("/jobs")
async def create_job(video: UploadFile = File(...)):
    if UI_ONLY:
        raise HTTPException(503, UI_ONLY_MSG)
    if state["error"]:
        raise HTTPException(503, "The analysis engine could not start. Stored results are still available.")
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
    (d / "name.txt").write_text(video.filename or "", encoding="utf-8")
    jobs[jid] = {"status": "queued", "phase": "queued", "video": str(dst), "dir": str(d), "name": video.filename, "created": time.time()}
    q.put(jid)
    return {"job_id": jid}


def _job(jid):
    if jid not in jobs:
        raise HTTPException(404, "unknown job")
    return jobs[jid]


@app.get("/jobs/{jid}")
def job_status(jid: str):
    j = _job(jid)
    out = {k: v for k, v in j.items() if k in ("status", "phase", "failed_at", "name", "summary", "timing", "error")}
    if j["status"] == "queued":
        out["position"] = list(q.queue).index(jid) + 1 if jid in q.queue else 1
    if j["status"] == "running":
        out["elapsed_s"] = time.time() - j["started"]
    return JSONResponse(out)


# ---------------------------------------------------------------- annotated video viewer
# /viewer/runs/clip03  or  /viewer/jobs/<job_id>: plays the clip with the tracked boxes drawn on it, and a side
# panel with each vehicle's picked frames (plate crops), per-frame reads, fused plate and ranked candidates.
VIEWER = Path(__file__).with_name("static") / "viewer.html"
_IMG = re.compile(r"^t\d+_(plate|vehicle)_f\d+\.jpg$")


def _run_dir(kind: str, rid: str) -> Path:
    if kind == "runs" and re.fullmatch(r"clip\d+", rid):
        d = RUNS / rid
    elif kind == "jobs" and re.fullmatch(r"[0-9a-f]{12}", rid):
        d = JOBS_DIR / rid
    else:
        raise HTTPException(404, "unknown run")
    if not (d / "result.json").exists():
        raise HTTPException(404, "no result yet for this run")
    return d


@app.get("/viewer/{kind}/{rid}", response_class=HTMLResponse)
def viewer(kind: str, rid: str):
    d = _run_dir(kind, rid)
    nf = d / "name.txt"  # original upload filename (jobs only)
    name = nf.read_text(encoding="utf-8").strip() if nf.exists() else rid
    name = re.sub(r"[^\w .()-]", "_", name)[:80]  # it is inserted into a JS string: keep it plain
    return VIEWER.read_text(encoding="utf-8").replace("__DATA__", f"/data/{kind}/{rid}").replace("__NAME__", name)


@app.get("/data/{kind}/{rid}/result.json")
def data_result(kind: str, rid: str):
    return _file(_run_dir(kind, rid), "result.json", "application/json")


@app.get("/data/{kind}/{rid}/video")
def data_video(kind: str, rid: str):
    d = _run_dir(kind, rid)
    if kind == "jobs":
        vids = [p for p in d.glob("upload.*") if p.suffix.lower() in ALLOWED]
    else:
        vids = [ROOT / "TRACEVISION_DATA/raw/test_videos" / f"{rid}.mp4"]
    if not vids or not vids[0].exists():
        raise HTTPException(404, "video not found")
    return FileResponse(vids[0], media_type="video/mp4")  # FileResponse answers Range requests (seeking)


@app.get("/data/{kind}/{rid}/crosscam")
def data_crosscam(kind: str, rid: str):
    """Cross-camera links involving this clip (from runs/crosscam/<a>__<b>.json, owner-declared same-scene pairs, M16).
    Each entry is written from THIS clip's point of view; `fold` maps nested duplicate tracks to the kept track."""
    _run_dir(kind, rid)
    out = {"links": [], "fold": {}}
    if kind != "runs":
        return JSONResponse(out)
    for p in sorted((RUNS / "crosscam").glob("*__*.json")):
        try:
            res = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        pl = res.get("pair_linking")
        if not pl or rid not in (res.get("clip_a"), res.get("clip_b")):
            continue
        me, other = ("a", "b") if res["clip_a"] == rid else ("b", "a")
        out["fold"].update(pl.get("duplicates_folded", {}).get(me, {}))
        for l in pl["links"]:
            out["links"].append({"track_id": l[me]["track_id"], "other_clip": l[other]["clip_id"],
                                 "other_track": l[other]["track_id"], "link": l["link"], "link_score": l["link_score"],
                                 "evidence": l["evidence"], "final": l["final"],
                                 "this_plate": l[me]["plate"], "other_plate": l[other]["plate"]})
    return JSONResponse(out)


@app.get("/data/{kind}/{rid}/files")
def data_files(kind: str, rid: str):
    vd = _run_dir(kind, rid) / "vehicles"
    return JSONResponse(sorted(p.name for p in vd.glob("*.jpg") if _IMG.match(p.name)) if vd.exists() else [])


@app.get("/data/{kind}/{rid}/vehicles/{name}")
def data_img(kind: str, rid: str, name: str):
    if not _IMG.match(name):
        raise HTTPException(404)
    return _file(_run_dir(kind, rid) / "vehicles", name, "image/jpeg")


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


# ---------------------------------------------------------------- vehicle intelligence + violations (synthetic demo)
def _who(role: str | None, user: str | None):
    try:
        return intel.role_of(role), intel.clean_user(user)
    except intel.Refused as e:
        raise HTTPException(e.status, str(e))


def _result_for(run: str):
    """'runs/clip03' or 'jobs/<id>' -> (run dir, result dict)."""
    kind, _, rid = run.partition("/")
    d = _run_dir(kind, rid)
    return d, json.loads((d / "result.json").read_text(encoding="utf-8"))


@app.get("/api/intel/meta")
def intel_meta():
    return JSONResponse({"roles": intel.ROLES, "reasons": intel.REASONS, "available": intel.available(),
                         "notice": "Synthetic demo data. Roles are chosen in the browser and not authenticated."})


@app.get("/api/intel/{registration}")
def intel_lookup(registration: str, reason: str = "", context: str = "",
                 x_tv_role: str | None = Header(None), x_tv_user: str | None = Header(None)):
    role, user = _who(x_tv_role, x_tv_user)
    reason, context = reason.strip()[:120], context.strip()[:80]
    if context:
        # Records are only attached to a CONFIDENT match: never to a candidate list or a partly read plate.
        m = re.fullmatch(r"((?:runs|jobs)/[\w]+):T(\d+)", context)
        if not m:
            raise HTTPException(400, "context must look like runs/clip03:T1")
        _, res = _result_for(m.group(1))
        veh = next((v for v in res.get("vehicles", []) if str(v.get("track_id")) == m.group(2)), None)
        top = (veh or {}).get("candidates") or []
        if not veh or veh.get("decision") != "match" or not top or top[0]["registration_number"] != registration.upper():
            intel.audit({"user": user, "role": role, "registration": registration.upper(), "reason": reason or None,
                         "context": context, "action": "lookup", "outcome": "refused: not a confident match"})
            raise HTTPException(409, "this vehicle has no confident registry match, so no record is attached to it")
    try:
        return JSONResponse(intel.lookup(registration, role, user, reason, context or "manual search"))
    except intel.Refused as e:
        raise HTTPException(e.status, str(e))


@app.get("/api/audit")
def audit_log(x_tv_role: str | None = Header(None), x_tv_user: str | None = Header(None)):
    role, _ = _who(x_tv_role, x_tv_user)
    if not intel.ROLES[role]["audit"]:
        raise HTTPException(403, "the audit log is visible to traffic officers only")
    return JSONResponse(intel.audit_log())


@app.get("/data/{kind}/{rid}/violations")
def data_violations(kind: str, rid: str):
    _, res = _result_for(f"{kind}/{rid}")
    return JSONResponse(violations.detect(res, f"{kind}/{rid}"))


@app.get("/api/violations")
def all_violations():
    items, assessed = [], []
    for p in sorted(RUNS.glob("clip*/result.json"), key=lambda p: int(re.search(r"\d+", p.parent.name).group())):
        try:
            d = violations.detect(json.loads(p.read_text(encoding="utf-8")), f"runs/{p.parent.name}")
        except Exception as e:  # one bad clip must not hide the rest
            d = {"assessed": False, "not_assessed_reason": repr(e), "violations": [], "checked_vehicles": 0, "camera_id": None}
        if d["assessed"]:
            assessed.append({"clip_id": p.parent.name, "camera_id": d["camera_id"], "checked_vehicles": d["checked_vehicles"],
                             "flagged": len(d["violations"]), "stabilisation": d.get("stabilisation")})
        items += d["violations"]
    return JSONResponse({"violations": items, "assessed_clips": assessed, "issued_challans": intel.issued_challans()})


@app.post("/api/violations/review")
def review_violation(payload: dict = Body(...), x_tv_role: str | None = Header(None), x_tv_user: str | None = Header(None)):
    role, user = _who(x_tv_role, x_tv_user)
    if not intel.ROLES[role]["review"]:
        raise HTTPException(403, "only a traffic officer can review violations")
    vid, decision = str(payload.get("violation_id", "")), payload.get("decision")
    note = str(payload.get("note", "")).strip()[:300]
    if decision not in ("confirmed", "rejected", "pending"):
        raise HTTPException(400, "decision must be confirmed, rejected or pending")
    m = re.fullmatch(r"((?:runs|jobs)/\w+):T(\d+):wrong_side", vid)
    if not m:
        raise HTTPException(400, "unknown violation id")
    _, res = _result_for(m.group(1))
    found = next((v for v in violations.detect(res, m.group(1))["violations"] if v["violation_id"] == vid), None)
    if not found:
        raise HTTPException(404, "no such suspected violation")
    review = {"status": decision, "by": user, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "note": note or None}
    violations.save_review(vid, review)
    challan = None
    if decision == "confirmed" and found["registration_number"]:
        challan = {"challan_id": f"SYN-SIM-{uuid.uuid4().hex[:8].upper()}", "violation_id": vid,
                   "registration_number": found["registration_number"], "violation": found["label"],
                   "date": time.strftime("%Y-%m-%dT%H:%M"), "location": f"{found['clip_id']} ({res.get('camera_type')})",
                   "fine_inr": 1000, "status": "Pending", "source": "simulated_from_review",
                   "issuing_authority": "TraceVision demo (simulated, not sent anywhere)", "confirmed_by": user}
        intel.add_issued_challan(challan)
    else:
        intel.remove_issued_challan(vid)
    intel.audit({"user": user, "role": role, "action": "review", "violation_id": vid, "outcome": decision,
                 "note": note or None, "challan": challan["challan_id"] if challan else None})
    return JSONResponse({"review": review, "challan": challan,
                         "message": None if challan or decision != "confirmed" else
                         "Confirmed. No challan raised: the vehicle has no confident registry match."})


def main():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
