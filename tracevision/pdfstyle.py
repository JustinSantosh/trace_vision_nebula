"""Shared look for every PDF TraceVision writes (clip reports, challan notices): fonts, colours, page frame.

reportlab only (already a dependency). Segoe UI / Consolas are used when Windows has them, else the PDF core fonts.
"""
from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Image, Paragraph, Table, TableStyle

PAGE = A4
MARGIN = 16 * mm
WIDTH = A4[0] - 2 * MARGIN

INK = colors.HexColor("#17202b")
MUTED = colors.HexColor("#5f6b7a")
LINE = colors.HexColor("#dfe4ea")
HEAD = colors.HexColor("#f3f5f8")
ACCENT = colors.HexColor("#1d4ed8")
OK = colors.HexColor("#15803d")
WARN = colors.HexColor("#b45309")
BAD = colors.HexColor("#b91c1c")
DECISION = {"match": ("Match", OK), "ambiguous": ("Ambiguous", WARN), "no_confident_match": ("No confident match", BAD)}


def _fonts():
    try:
        pdfmetrics.getFont("TV-Body")
        return "TV-Body", "TV-Bold", "TV-Mono"
    except KeyError:
        pass
    try:
        pdfmetrics.registerFont(TTFont("TV-Body", r"C:\Windows\Fonts\segoeui.ttf"))
        pdfmetrics.registerFont(TTFont("TV-Bold", r"C:\Windows\Fonts\segoeuib.ttf"))
        pdfmetrics.registerFont(TTFont("TV-Mono", r"C:\Windows\Fonts\consolab.ttf"))
        return "TV-Body", "TV-Bold", "TV-Mono"
    except Exception:
        return "Helvetica", "Helvetica-Bold", "Courier-Bold"


BODY, BOLD, MONO = _fonts()


def styles():
    return {
        "title": ParagraphStyle("title", fontName=BOLD, fontSize=19, leading=23, textColor=INK, spaceAfter=2),
        "sub": ParagraphStyle("sub", fontName=BODY, fontSize=9, leading=12, textColor=MUTED),
        "h2": ParagraphStyle("h2", fontName=BOLD, fontSize=11.5, leading=14, textColor=INK, spaceBefore=12, spaceAfter=6),
        "h3": ParagraphStyle("h3", fontName=BOLD, fontSize=10, leading=13, textColor=INK),
        "p": ParagraphStyle("p", fontName=BODY, fontSize=8.8, leading=12, textColor=INK),
        "small": ParagraphStyle("small", fontName=BODY, fontSize=7.6, leading=10, textColor=MUTED),
        "cell": ParagraphStyle("cell", fontName=BODY, fontSize=8, leading=10.5, textColor=INK),
        "label": ParagraphStyle("label", fontName=BODY, fontSize=7.2, leading=9, textColor=MUTED),
        "value": ParagraphStyle("value", fontName=BOLD, fontSize=9.5, leading=12, textColor=INK),
        "plate": ParagraphStyle("plate", fontName=MONO, fontSize=16, leading=19, textColor=INK),
        "stat": ParagraphStyle("stat", fontName=BOLD, fontSize=17, leading=20, textColor=INK),
    }


def esc(s) -> str:
    return (str(s) if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def plate_markup(text: str, size=None) -> str:
    """Plate string with every unread position ('?') in red."""
    if not text:
        return "<font color='#5f6b7a'>not read</font>"
    out = "".join("<font color='#b91c1c'>?</font>" if c == "?" else esc(c) for c in text)
    return f"<font size='{size}'>{out}</font>" if size else out


def grid_style(header=True, zebra=False, n_rows=0):
    cmds = [("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("FONTNAME", (0, 0), (-1, -1), BODY), ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("TEXTCOLOR", (0, 0), (-1, -1), INK), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    if header:
        cmds += [("BACKGROUND", (0, 0), (-1, 0), HEAD), ("FONTNAME", (0, 0), (-1, 0), BOLD), ("FONTSIZE", (0, 0), (-1, 0), 7.4),
                 ("TEXTCOLOR", (0, 0), (-1, 0), MUTED), ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#c9d1db"))]
    if zebra:
        cmds += [("BACKGROUND", (0, i), (-1, i), colors.HexColor("#fafbfc")) for i in range(2, n_rows, 2)]
    return TableStyle(cmds)


def stat_tiles(items, st, width=WIDTH):
    """Row of big-number tiles: items = [(value, label), ...]."""
    cells = [[Paragraph(esc(v), st["stat"]), Paragraph(esc(lab), st["label"])] for v, lab in items]
    t = Table([cells], colWidths=[width / len(items)] * len(items))
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, LINE), ("LINEAFTER", (0, 0), (-2, -1), 0.5, LINE),
                           ("BACKGROUND", (0, 0), (-1, -1), HEAD), ("TOPPADDING", (0, 0), (-1, -1), 6),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
    return t


def kv_table(pairs, st, width=WIDTH, cols=2):
    """Label/value pairs laid out in `cols` column pairs (labels small and muted, values bold)."""
    pairs = [(k, v) for k, v in pairs if v not in (None, "")]
    rows = []
    for i in range(0, len(pairs), cols):
        row = []
        for k, v in pairs[i:i + cols]:
            row += [Paragraph(esc(k), st["label"]), v if not isinstance(v, (str, int, float)) else Paragraph(esc(v), st["cell"])]
        row += [""] * (2 * cols - len(row))
        rows.append(row)
    if not rows:
        return Paragraph("—", st["small"])
    lw = 30 * mm
    t = Table(rows, colWidths=[lw, width / cols - lw] * cols)
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE)]))
    return t


def thumb(path, max_h, max_w, max_side=480):
    """reportlab Image of a downscaled JPEG copy of `path` (None if unreadable). 4K crops would bloat the PDF."""
    import cv2
    im = cv2.imread(str(path)) if path else None
    if im is None:
        return None
    s = max_side / max(im.shape[:2])
    if s < 1:
        im = cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        return None
    img = Image(io.BytesIO(buf.tobytes()))
    r = min(max_h / img.imageHeight, max_w / img.imageWidth)
    img.drawHeight, img.drawWidth = img.imageHeight * r, img.imageWidth * r
    return img


def numbered_canvas(left: str, right: str, footer_note: str, watermark: str | None = None):
    """Canvas class drawing a thin running header, 'Page n of m' footer and an optional diagonal watermark."""
    stamp = datetime.now().strftime("%d %b %Y, %H:%M")

    class _Canvas(rl_canvas.Canvas):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._pages = []

        def showPage(self):
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            n = len(self._pages)
            for state in self._pages:
                self.__dict__.update(state)
                self._frame(n)
                super().showPage()
            super().save()

        def _frame(self, n):
            w, h = PAGE
            self.saveState()
            if watermark:
                self.setFont(BOLD, 54)
                self.setFillColor(colors.Color(0.73, 0.11, 0.11, alpha=0.07))
                self.translate(w / 2, h / 2)
                self.rotate(35)
                self.drawCentredString(0, 0, watermark)
                self.rotate(-35)
                self.translate(-w / 2, -h / 2)
            self.setStrokeColor(LINE)
            self.setLineWidth(0.5)
            self.line(MARGIN, h - 11 * mm, w - MARGIN, h - 11 * mm)
            self.line(MARGIN, 11 * mm, w - MARGIN, 11 * mm)
            self.setFont(BOLD, 7.5)
            self.setFillColor(ACCENT)
            self.drawString(MARGIN, h - 9 * mm, "TRACEVISION")
            self.setFont(BODY, 7.5)
            self.setFillColor(MUTED)
            self.drawString(MARGIN + 17 * mm, h - 9 * mm, left)
            self.drawRightString(w - MARGIN, h - 9 * mm, right)
            self.drawString(MARGIN, 7.5 * mm, footer_note)
            self.drawRightString(w - MARGIN, 7.5 * mm, f"Generated {stamp}  ·  Page {self._pageNumber} of {n}")
            self.restoreState()

    return _Canvas
