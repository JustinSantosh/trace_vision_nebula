"""Printable e-challan notice (PDF) for a SIMULATED or synthetic-history challan.

    python -m tracevision.challan SYN-SIM-1A2B3C4D [-o out.pdf]

The notice carries the offence, the vehicle and its (synthetic) registered owner, the fine, and, when the challan was
raised from a case, the camera evidence: the vehicle and plate crops, the plate as read, the registry match score and
the wrong-side measurement. Every page is watermarked SIMULATED: nothing here is a legal document or is sent anywhere.
"""
from __future__ import annotations

import argparse
import io
import json
import re
from datetime import datetime
from pathlib import Path

from . import ROOT, intel

RUNS = ROOT / "runs"
JOBS = RUNS / "jobs"
NOTICE = ("Simulated notice produced by the TraceVision prototype from synthetic registry data. It is not issued by "
          "any traffic authority, has no legal effect, cannot be paid, and has not been sent to anyone.")


def _when(iso: str | None, fmt="%d %b %Y, %H:%M") -> str:
    try:
        return datetime.fromisoformat(iso).strftime(fmt)
    except (TypeError, ValueError):
        return iso or "—"


def _inr(n) -> str:
    """Indian digit grouping: 120000 -> 1,20,000."""
    s = str(int(n))
    if len(s) <= 3:
        return "₹" + s
    head, tail = s[:-3], s[-3:]
    head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
    return f"₹{head},{tail}"


def _case(challan: dict):
    """Camera evidence behind a challan raised from a case: (run dir, run id, vehicle, violation entry) or None."""
    ctx = challan.get("violation_id") or challan.get("context") or ""
    m = re.match(r"^(runs|jobs)/(\w+):T(\d+)", ctx)
    if not m:
        return None
    kind, rid, tid = m.groups()
    d = (RUNS if kind == "runs" else JOBS) / rid
    try:
        res = json.loads((d / "result.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    veh = next((v for v in res.get("vehicles", []) if str(v.get("track_id")) == tid), None)
    if veh is None:
        return None
    vio = None
    if challan.get("violation_id"):
        try:
            from . import violations
            vio = next((x for x in violations.detect(res, f"{kind}/{rid}")["violations"]
                        if x["violation_id"] == challan["violation_id"]), None)
        except Exception:
            vio = None
    nf = d / "name.txt"
    name = (nf.read_text(encoding="utf-8").strip() if nf.exists() else "") or rid
    return {"dir": d, "run": f"{kind}/{rid}", "name": name, "res": res, "veh": veh, "vio": vio}


def _measurement_text(vio: dict) -> str | None:
    if not vio:
        return None
    m, fps = vio["measurement"], None
    t0, t1 = vio["time_s"]
    if m.get("method") == "head_on_pass":
        span = max(1, vio["evidence_frames"][2] - vio["evidence_frames"][0])
        fps = span / max(t1 - t0, 1e-6)
        ff, rr = m["front_frames"], m["rear_frames"]
        return (f"Moving camera, head-on pass: the vehicle is seen from the front ({len(ff)} frames from "
                f"{ff[0] / fps:.1f} s) and then from the rear ({len(rr)} frames from {rr[0] / fps:.1f} s); its box grew "
                f"{m['growth']:.1f}× while approaching. Road layout: {str(m.get('layout', 'undeclared')).replace('_', ' ')}.")
    if "cos_to_allowed" in m:
        import math
        ang = math.degrees(math.acos(max(-1.0, min(1.0, m["cos_to_allowed"]))))
        return (f"Fixed camera, zone '{m.get('zone')}': the vehicle moved {ang:.0f}° off the permitted direction, "
                f"{m.get('against_flow_share', 0):.0%} of its steps against the flow, between {t0:.1f} s and {t1:.1f} s.")
    return None


def _evidence_images(case):
    vd = case["dir"] / "vehicles"
    tid = case["veh"]["track_id"]
    veh = sorted(vd.glob(f"t{tid}_vehicle_f*.jpg"))
    plates = sorted(vd.glob(f"t{tid}_plate_f*.jpg"), key=lambda p: int(p.stem.split("_f")[-1]))
    return (veh[0] if veh else None), plates


def build_pdf(challan: dict) -> bytes:
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from . import pdfstyle as ps

    st, W = ps.styles(), ps.WIDTH
    reg = challan["registration_number"]
    try:
        rec = intel.record(reg)
    except intel.Refused:
        rec = None
    simulated = challan.get("source") == "simulated_issued"
    case = _case(challan) if simulated else None

    # ---- title row: title + id block + QR
    qr = QrCodeWidget(f"TRACEVISION-SIMULATED|{challan['challan_id']}|{reg}|{challan['fine_inr']}")
    b = qr.getBounds()
    qd = Drawing(26 * mm, 26 * mm, transform=[26 * mm / (b[2] - b[0]), 0, 0, 26 * mm / (b[3] - b[1]), 0, 0])
    qd.add(qr)
    kind = "Simulated e-challan" if simulated else "e-Challan record (synthetic history)"
    title = [Paragraph(kind.upper(), st["label"]), Paragraph("Notice of traffic violation", st["title"]),
             Paragraph(f"Challan no. <font name='{ps.MONO}'>{ps.esc(challan['challan_id'])}</font>", st["p"]),
             Paragraph(f"Issued {ps.esc(_when(challan.get('date')))}  ·  Status <b>{ps.esc(challan.get('status', '—'))}</b>", st["p"]),
             Paragraph(ps.esc(challan.get("issuing_authority") or ""), st["small"])]
    head = Table([[title, qd]], colWidths=[W - 30 * mm, 30 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                              ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    banner = Table([[Paragraph(f"<b>Not a legal document.</b> {ps.esc(NOTICE)}", st["cell"])]], colWidths=[W])
    banner.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fef3c7")),
                                ("LINEBEFORE", (0, 0), (0, -1), 3, ps.WARN), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                                ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story = [head, Spacer(1, 8), banner]

    # ---- offence + fine box side by side
    when = challan.get("date")
    if case:
        t0 = case["veh"]["first_frame"] / (case["res"]["video"]["fps"] or 30)
        t1 = case["veh"]["last_frame"] / (case["res"]["video"]["fps"] or 30)
        seen = f"{case['name']}, {t0:.1f}–{t1:.1f} s into the clip"
    else:
        seen = None
    offence = ps.kv_table([("Violation", Paragraph(f"<b>{ps.esc(challan['violation'])}</b>", st["cell"])),
                           ("Date and time", _when(when)), ("Location", challan.get("location")),
                           ("Recorded on", seen), ("Officer note", challan.get("note"))], st, W - 62 * mm, cols=1)
    fine = Table([[Paragraph("FINE", st["label"])], [Paragraph(_inr(challan["fine_inr"]), ps.ParagraphStyle(
        "fine", fontName=ps.BOLD, fontSize=24, leading=28, textColor=ps.INK))],
        [Paragraph("Not payable: simulated notice" if simulated else f"Status: {ps.esc(challan.get('status'))}", st["small"])]],
        colWidths=[56 * mm])
    fine.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, ps.INK), ("LEFTPADDING", (0, 0), (-1, -1), 10),
                              ("TOPPADDING", (0, 0), (0, 0), 8), ("BOTTOMPADDING", (0, -1), (-1, -1), 9)]))
    row = Table([[offence, fine]], colWidths=[W - 60 * mm, 60 * mm])
    row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    story += [Paragraph("Offence", st["h2"]), row]

    # ---- vehicle + owner
    story.append(Paragraph("Vehicle and registered owner", st["h2"]))
    story.append(Paragraph(ps.plate_markup(reg), st["plate"]))
    story.append(Spacer(1, 4))
    if rec:
        v, o = rec["vehicle"], rec["owner"]
        story.append(ps.kv_table([
            ("Make / model", " ".join(x for x in (v.get("manufacturer"), v.get("model")) if x)), ("Model year", v.get("model_year")),
            ("Type", v.get("vehicle_type")), ("Class", v.get("vehicle_class")), ("Colour", (v.get("colour") or "").capitalize()),
            ("Fuel", v.get("fuel_type")), ("RTO", v.get("rto")), ("Registered", v.get("registration_date")),
            ("Owner", o.get("name")), ("Owner type", f"{o.get('type')} · owner no. {o.get('serial')}"),
            ("Insurance", f"{rec['compliance']['insurance']['state']} (until {rec['compliance']['insurance']['until']})"),
            ("PUC", f"{rec['compliance']['puc']['state']} (until {rec['compliance']['puc']['until']})"),
        ], st, W, cols=2))
    else:
        story.append(Paragraph("The registration is no longer in the synthetic registry.", st["small"]))

    # ---- camera evidence
    if case:
        veh = case["veh"]
        top = (veh.get("candidates") or [{}])[0]
        story.append(Paragraph("Camera evidence", st["h2"]))
        vimg, plates = _evidence_images(case)
        shots = [x for x in [ps.thumb(vimg, 46 * mm, 62 * mm)] + [ps.thumb(p, 16 * mm, 46 * mm) for p in plates[:3]] if x]
        facts = [("Clip", f"{case['name']} ({str(case['res'].get('camera_type', '')).replace('_', ' ')})"),
                 ("Vehicle track", f"T{veh['track_id']}"),
                 ("Type / colour", f"{veh['type']['label']} · {veh['colour']['label']}"),
                 ("Plate as read", Paragraph(f"<font name='{ps.MONO}'>{ps.plate_markup(veh['plate'].get('fused'))}</font>", st["cell"])),
                 ("Registry match", f"{top.get('registration_number', '—')} · score {top.get('match_score', '—')} (ranking, not a probability)"),
                 ("Measured", Paragraph(ps.esc(_measurement_text(case["vio"])), st["cell"]) if case["vio"] else None),
                 ("Review", f"{case['vio']['review']['status']} on {_when(case['vio']['review'].get('at'))}" if case["vio"] and case["vio"]["review"].get("at") else None)]
        left = shots[0] if shots else ""
        right = [ps.kv_table(facts, st, W - 70 * mm, cols=1)]
        if len(shots) > 1:
            t = Table([shots[1:]], colWidths=[48 * mm] * (len(shots) - 1), hAlign="LEFT")
            t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 6)]))
            right.append(t)
        ev = Table([[left, right]], colWidths=[68 * mm, W - 68 * mm])
        ev.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        story.append(ev)

    # ---- what happens next (demo wording)
    story += [Paragraph("What happens next", st["h2"]),
              Paragraph("In a real deployment the owner would be able to view the evidence, pay, or contest the challan with the "
                        "issuing authority. " + (
                            "This prototype stops here: the challan exists only in the local demo store (runs/enforcement) "
                            "and can be cancelled from the Enforcement page." if simulated else
                            "This entry is part of the generated e-challan history that ships with the demo registry."), st["p"])]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=ps.PAGE, leftMargin=ps.MARGIN, rightMargin=ps.MARGIN, topMargin=17 * mm,
                            bottomMargin=16 * mm, title=f"Challan {challan['challan_id']}", author="TraceVision (simulated)")
    doc.build(story, canvasmaker=ps.numbered_canvas(f"e-Challan · {challan['challan_id']}", "SIMULATED · synthetic data",
                                                    "Not a legal document. Nothing has been sent to any authority.",
                                                    watermark="SIMULATED"))
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("challan_id")
    ap.add_argument("-o", "--out")
    a = ap.parse_args()
    c = intel.find_challan(a.challan_id)
    if not c:
        raise SystemExit(f"no challan {a.challan_id}")
    out = Path(a.out or f"{c['challan_id']}.pdf")
    out.write_bytes(build_pdf(c))
    print(out, f"{out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
