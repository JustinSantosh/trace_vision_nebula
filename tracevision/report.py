"""Per-clip investigator report (P5): HTML (self-contained) + PDF, built from runs/<clip>/result.json.

    python -m tracevision.report                 # every runs/clip*/ -> report.html + report.pdf (+ copy in evaluation/reports/)
    python -m tracevision.report --clips clip03

Content per vehicle (problem statement): frames used, characters read per frame with confidence, fused plate with '?',
type and colour, top-5 registry candidates with match score and reasons, or "no confident match" with the reason.
The HTML and the PDF are laid out from the same outline (`_outline`), so they always say the same thing.
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import shutil
from datetime import datetime
from pathlib import Path

from . import ROOT

RUNS = ROOT / "runs"
DELIVER = ROOT / "TRACEVISION_DATA/evaluation/reports"
DECISION_LABEL = {"match": "Match", "ambiguous": "Ambiguous", "no_confident_match": "No confident match"}
READING_NOTE = ("Match score is a heuristic ranking score (0–100), not a probability. A red ? marks a plate character "
                "that could not be read; it is never guessed. The registry is synthetic demo data with no real owners.")


# ------------------------------------------------------------------ shared outline
def _evidence(run_dir: Path, v):
    vd = run_dir / "vehicles"
    veh = sorted(vd.glob(f"t{v['track_id']}_vehicle_f*.jpg"))
    plates = sorted(vd.glob(f"t{v['track_id']}_plate_f*.jpg"), key=lambda p: int(p.stem.split("_f")[-1]))
    return (veh[0] if veh else None), plates


def ordered_vehicles(res):
    """Vehicles with a readable plate first (most informative), then the rest by first appearance."""
    key = {"match": 0, "ambiguous": 1, "no_confident_match": 2}
    return sorted(res["vehicles"], key=lambda v: (0 if v["plate"]["fused"] and v["plate"]["fused"].strip("?") else 1,
                                                  key.get(v["decision"], 3), v["first_frame"]))


def _clock(sec: float) -> str:
    m, s = divmod(max(0.0, sec), 60)
    return f"{int(m)}:{s:04.1f}"


def _when(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %Y, %H:%M")
    except (TypeError, ValueError):
        return iso or "—"


def _outline(run_dir: Path):
    res = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    nf = run_dir / "name.txt"
    name = (nf.read_text(encoding="utf-8").strip() if nf.exists() else "") or res["clip_id"]
    vid, s = res["video"], res["summary"]
    fps = vid["fps"] or 30.0
    dec = s.get("decisions", {})
    vs = ordered_vehicles(res)
    detailed = [v for v in vs if v["plate"]["fused"] or v["plate"]["per_frame_reads"] or v["decision"] != "no_confident_match"]
    rest = [v for v in vs if v not in detailed]
    return {
        "res": res, "name": name, "fps": fps, "detailed": detailed, "rest": rest,
        "meta": [("Camera", str(res.get("camera_type", "unknown")).replace("_", " ").capitalize()),
                 ("Video", f"{vid['width']}×{vid['height']} · {fps:.0f} fps · {_clock(vid['frames'] / fps)}"),
                 ("Processed", _when(res.get("processed_at"))),
                 ("Analysis time", f"{res['timing']['total_s']:.0f} s")],
        "stats": [(s["vehicles_after_relink"], "vehicles tracked"), (s["plates_read"], "plates read"),
                  (dec.get("match", 0), "registry matches"), (dec.get("ambiguous", 0), "ambiguous"),
                  (dec.get("no_confident_match", 0), "no confident match")],
    }


def _span(v, fps):
    return f"{_clock(v['first_frame'] / fps)}–{_clock(v['last_frame'] / fps)}"


def _tracks(v):
    ids = v["merged_track_ids"]
    return f"T{ids[0]}" + (f" (+{len(ids) - 1} merged)" if len(ids) > 1 else "")


def _prob_colour(p):
    return "#15803d" if p >= 0.95 else "#4d7c0f" if p >= 0.8 else "#b45309" if p >= 0.5 else "#b91c1c"


# ------------------------------------------------------------------ HTML
def _img_b64(p: Path, max_side=360):
    import cv2
    im = cv2.imread(str(p)) if p and p.exists() else None
    if im is None:
        return ""
    s = max_side / max(im.shape[:2])
    if s < 1:
        im = cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode() if ok else ""


CSS = """
:root{color-scheme:dark;--ink:#eef0ea;--muted:#a6adb6;--line:#23272d;--bg:#0a0b0d;--card:#121418;--head:#1a1d22;--accent:#f2c230;
--ok:#4ade80;--ok-bg:#10291a;--warn:#f2b544;--warn-bg:#33260c;--bad:#f2817a;--bad-bg:#3a1c1c}
*{box-sizing:border-box}
body{font-family:"Segoe UI",system-ui,sans-serif;color:var(--ink);background:var(--bg);margin:0;line-height:1.45;font-size:14px}
main{max-width:1040px;margin:0 auto;padding:28px 16px 48px}
.brand{font-weight:700;letter-spacing:.08em;font-size:12px;color:var(--accent)}
h1{font-size:26px;margin:4px 0 10px;overflow-wrap:anywhere}
h2{font-size:16px;margin:32px 0 12px}
.meta{display:flex;flex-wrap:wrap;gap:6px 22px;color:var(--muted);font-size:13px}.meta b{color:var(--ink);font-weight:600}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));border:1px solid var(--line);border-radius:10px;
 background:var(--card);margin:20px 0 8px;overflow:hidden}
.stats div{padding:12px 14px;border-right:1px solid var(--line)}.stats div:last-child{border-right:0}
.stats b{display:block;font-size:24px;font-variant-numeric:tabular-nums}.stats span{color:var(--muted);font-size:12px}
.note{color:var(--muted);font-size:12.5px;margin:8px 0 0}
.card{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--c);border-radius:10px;padding:16px 18px;margin:0 0 14px;break-inside:avoid}
.card.match{--c:var(--ok)}.card.ambiguous{--c:var(--warn)}.card.no_confident_match{--c:var(--bad)}
.card-head{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;margin-bottom:12px}
.card-head h3{margin:0;font-size:15px}.card-head .sub{color:var(--muted);font-size:13px}
.chip{margin-left:auto;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600}
.chip.match{background:var(--ok-bg);color:var(--ok)}.chip.ambiguous{background:var(--warn-bg);color:var(--warn)}
.chip.no_confident_match{background:var(--bad-bg);color:var(--bad)}
.top{display:grid;grid-template-columns:minmax(0,200px) minmax(0,1fr);gap:16px}
@media (max-width:640px){.top{grid-template-columns:1fr}}
.shot{width:100%;border-radius:6px;border:1px solid var(--line);background:var(--head);display:block}
.plate{font-family:Consolas,"Cascadia Mono",monospace;font-weight:700;font-size:26px;letter-spacing:3px;overflow-wrap:anywhere}
.q{color:var(--bad)}
dl{display:grid;grid-template-columns:110px minmax(0,1fr);gap:4px 12px;margin:10px 0 0}dt{color:var(--muted);font-size:12.5px}dd{margin:0}
.reason{margin:10px 0 0;padding:8px 10px;background:var(--head);border-radius:6px;font-size:13px}
.crops{display:flex;flex-wrap:wrap;gap:6px;margin:14px 0 4px}.crops img{height:44px;border-radius:4px;border:1px solid var(--line)}
.label{font-size:11.5px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin:16px 0 6px}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13px}
th{background:var(--head);color:var(--muted);font-weight:600;font-size:11.5px;text-align:left}
th,td{padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
.grid td,.grid th{text-align:center;font-family:Consolas,monospace;padding:4px 5px;min-width:26px}
.grid td small{display:block;font-family:"Segoe UI",sans-serif;font-size:10px;opacity:.85}
.grid th:first-child,.grid td:first-child{text-align:left;font-family:inherit;white-space:nowrap}
.num{text-align:right;font-variant-numeric:tabular-nums}.mono{font-family:Consolas,monospace;font-weight:700;letter-spacing:1px}
.score{display:inline-block;height:6px;border-radius:3px;background:var(--accent);vertical-align:middle;margin-right:6px}
.muted{color:var(--muted)}
footer{color:var(--muted);font-size:12px;margin-top:40px;border-top:1px solid var(--line);padding-top:12px}
@media print{:root{color-scheme:light;--ink:#17202b;--muted:#5f6b7a;--line:#d5dbe3;--card:#fff;--head:#f3f5f8;--accent:#8a6a00;
--ok:#15803d;--ok-bg:#dcfce7;--warn:#b45309;--warn-bg:#fef3c7;--bad:#b91c1c;--bad-bg:#fee2e2}body{background:#fff;font-size:12px}main{padding:0}.card{border-color:#ccc}@page{size:A4;margin:14mm}}
"""


def _plate_html(text):
    return "".join('<span class="q">?</span>' if c == "?" else html.escape(c) for c in text) if text else '<span class="muted">not read</span>'


def _vehicle_html(run_dir, v, i, fps):
    veh_img, plate_imgs = _evidence(run_dir, v)
    p, dec = v["plate"], v["decision"]
    col = v["colour"]
    shot = f'<img class="shot" src="{_img_b64(veh_img)}" alt="Vehicle T{v["track_id"]}">' if veh_img else '<div class="shot" style="aspect-ratio:4/3"></div>'
    crops = "".join(f'<img src="{_img_b64(x, 240)}" alt="Plate crop" title="frame {x.stem.split("_f")[-1]}">' for x in plate_imgs[:6])
    out = [f'<section class="card {dec}"><div class="card-head"><h3>Vehicle {i}</h3>'
           f'<span class="sub">{_tracks(v)} · {_span(v, fps)}</span><span class="chip {dec}">{DECISION_LABEL[dec]}</span></div>',
           f'<div class="top">{shot}<div><div class="plate">{_plate_html(p["fused"])}</div><dl>'
           f'<dt>Type</dt><dd>{html.escape(v["type"]["label"])} <span class="muted">· vote {v["type"]["vote_share"]:.0%}</span></dd>'
           f'<dt>Colour</dt><dd>{html.escape(col["label"])} <span class="muted">· confidence {col["confidence"]:.2f}</span></dd>'
           f'<dt>Plate</dt><dd>{html.escape(p["status"])}</dd></dl>'
           f'<p class="reason"><b>Decision:</b> {html.escape(v["decision_reason"])}</p></div></div>']
    if p["warnings"]:
        out.append(f'<p class="note">Note: {html.escape("; ".join(p["warnings"]))}</p>')
    if crops:
        out.append(f'<div class="crops">{crops}</div>')
    if p["per_frame_reads"]:
        n = max(len(r["text"]) for r in p["per_frame_reads"])
        head = "".join(f"<th>{k + 1}</th>" for k in range(n))
        rows = "".join(
            f"<tr><td>{_clock(r['frame'] / fps)} <span class='muted'>f{r['frame']} · {r['height_px']} px</span></td>"
            + "".join(f'<td style="color:{_prob_colour(pr)}">{html.escape(ch)}<small>{pr:.2f}</small></td>' for ch, pr in zip(r["text"], r["char_probs"]))
            + "<td></td>" * (n - len(r["text"])) + "</tr>" for r in p["per_frame_reads"])
        out.append(f'<div class="label">Characters read per frame (OCR confidence)</div><div class="scroll"><table class="grid"><tr><th>Frame</th>{head}</tr>{rows}</table></div>')
    if p["positions"]:
        pos = p["positions"]
        out.append('<div class="label">Fused plate by position</div><div class="scroll"><table class="grid">'
                   "<tr><th>Position</th>" + "".join(f"<th>{x['pos']}</th>" for x in pos) + "</tr>"
                   "<tr><td>Character</td>" + "".join(f'<td class="{"q" if x["char"] == "?" else ""}"><b>{html.escape(x["char"])}</b></td>' for x in pos) + "</tr>"
                   "<tr><td>Confidence</td>" + "".join(f"<td><small>{x['confidence']:.2f}</small></td>" for x in pos) + "</tr>"
                   "<tr><td>Vote share</td>" + "".join(f"<td><small>{x['share']:.2f}</small></td>" for x in pos) + "</tr></table></div>")
    if v["candidates"]:
        rows = "".join(f"<tr><td class='num'>{c['rank']}</td><td class='mono'>{html.escape(c['registration_number'])}</td>"
                       f"<td class='muted'>{html.escape(c['synthetic_vehicle_id'])}</td>"
                       f"<td class='num'><span class='score' style='width:{max(2, c['match_score'] * 0.5):.0f}px'></span>{c['match_score']}</td>"
                       f"<td>{'<br>'.join(html.escape(x) for x in c['reasons'])}</td></tr>" for c in v["candidates"])
        out.append('<div class="label">Registry candidates</div><div class="scroll"><table><tr><th class="num">#</th><th>Plate</th>'
                   f'<th>Registry id</th><th class="num">Score</th><th>Why</th></tr>{rows}</table></div>')
    out.append("</section>")
    return "".join(out)


def build_html(run_dir: Path):
    o = _outline(run_dir)
    fps = o["fps"]
    meta = "".join(f"<span>{k} <b>{html.escape(v)}</b></span>" for k, v in o["meta"])
    stats = "".join(f"<div><b>{v}</b><span>{html.escape(k)}</span></div>" for v, k in o["stats"])
    cards = "".join(_vehicle_html(run_dir, v, i + 1, fps) for i, v in enumerate(o["detailed"])) or '<p class="muted">None.</p>'
    rest = "".join(f"<tr><td>{_tracks(v)}</td><td>{_span(v, fps)}</td><td>{html.escape(v['type']['label'])}</td>"
                   f"<td>{html.escape(v['colour']['label'])}</td><td class='muted'>{html.escape(v['plate']['status'])}</td></tr>" for v in o["rest"])
    rest_html = (f'<div class="scroll"><table><tr><th>Track</th><th>Seen</th><th>Type</th><th>Colour</th><th>Plate</th></tr>{rest}</table></div>'
                 if rest else '<p class="muted">None.</p>')
    body = f"""<main><div class="brand">TRACEVISION · CLIP REPORT</div><h1>{html.escape(o['name'])}</h1><div class="meta">{meta}</div>
<div class="stats">{stats}</div><p class="note">{READING_NOTE.replace('red ?', '<span class="q">?</span>')}</p>
<h2>Vehicles with plate evidence or a registry candidate ({len(o['detailed'])})</h2>{cards}
<h2>Other vehicles ({len(o['rest'])})</h2><p class="note" style="margin:0 0 10px">Detected and tracked, but no plate was usable.</p>{rest_html}
<footer>TraceVision · investigator copy · generated {datetime.now().strftime('%d %b %Y, %H:%M')}</footer></main>"""
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>Clip report · {html.escape(o['name'])}</title><style>{CSS}</style></head><body>{body}</body></html>")


# ------------------------------------------------------------------ PDF
def build_pdf(run_dir: Path, out: Path):
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import CondPageBreak, HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from . import pdfstyle as ps

    o = _outline(run_dir)
    st, fps, W = ps.styles(), o["fps"], ps.WIDTH
    story = [Paragraph("Clip report", st["sub"]), Paragraph(ps.esc(o["name"]), st["title"]),
             Paragraph("   ·   ".join(f"{k} <b>{ps.esc(v)}</b>" for k, v in o["meta"]), st["sub"]), Spacer(1, 10),
             ps.stat_tiles(o["stats"], st), Spacer(1, 6),
             Paragraph(ps.esc(READING_NOTE).replace("red ?", "red <font color='#b91c1c'>?</font>"), st["small"]),
             Paragraph(f"Vehicles with plate evidence or a registry candidate ({len(o['detailed'])})", st["h2"])]

    for i, v in enumerate(o["detailed"], 1):
        p, dec = v["plate"], v["decision"]
        label, dcol = ps.DECISION[dec]
        veh_img, plate_imgs = _evidence(run_dir, v)
        head = Table([[Paragraph(f"<b>Vehicle {i}</b>  <font color='#5f6b7a'>{_tracks(v)} · {_span(v, fps)}</font>", st["h3"]),
                       Paragraph(f"<font color='{dcol.hexval().replace('0x', '#')}'><b>{label}</b></font>", st["p"])]],
                     colWidths=[W - 44 * mm, 44 * mm])
        head.setStyle(TableStyle([("ALIGN", (1, 0), (1, 0), "RIGHT"), ("BACKGROUND", (0, 0), (-1, -1), ps.HEAD),
                                  ("LINEBEFORE", (0, 0), (0, -1), 3, dcol), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                                  ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        info = [Paragraph(ps.plate_markup(p["fused"]), st["plate"]), Spacer(1, 4),
                ps.kv_table([("Type", f"{v['type']['label']}  ·  vote {v['type']['vote_share']:.0%}"),
                             ("Colour", f"{v['colour']['label']}  ·  confidence {v['colour']['confidence']:.2f}"),
                             ("Plate", p["status"]), ("Decision", Paragraph(ps.esc(v["decision_reason"]), st["cell"]))], st, W - 52 * mm, cols=1)]
        shot = ps.thumb(veh_img, 34 * mm, 46 * mm) if veh_img else None
        top = Table([[shot or "", info]], colWidths=[50 * mm, W - 52 * mm])
        top.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        block = [head, Spacer(1, 6), top]
        crops = [c for c in (ps.thumb(x, 11 * mm, 34 * mm) for x in plate_imgs[:5]) if c]
        if crops:
            t = Table([crops], hAlign="LEFT", colWidths=[36 * mm] * len(crops))
            t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 6)]))
            block.append(t)
        if p["per_frame_reads"]:
            n = max(len(r["text"]) for r in p["per_frame_reads"])
            data = [["Frame"] + [str(k + 1) for k in range(n)]]
            for r in p["per_frame_reads"]:
                data.append([Paragraph(f"{_clock(r['frame'] / fps)} <font color='#5f6b7a' size='6.5'>f{r['frame']} · {r['height_px']}px</font>", st["cell"])]
                            + [Paragraph(f"<font name='{ps.MONO}' size='9' color='{_prob_colour(pr)}'>{ps.esc(ch)}</font><br/>"
                                         f"<font size='6' color='#5f6b7a'>{pr:.2f}</font>", st["cell"]) for ch, pr in zip(r["text"], r["char_probs"])]
                            + [""] * (n - len(r["text"])))
            t = Table(data, colWidths=[30 * mm] + [min(11 * mm, (W - 30 * mm) / n)] * n, hAlign="LEFT", repeatRows=1)
            t.setStyle(ps.grid_style())
            t.setStyle(TableStyle([("ALIGN", (1, 0), (-1, -1), "CENTER")]))
            block += [Spacer(1, 6), Paragraph("CHARACTERS READ PER FRAME (OCR CONFIDENCE)", st["label"]), Spacer(1, 2), t]
        if v["candidates"]:
            data = [["#", "Plate", "Registry id", "Score", "Why"]] + [
                [str(c["rank"]), Paragraph(f"<font name='{ps.MONO}'>{ps.esc(c['registration_number'])}</font>", st["cell"]),
                 Paragraph(ps.esc(c["synthetic_vehicle_id"]), st["small"]), Paragraph(f"<b>{c['match_score']}</b>", st["cell"]),
                 Paragraph("<br/>".join(ps.esc(x) for x in c["reasons"]), st["small"])] for c in v["candidates"]]
            t = Table(data, colWidths=[7 * mm, 30 * mm, 26 * mm, 14 * mm, W - 77 * mm], hAlign="LEFT", repeatRows=1)
            t.setStyle(ps.grid_style())
            block += [Spacer(1, 6), Paragraph("REGISTRY CANDIDATES", st["label"]), Spacer(1, 2), t]
        # Header, photo and plate crops stay together; the read / candidate tables may continue on the next page.
        story += [CondPageBreak(60 * mm), KeepTogether(block[:4 if crops else 3])] + block[4 if crops else 3:]
        story += [Spacer(1, 8), HRFlowable(width="100%", thickness=0.5, color=ps.LINE, spaceAfter=10)]

    story += [CondPageBreak(40 * mm), Paragraph(f"Other vehicles ({len(o['rest'])})", st["h2"]),
              Paragraph("Detected and tracked, but no plate was usable.", st["small"]), Spacer(1, 4)]
    if o["rest"]:
        data = [["Track", "Seen", "Type", "Colour", "Plate"]] + [
            [_tracks(v), _span(v, fps), v["type"]["label"], v["colour"]["label"], Paragraph(ps.esc(v["plate"]["status"]), st["small"])]
            for v in o["rest"]]
        t = Table(data, colWidths=[34 * mm, 28 * mm, 28 * mm, 20 * mm, W - 110 * mm], hAlign="LEFT", repeatRows=1)
        t.setStyle(ps.grid_style(zebra=True, n_rows=len(data)))
        story.append(t)
    doc = SimpleDocTemplate(str(out), pagesize=ps.PAGE, leftMargin=ps.MARGIN, rightMargin=ps.MARGIN, topMargin=16 * mm,
                            bottomMargin=16 * mm, title=f"Clip report {o['name']}", author="TraceVision")
    doc.build(story, canvasmaker=ps.numbered_canvas(f"Clip report · {o['name']}", "Investigator copy · synthetic registry",
                                                    "Match score is a ranking, not a probability. ? = unread, never guessed."))


def build(run_dir: Path, deliver=True):
    (run_dir / "report.html").write_text(build_html(run_dir), encoding="utf-8")
    build_pdf(run_dir, run_dir / "report.pdf")
    if deliver:
        DELIVER.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(run_dir / "report.pdf", DELIVER / f"{run_dir.name}_report.pdf")
    return run_dir / "report.html", run_dir / "report.pdf"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", nargs="*")
    ap.add_argument("--runs", default=str(RUNS))
    a = ap.parse_args()
    dirs = [Path(a.runs) / c for c in a.clips] if a.clips else sorted(p.parent for p in Path(a.runs).glob("clip*/result.json"))
    for d in dirs:
        h, p = build(d)
        print(d.name, "->", h.name, p.name, f"{p.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
