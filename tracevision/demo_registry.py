"""Synthetic DEMO registry layer (DECISIONS M21): possible matches for every partly or fully read plate.

The main registry deliberately leaves unregistered clip vehicles out (that is what the evaluation's "no false
identification" check rests on), so most read plates in a demo found no candidates at all. This layer adds
fictional records the app matches against as well; the evaluation never uses it (each result keeps the
main-registry answer in `main_registry`).

  * demo_seed / demo_decoy  stored clips only: the human label's plate for every labelled vehicle that is NOT in the
                            main registry, plus 4 look-alike plates around it
  * demo_possible           any clip, uploads included (runs/jobs is never committed, so their records are local): for a plate read with >= MIN_KNOWN characters that no
                            registry record agrees with, 5 fictional plates that agree with every READ character
                            (a fully read plate: 5 plates one character off). Two of them share the observed colour
                            and type, so the top two tie and the answer stays "ambiguous": a ranked list of
                            possible matches, never a confident identification.

Every record is synthetic, marked `source = demo_*`, and shown with the reason "demo registry record".
`extend_for_result` runs after every analysis (api worker) and `build_all` regenerates the layer for the stored clips:

    python -m tracevision.demo_registry          # stored clips: rebuild the layer, owner records, re-rank, reports
"""
from __future__ import annotations

import csv
import importlib.util
import json
import random
import string
import threading
from collections import Counter
from pathlib import Path

from . import ROOT, load_config
from .match import DEMO_LOCAL, decide, is_demo, load_registry, rank

DATA = ROOT / "TRACEVISION_DATA"
MAIN = DATA / "registry" / "synthetic_vehicle_registry.csv"
DEMO = DATA / "registry" / "synthetic_demo_registry.csv"
LABELS = DATA / "evaluation" / "test_clip_labels.csv"
FIELDS = ["synthetic_vehicle_id", "registration_number", "state_code", "vehicle_type", "vehicle_colour",
          "manufacturer", "model", "model_year", "source", "synthetic"]
MIN_KNOWN = 5
COLOURS = ["white", "silver", "grey", "black", "red", "blue", "brown"]
TYPES = ["car", "SUV", "motorcycle", "scooter", "truck", "bus", "auto_rickshaw"]
MAKES = {"car": ("Maruti Suzuki", "Swift"), "SUV": ("Hyundai", "Creta"), "motorcycle": ("Hero", "Splendor Plus"),
         "scooter": ("Honda", "Activa 6G"), "truck": ("Tata", "Ultra 1918"), "bus": ("Ashok Leyland", "Viking"),
         "auto_rickshaw": ("Bajaj", "RE"), "van": ("Maruti Suzuki", "Eeco")}
TYPE_MAP = {"motorcycle/scooter": "motorcycle", "unknown": "car", "bicycle": "motorcycle", "lcv": "truck"}
SEED = 2026
_lock = threading.Lock()


# ---------------------------------------------------------------- plate helpers
def is_letter_pos(plate: str, i: int) -> bool:
    """Indian format SS DD L..L DDDD: first two and the middle are letters, the rest digits."""
    return i < 2 or (4 <= i < len(plate) - 4)


def fill(rng, plate: str) -> str:
    return "".join((rng.choice(string.ascii_uppercase) if is_letter_pos(plate, i) else rng.choice(string.digits))
                   if c == "?" else c for i, c in enumerate(plate))


def mutate(rng, plate: str, k: int, positions=None) -> str:
    p = list(plate)
    for i in positions or rng.sample(range(2, len(p)), k):
        pool = string.ascii_uppercase if p[i].isalpha() else string.digits
        p[i] = rng.choice([c for c in pool if c != p[i]])
    return "".join(p)


def agrees(q: str, plate: str) -> bool:
    return len(q) == len(plate) and all(a == "?" or a == b for a, b in zip(q, plate))


def _row(rid, plate, vtype, colour, source, rng):
    vtype = TYPE_MAP.get(vtype, vtype)
    make, model = MAKES.get(vtype, MAKES["car"])
    return {"synthetic_vehicle_id": rid, "registration_number": plate, "state_code": plate[:2], "vehicle_type": vtype,
            "vehicle_colour": colour, "manufacturer": make, "model": model, "model_year": str(rng.randint(2010, 2025)),
            "source": source, "synthetic": "true"}


def _read(path):
    return list(csv.DictReader(open(path, encoding="utf-8"))) if path.exists() else []


class _Builder:
    def __init__(self, existing):
        self.main = _read(MAIN)
        self.rows = list(existing)
        self.taken = {r["registration_number"] for r in self.main + self.rows}
        self.n = max([int(r["synthetic_vehicle_id"][2:]) for r in self.rows] + [0])

    def add(self, plate, vtype, colour, source, rng):
        if plate in self.taken or "?" in plate:
            return None
        self.taken.add(plate)
        self.n += 1
        r = _row(f"SD{self.n:05d}", plate, vtype, colour, source, rng)
        self.rows.append(r)
        return r

    def covered(self, q: str) -> bool:
        """Something already answers this read: a record agreeing with every read character, or, for a fully read
        plate, the plate itself or a record one character off (so re-uploading a clip adds nothing new)."""
        if "?" in q:
            return any(agrees(q, r["registration_number"]) for r in self.main + self.rows)
        return q in self.taken or any(len(r["registration_number"]) == len(q) and
                                      sum(a != b for a, b in zip(q, r["registration_number"])) <= 1
                                      for r in self.main + self.rows)

    def possible(self, q: str, vtype: str, colour: str, key: str) -> int:
        """5 fictional possible matches for a read plate (see module doc). Returns how many were added."""
        rng = random.Random(f"{SEED}:{key}:{q}")
        colour = colour if colour in COLOURS else "white"
        styles = [(colour, vtype), (colour, vtype), (colour, rng.choice(TYPES)),
                  (rng.choice([x for x in COLOURS if x != colour]), vtype),
                  (rng.choice([x for x in COLOURS if x != colour]), rng.choice(TYPES))]
        free = list(range(2, len(q)))
        rng.shuffle(free)
        added = 0
        for k, (c, t) in enumerate(styles):
            for _ in range(30):
                plate = fill(rng, q) if "?" in q else mutate(rng, q, 1, [free[k % len(free)]] if free else None)
                if self.add(plate, t, c, "demo_possible", rng):
                    added += 1
                    break
        return added


def _readable(q: str) -> bool:
    return bool(q) and sum(c != "?" for c in q) >= MIN_KNOWN


# ---------------------------------------------------------------- write + owner records + re-rank
def _write(rows, path=DEMO):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def _owner_records():
    """Owner records + e-challans for every registry vehicle, the demo layer included (per-vehicle seeded streams,
    so existing vehicles keep exactly the records they had)."""
    gvi = _gvi()
    owners, challans = gvi.build(SEED)
    gvi.write(gvi.OWNERS, owners)
    gvi.write(gvi.CHALLANS, challans)


def _gvi():
    spec = importlib.util.spec_from_file_location("gvi", DATA / "scripts" / "generate_vehicle_intel.py")
    gvi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gvi)
    return gvi


def _local_owner_records(rows):
    """Owner records + e-challans for the upload-made records, kept beside them in runs/demo_registry/."""
    gvi = _gvi()
    owners, challans = gvi.build(SEED, rows)
    gvi.write(DEMO_LOCAL.parent / "owners.csv", owners)
    gvi.write(DEMO_LOCAL.parent / "challans.csv", challans)


def rerank(run_dir: Path, cfg=None) -> int:
    """Re-match every read plate of one run against the current registry (main + demo). The main-registry answer
    (`main_registry`, used by the evaluation) is kept, or computed if missing. Returns vehicles changed."""
    cfg = cfg or load_config()
    p = Path(run_dir) / "result.json"
    res = json.loads(p.read_text(encoding="utf-8"))
    reg = load_registry()
    main = [r for r in reg if not is_demo(r)]
    changed = 0
    for v in res["vehicles"]:
        q = v["plate"].get("fused") or ""
        if not q.strip("?"):
            continue
        vtype, colour = v["type"]["label"], v["colour"]["label"]
        if "main_registry" not in v:
            q2, k2, c2 = rank(q, colour, vtype, main, cfg)
            m2 = decide(q2, colour, vtype, k2, c2, cfg)
            v["main_registry"] = {"decision": m2.decision, "candidates": [c.synthetic_vehicle_id for c in m2.candidates]}
        qq, known, cands = rank(q, colour, vtype, reg, cfg)
        m = decide(qq, colour, vtype, known, cands, cfg)
        new = [c.__dict__ for c in m.candidates]
        if new != v["candidates"] or m.decision != v["decision"]:
            changed += 1
        v.update(decision=m.decision, decision_reason=m.decision_reason, candidates=new)
    res["summary"]["decisions"] = dict(Counter(v["decision"] for v in res["vehicles"]))
    p.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    return changed


def extend_for_result(run_dir: Path, key: str | None = None) -> dict:
    """After an analysis: add possible-match records for its read plates that nothing in the registry agrees with,
    refresh owner records, and re-rank the run. Safe to call more than once."""
    run_dir = Path(run_dir)
    res = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    key = key or run_dir.name
    with _lock:
        committed = _read(DEMO)
        b = _Builder(committed + _read(DEMO_LOCAL))
        before = len(b.rows)
        for v in res["vehicles"]:
            q = v["plate"].get("fused") or ""
            if v.get("decision") == "match" or not _readable(q) or b.covered(q):
                continue
            b.possible(q, v["type"]["label"], v["colour"]["label"], f"{key}:{v['track_id']}")
        added = len(b.rows) - before
        if added:   # uploads only ever add to the LOCAL file (never committed)
            local = b.rows[len(committed):]
            _write(local, DEMO_LOCAL)
            _local_owner_records(local)
    changed = rerank(run_dir)
    return {"records_added": added, "vehicles_rematched": changed}


def build_all() -> dict:
    """Stored clips: rebuild the whole layer (label seeds + decoys, then possible matches for every stored clip)."""
    b = _Builder([])
    for lab in _read(LABELS):
        plate = (lab.get("plate_text_truth") or "").strip().upper()
        if lab["in_registry"] != "no" or not plate or "?" in plate or plate in b.taken:
            continue
        rng = random.Random(f"{SEED}:{plate}")
        vtype, colour = lab["vehicle_type"] or "car", lab["colour"] or "white"
        b.add(plate, vtype, colour, "demo_seed", rng)
        others_c = [c for c in COLOURS if c != colour]
        others_t = [t for t in TYPES if t != TYPE_MAP.get(vtype, vtype)]
        for k, (c, t) in enumerate([(colour, vtype), (rng.choice(others_c), vtype), (colour, rng.choice(others_t)),
                                    (rng.choice(others_c), vtype)]):
            for _ in range(20):
                if b.add(mutate(rng, plate, 1 + k % 3), t, c, "demo_decoy", rng):
                    break
    stored = sorted(ROOT.glob("runs/clip*/result.json"))
    jobs = sorted(ROOT.glob("runs/jobs/*/result.json"), key=lambda p: p.stat().st_mtime)
    for p in stored:
        res = json.loads(p.read_text(encoding="utf-8"))
        for v in res["vehicles"]:
            q = v["plate"].get("fused") or ""
            if v.get("main_registry", {}).get("decision", v.get("decision")) == "match" or not _readable(q) or b.covered(q):
                continue
            b.possible(q, v["type"]["label"], v["colour"]["label"], f"{p.parent.name}:{v['track_id']}")
    _write(b.rows)
    _owner_records()
    # uploads: rebuilt into the local file from scratch, on top of the committed layer
    n_committed = len(b.rows)
    for p in jobs:
        res = json.loads(p.read_text(encoding="utf-8"))
        for v in res["vehicles"]:
            q = v["plate"].get("fused") or ""
            if v.get("main_registry", {}).get("decision", v.get("decision")) == "match" or not _readable(q) or b.covered(q):
                continue
            b.possible(q, v["type"]["label"], v["colour"]["label"], f"{p.parent.name}:{v['track_id']}")
    local = b.rows[n_committed:]
    _write(local, DEMO_LOCAL)
    _local_owner_records(local)
    changed = {f"{p.parent.parent.name}/{p.parent.name}": rerank(p.parent) for p in stored + jobs}
    return {"committed": dict(Counter(r["source"] for r in b.rows[:n_committed])), "local_uploads": len(local),
            "rematched": changed}


if __name__ == "__main__":
    out = build_all()
    from .report import build
    for p in sorted(ROOT.glob("runs/clip*/result.json")):
        build(p.parent)
    for p in sorted(ROOT.glob("runs/jobs/*/result.json")):
        build(p.parent, deliver=False)
    print(json.dumps(out, indent=1))
