"""Per-clip investigator report (P5): HTML (self-contained) + PDF, built from runs/<clip>/result.json.

    python -m tracevision.report                 # every runs/clip*/ -> report.html + report.pdf (+ copy in evaluation/reports/)
    python -m tracevision.report --clips clip03

Content per vehicle (problem statement): frames used, characters read per frame with confidence, fused plate with '?',
type and colour, top-5 registry candidates with match score and reasons, or "no confident match" with the reason.
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import shutil
from pathlib import Path

from . import ROOT

RUNS = ROOT / "runs"
DELIVER = ROOT / "TRACEVISION_DATA/evaluation/reports"
DECISION_LABEL = {"match": "MATCH", "ambiguous": "AMBIGUOUS (no single confident answer)", "no_confident_match": "NO CONFIDENT MATCH"}


def _thumb_bytes(p: Path, max_side=360):
    """Downscaled JPEG bytes (4K crops would make reports huge)."""
    import cv2
    im = cv2.imread(str(p))
    if im is None:
        return None
    s = max_side / max(im.shape[:2])
    if s < 1:
        im = cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return buf.tobytes() if ok else None


def _img_b64(p: Path):
    b = _thumb_bytes(p) if p and p.exists() else None
    return "data:image/jpeg;base64," + base64.b64encode(b).decode() if b else ""


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


def _prob_colour(p):
    return "#1b7f3b" if p >= 0.95 else "#7a8f1b" if p >= 0.8 else "#b7791f" if p >= 0.5 else "#b91c1c"


# ------------------------------------------------------------------ HTML
CSS = """
:root{color-scheme:light dark;--ink:#1d2932;--muted:#52616e;--line:#d2dce2;--bg:#f5f7f7;--surface:#fff;--head:#edf2f3;--accent:#286f68;--ok:#236b4a;--warn:#805b1c;--bad:#8d3f47;--unknown:#765c24}
@media (prefers-color-scheme:dark){:root{--ink:#edf2f5;--muted:#a5b1bc;--line:#34424c;--bg:#0d1218;--surface:#151e28;--head:#1b2632;--accent:#94ddd1;--ok:#9bd8b3;--warn:#e4b76d;--bad:#e17e83;--unknown:#e4c47e}}
*{box-sizing:border-box}body{font-family:"Segoe UI Variable",Segoe UI,system-ui,sans-serif;color:var(--ink);background:var(--bg);margin:0 auto;max-width:1240px;padding:32px;line-height:1.55}
h1{margin:0 0 8px;font-size:clamp(26px,4vw,36px);line-height:1.15;letter-spacing:-.03em}h2{margin:32px 0 12px;border-bottom:1px solid var(--line);padding-bottom:9px;font-size:21px;line-height:1.3}.muted{color:var(--muted)}
body>div:first-of-type{line-height:1.65}p{margin:12px 0}.small{font-size:13px}
table{border-collapse:collapse;width:100%;margin:10px 0 18px;background:var(--surface)}th,td{border:1px solid var(--line);padding:8px 10px;vertical-align:top;text-align:left;font-size:13px;line-height:1.45}
th{background:var(--head);font-size:12px;font-weight:650}tr:nth-child(even) td{background:color-mix(in srgb,var(--surface) 92%,var(--head))}.plate{font-family:Consolas,"Cascadia Mono",monospace;font-size:22px;letter-spacing:2px;font-weight:700;font-variant-numeric:tabular-nums}
.q{color:var(--unknown);text-decoration:underline;text-decoration-style:dotted;text-underline-offset:3px}.chip{display:inline-block;padding:4px 9px;border:1px solid currentColor;border-radius:5px;font-weight:700;font-size:12px;letter-spacing:.035em}
.match{background:color-mix(in srgb,var(--ok) 12%,var(--surface));color:var(--ok)}.ambiguous{background:color-mix(in srgb,var(--warn) 13%,var(--surface));color:var(--warn)}.no_confident_match{background:color-mix(in srgb,var(--bad) 12%,var(--surface));color:var(--bad)}
.card{border:1px solid var(--line);border-radius:8px;padding:18px 20px;margin:14px 0;background:var(--surface);break-inside:avoid}.imgs{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}.imgs img{max-width:min(240px,100%);max-height:180px;object-fit:contain;margin:0;border:1px solid var(--line);border-radius:5px;background:var(--bg)}
.grid td{font-family:Consolas,"Cascadia Mono",monospace;text-align:center;min-width:30px;font-variant-numeric:tabular-nums}.card>div{margin:7px 0}
@media(max-width:700px){body{padding:18px 14px}.card{padding:13px}.grid-wrap{overflow-x:auto}table{min-width:560px}h2{font-size:19px}}
@media print{:root{color-scheme:light}body{max-width:none;padding:0;background:#fff;color:#111}h1,h2{break-after:avoid}.card{background:#fff;box-shadow:none}.card,.imgs,table{break-inside:avoid}a{color:inherit}th{background:#edf2f3!important}.muted{color:#46525c}}
"""


def vehicle_html(run_dir, v):
    veh_img, plate_imgs = _evidence(run_dir, v)
    p = v["plate"]
    fused = p["fused"] or ""
    plate_html = "".join(f'<span class="q">?</span>' if c == "?" else html.escape(c) for c in fused) if fused else "<i>—</i>"
    rows = []
    for r in p["per_frame_reads"]:
        cells = "".join(f'<td style="color:{_prob_colour(pr)}">{html.escape(ch)}<div class="small">{pr:.2f}</div></td>'
                        for ch, pr in zip(r["text"], r["char_probs"]))
        rows.append(f"<tr><td>f{r['frame']}</td><td>{r['height_px']} px</td><td>{r['quality']}</td>{cells}</tr>")
    reads = (f'<table class="grid"><tr><th>frame</th><th>plate height</th><th>quality</th><th colspan="12">characters read (OCR confidence)</th></tr>{"".join(rows)}</table>'
             if rows else "")
    pos = ""
    if p["positions"]:
        pos = ('<table class="grid"><tr><th>position</th>' + "".join(f"<td>{x['pos']}</td>" for x in p["positions"]) + "</tr>"
               "<tr><th>fused</th>" + "".join(f'<td class="{"q" if x["char"] == "?" else ""}">{html.escape(x["char"])}</td>' for x in p["positions"]) + "</tr>"
               "<tr><th>confidence</th>" + "".join(f"<td class='small'>{x['confidence']:.2f}</td>" for x in p["positions"]) + "</tr>"
               "<tr><th>vote share</th>" + "".join(f"<td class='small'>{x['share']:.2f}</td>" for x in p["positions"]) + "</tr></table>")
    if v["candidates"]:
        cand = "<table><tr><th>#</th><th>registry id</th><th>plate</th><th>match score</th><th>reasons</th></tr>" + "".join(
            f"<tr><td>{c['rank']}</td><td>{c['synthetic_vehicle_id']}</td><td class='plate' style='font-size:15px'>{c['registration_number']}</td>"
            f"<td><b>{c['match_score']}</b></td><td>{'<br>'.join(html.escape(x) for x in c['reasons'])}</td></tr>" for c in v["candidates"]) + "</table>"
    else:
        cand = ""
    imgs = "".join(f'<img src="{_img_b64(x)}" title="{x.stem}">' for x in ([veh_img] if veh_img else []) + plate_imgs[:5])
    warn = f"<div class='small muted'>warnings: {html.escape('; '.join(p['warnings']))}</div>" if p["warnings"] else ""
    return f"""<div class="card">
<div><b>Vehicle (track {', '.join(map(str, v['merged_track_ids']))})</b> · frames {v['first_frame']}–{v['last_frame']} (from {v['first_time_s']} s)
 · <span class="chip {v['decision']}">{DECISION_LABEL[v['decision']]}</span></div>
<div>Type: <b>{v['type']['label']}</b> <span class="muted small">(vote share {v['type']['vote_share']})</span> ·
 Colour: <b>{v['colour']['label']}</b> <span class="muted small">(confidence {v['colour']['confidence']}{', ' + html.escape(v['colour']['note']) if v['colour'].get('note') else ''})</span></div>
<div>Plate: <span class="plate">{plate_html}</span> <span class="muted small">{html.escape(p['status'])}</span></div>{warn}
<div class="imgs">{imgs}</div>{reads}{pos}
<div><b>Decision:</b> {html.escape(v['decision_reason'])}</div>{cand}</div>"""


def build_html(run_dir: Path):
    res = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    vs = ordered_vehicles(res)
    detailed = [v for v in vs if v["plate"]["fused"] or v["plate"]["per_frame_reads"] or v["decision"] != "no_confident_match"]
    rest = [v for v in vs if v not in detailed]
    s = res["summary"]
    rest_rows = "".join(f"<tr><td>{', '.join(map(str, v['merged_track_ids']))}</td><td>{v['first_frame']}–{v['last_frame']}</td>"
                        f"<td>{v['type']['label']}</td><td>{v['colour']['label']}</td><td>{html.escape(v['plate']['status'])}</td>"
                        f"<td>{DECISION_LABEL[v['decision']]}</td></tr>" for v in rest)
    body = f"""<h1>TRACEVISION AI: clip report {res['clip_id']}</h1>
<div class="muted">Camera: {res['camera_type']} · {res['video']['width']}×{res['video']['height']} @ {res['video']['fps']:.1f} fps, {res['video']['frames']} frames ·
processed {res['processed_at']} · {res['timing']['total_s']} s</div>
<p><b>{s['vehicles_after_relink']} vehicles</b> · plates read: {s['plates_read']} · decisions: {', '.join(f'{k}: {v}' for k, v in s['decisions'].items())}</p>
<p class="small muted">Match score is a heuristic ranking score (0–100), <b>not a probability</b>. <span class="q">?</span> marks characters that could not be read; they are never guessed.
The registry is synthetic (no real owner data).</p>
<h2>Vehicles with plate evidence or a candidate ({len(detailed)})</h2>{''.join(vehicle_html(run_dir, v) for v in detailed) or '<p>None.</p>'}
<h2>Other vehicles ({len(rest)})</h2>
<table><tr><th>track</th><th>frames</th><th>type</th><th>colour</th><th>plate</th><th>decision</th></tr>{rest_rows}</table>"""
    return f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Clip report {res['clip_id']}</title><style>{CSS}</style></head><body>{body}</body></html>"


# ------------------------------------------------------------------ PDF (reportlab, no extra install)
def build_pdf(run_dir: Path, out: Path):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    try:
        pdfmetrics.registerFont(TTFont("Body", r"C:\Windows\Fonts\segoeui.ttf"))
        pdfmetrics.registerFont(TTFont("Body-B", r"C:\Windows\Fonts\segoeuib.ttf"))
        pdfmetrics.registerFont(TTFont("Mono", r"C:\Windows\Fonts\consola.ttf"))
        B, BB, M = "Body", "Body-B", "Mono"
    except Exception:
        B, BB, M = "Helvetica", "Helvetica-Bold", "Courier"
    res = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    st = {"h1": ParagraphStyle("h1", fontName=BB, fontSize=16, leading=20, spaceAfter=4),
          "h2": ParagraphStyle("h2", fontName=BB, fontSize=12, leading=15, spaceBefore=8, spaceAfter=4, textColor=colors.HexColor("#1d4ed8")),
          "p": ParagraphStyle("p", fontName=B, fontSize=8.8, leading=11.5),
          "s": ParagraphStyle("s", fontName=B, fontSize=7.5, leading=9.5, textColor=colors.HexColor("#5f6b7a")),
          "plate": ParagraphStyle("pl", fontName=M, fontSize=15, leading=18)}
    W = A4[0] - 30 * mm
    s = res["summary"]
    story = [Paragraph(f"TRACEVISION AI: clip report {res['clip_id']}", st["h1"]),
             Paragraph(f"Camera: {res['camera_type']} · {res['video']['width']}×{res['video']['height']} @ {res['video']['fps']:.1f} fps · "
                       f"{s['vehicles_after_relink']} vehicles · plates read {s['plates_read']} · "
                       + ", ".join(f"{k}: {v}" for k, v in s['decisions'].items()) + f" · processed in {res['timing']['total_s']} s", st["p"]),
             Paragraph("Match score is a heuristic ranking score (0–100), not a probability. '?' marks characters that could not be read; "
                       "they are never guessed. The registry is synthetic.", st["s"]), Spacer(1, 4)]
    vs = ordered_vehicles(res)
    detailed = [v for v in vs if v["plate"]["fused"] or v["plate"]["per_frame_reads"] or v["decision"] != "no_confident_match"]
    rest = [v for v in vs if v not in detailed]
    story.append(Paragraph(f"Vehicles with plate evidence or a candidate ({len(detailed)})", st["h2"]))
    grid = TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d5dbe3")), ("FONTNAME", (0, 0), (-1, -1), B),
                       ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                       ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f8"))])
    for v in detailed:
        block = []
        p = v["plate"]
        fused = (p["fused"] or "—").replace("?", "<font color='#b91c1c'>?</font>")
        dec_col = {"match": "#15803d", "ambiguous": "#b45309", "no_confident_match": "#b91c1c"}[v["decision"]]
        block.append(Paragraph(f"<b>Vehicle (track {', '.join(map(str, v['merged_track_ids']))})</b> · frames {v['first_frame']}–{v['last_frame']} · "
                               f"<font color='{dec_col}'><b>{DECISION_LABEL[v['decision']]}</b></font>", st["p"]))
        block.append(Paragraph(f"Type <b>{v['type']['label']}</b> (vote {v['type']['vote_share']}) · Colour <b>{v['colour']['label']}</b> "
                               f"(conf {v['colour']['confidence']}) · Plate status: {html.escape(p['status'])}", st["p"]))
        block.append(Paragraph(f"Fused plate: <font name='{M}' size='14'>{fused}</font>", st["plate"]))
        veh_img, plate_imgs = _evidence(run_dir, v)
        ims = []
        import io
        for x in ([veh_img] if veh_img else []) + plate_imgs[:4]:
            b = _thumb_bytes(x)
            if not b:
                continue
            im = Image(io.BytesIO(b)); r = min(28 * mm / im.imageHeight, (W / 5 - 2 * mm) / im.imageWidth)
            im.drawHeight, im.drawWidth = im.imageHeight * r, im.imageWidth * r; ims.append(im)
        if ims:
            t = Table([ims], hAlign="LEFT", colWidths=[W / 5] * len(ims))
            t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 1), ("RIGHTPADDING", (0, 0), (-1, -1), 1)]))
            block.append(t)
        if p["per_frame_reads"]:
            n = max(len(r["text"]) for r in p["per_frame_reads"])
            data = [["frame", "h px"] + [str(i + 1) for i in range(n)]]
            for r in p["per_frame_reads"]:
                data.append([f"f{r['frame']}", str(r["height_px"])] + [f"{c}\n{pr:.2f}" for c, pr in zip(r["text"], r["char_probs"])] + [""] * (n - len(r["text"])))
            t = Table(data, hAlign="LEFT"); t.setStyle(grid); block.append(t)
        block.append(Paragraph(f"<b>Decision:</b> {html.escape(v['decision_reason'])}", st["p"]))
        if v["candidates"]:
            data = [["#", "registry id", "plate", "match score", "reasons"]]
            for c in v["candidates"]:
                data.append([str(c["rank"]), c["synthetic_vehicle_id"], c["registration_number"], str(c["match_score"]),
                             Paragraph("<br/>".join(html.escape(x) for x in c["reasons"]), st["s"])])
            t = Table(data, colWidths=[8 * mm, 22 * mm, 28 * mm, 18 * mm, W - 76 * mm], hAlign="LEFT"); t.setStyle(grid); block.append(t)
        block.append(Spacer(1, 8))
        story.append(KeepTogether(block))
    story.append(Paragraph(f"Other vehicles ({len(rest)}): detected and tracked, no usable plate", st["h2"]))
    data = [["track", "frames", "type", "colour", "plate status"]] + [
        [", ".join(map(str, v["merged_track_ids"])), f"{v['first_frame']}–{v['last_frame']}", v["type"]["label"], v["colour"]["label"],
         Paragraph(html.escape(v["plate"]["status"]), st["s"])] for v in rest]
    t = Table(data, colWidths=[22 * mm, 22 * mm, 30 * mm, 18 * mm, W - 92 * mm], hAlign="LEFT", repeatRows=1); t.setStyle(grid); story.append(t)
    SimpleDocTemplate(str(out), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
                      title=f"Clip report {res['clip_id']}").build(story)


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
