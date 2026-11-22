"""Indian number-plate rules shared by fusion and matching."""
from __future__ import annotations

import re

# Current and legacy RTO state / UT codes (OR and UA are legacy for OD and UK; TS and TG both seen for Telangana).
STATE_CODES = {
    "AN", "AP", "AR", "AS", "BR", "CH", "CG", "DD", "DL", "DN", "GA", "GJ", "HR", "HP", "JK", "JH", "KA", "KL",
    "LA", "LD", "MP", "MH", "MN", "ML", "MZ", "NL", "OD", "OR", "PB", "PY", "RJ", "SK", "TN", "TS", "TG", "TR",
    "UP", "UK", "UA", "WB",
}

# Characters that OCR (and people) confuse. Groups mix letters and digits on purpose.
LOOKALIKE_GROUPS = [set("0ODQ"), set("1I"), set("2Z"), set("5S"), set("8B"), set("6G")]
_GROUP_OF = {c: i for i, g in enumerate(LOOKALIKE_GROUPS) for c in g}

STANDARD = re.compile(r"^[A-Z?]{2}[0-9?]{1,2}[A-Z?]{0,3}[0-9?]{4}$")
BH = re.compile(r"^[0-9?]{2}[B?][H?][0-9?]{4}[A-Z?]{1,2}$")


def normalise(text: str) -> str:
    """Uppercase, keep A-Z, 0-9 and '?'."""
    return re.sub(r"[^A-Z0-9?]", "", (text or "").upper())


def is_lookalike(a: str, b: str) -> bool:
    return a != b and a in _GROUP_OF and _GROUP_OF.get(a) == _GROUP_OF.get(b)


def char_class(c: str) -> str:
    return "D" if c.isdigit() else "L" if c.isalpha() else "?"


def coerce(c: str, cls: str):
    """Return the look-alike of `c` in class `cls` ('L' or 'D'), or None if there is none."""
    if char_class(c) == cls:
        return c
    g = _GROUP_OF.get(c)
    if g is None:
        return None
    options = sorted(x for x in LOOKALIKE_GROUPS[g] if char_class(x) == cls)
    if not options:
        return None
    return "O" if cls == "L" and "O" in options else options[0]


def class_templates(n: int):
    """All letter/digit layouts of length n that an Indian plate can have, as (name, 'LLDD...') pairs."""
    out = []
    for d in (1, 2):
        s = n - 2 - d - 4
        if 0 <= s <= 3:
            out.append(("standard", "L" * 2 + "D" * d + "L" * s + "D" * 4))
    if n in (9, 10):
        out.append(("bh", "DD" + "LL" + "DDDD" + "L" * (n - 8)))
    return out


def best_template(text: str):
    """Pick the layout that best fits the classes of `text`. Ties go to the standard format."""
    best = None
    for name, tpl in class_templates(len(text)):
        score = sum(1 for c, k in zip(text, tpl) if c != "?" and char_class(c) == k)
        if text[2:4] == "BH" and name == "bh":
            score += 1
        if best is None or score > best[0]:
            best = (score, name, tpl)
    return (best[1], best[2]) if best else ("unknown", None)


def format_warnings(plate: str) -> list[str]:
    w = []
    if not (STANDARD.match(plate) or BH.match(plate)):
        w.append("does not fit the Indian plate format")
    st = plate[:2]
    if "?" not in st and not st.isdigit() and st not in STATE_CODES and not BH.match(plate):
        w.append(f"state code '{st}' not recognised")
    return w
