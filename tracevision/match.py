"""Registry matching and ranking (judged algorithm, PIPELINE.md section 6).

Ranks registry vehicles for one observed vehicle (fused plate with '?', colour, type) and returns the top K,
each with a **match score** (0-100, a heuristic ranking score, NOT a probability) and human-readable reasons.
The decision is one of: "match", "ambiguous" or "no_confident_match".

The answer key `evaluation/registry_decoy_map.csv` is never read here (DECISIONS E7).
"""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from math import sqrt
from pathlib import Path

from . import ROOT, load_config
from .plates import is_lookalike, normalise

NEAR_COLOURS = [{"white", "silver", "grey"}, {"red", "orange"}, {"brown", "orange", "yellow"}]
UNKNOWN = {"", "unknown", None}


def _type_rules():
    cm = json.loads((ROOT / "TRACEVISION_DATA/models/class_mapping.json").read_text(encoding="utf-8"))
    return [set(p) for p in cm.get("compatible_types", [])]


COMPATIBLE_TYPES = _type_rules()


@dataclass
class Candidate:
    rank: int
    synthetic_vehicle_id: str
    registration_number: str
    match_score: float
    plate_score: float
    colour_score: float | None
    type_score: float | None
    reasons: list = field(default_factory=list)


@dataclass
class MatchResult:
    decision: str                 # match | ambiguous | no_confident_match
    decision_reason: str
    query: dict
    candidates: list

    def to_dict(self):
        return asdict(self)


DEMO_REGISTRY = ROOT / "TRACEVISION_DATA/registry/synthetic_demo_registry.csv"
DEMO_LOCAL = ROOT / "runs/demo_registry/registry.csv"   # records made from uploads: local only, never committed


def load_registry(path=None, demo=None):
    """The main synthetic registry, plus the demo layer (DECISIONS M21) when `demo` is true or, by default, when
    config `registry.demo` is true. The evaluation always uses the main registry only (demo=False)."""
    path = path or ROOT / "TRACEVISION_DATA/registry/synthetic_vehicle_registry.csv"
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if demo is None:
        demo = bool(load_config().get("registry", {}).get("demo", False))
    if demo:
        for extra in (DEMO_REGISTRY, DEMO_LOCAL):
            if extra.exists():
                with open(extra, encoding="utf-8") as f:
                    rows += list(csv.DictReader(f))
    return rows


def is_demo(row) -> bool:
    return str(row.get("source", "")).startswith("demo_")


def plate_alignment(query: str, cand: str, lookalike_cost: float):
    """Weighted edit distance where '?' in the query matches anything for free.
    Returns (cost, exact, lookalike, mismatched_positions, gaps)."""
    n, m = len(query), len(cand)
    D = [[(0.0, 0, 0)] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        D[i][0] = (float(i), 0, 0)
    for j in range(1, m + 1):
        D[0][j] = (float(j), 0, 0)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            q, c = query[i - 1], cand[j - 1]
            if q == "?" or q == c:
                sub = (D[i - 1][j - 1][0], D[i - 1][j - 1][1] + (q != "?"), D[i - 1][j - 1][2])
            elif is_lookalike(q, c):
                sub = (D[i - 1][j - 1][0] + lookalike_cost, D[i - 1][j - 1][1], D[i - 1][j - 1][2] + 1)
            else:
                sub = (D[i - 1][j - 1][0] + 1, D[i - 1][j - 1][1], D[i - 1][j - 1][2])
            dele = (D[i - 1][j][0] + 1, D[i - 1][j][1], D[i - 1][j][2])
            ins = (D[i][j - 1][0] + 1, D[i][j - 1][1], D[i][j - 1][2])
            D[i][j] = min(sub, dele, ins, key=lambda x: (x[0], -x[1]))
    cost, exact, look = D[n][m]
    return cost, exact, look


def plate_score(query: str, cand: str, lookalike_cost: float):
    known = sum(1 for c in query if c != "?")
    if known == 0 or not cand:
        return 0.0, {"known": known, "exact": 0, "lookalike": 0, "cost": None}
    cost, exact, look = plate_alignment(query, cand, lookalike_cost)
    sim = max(0.0, 1.0 - cost / known)
    coverage = min(1.0, known / len(cand))
    # sim is squared: a full plate that disagrees in 2 characters must not outrank an exact plate
    # whose colour conflicts (plate evidence dominates identity). Design choice, not fitted to test cases.
    return (sim ** 2) * sqrt(coverage), {"known": known, "exact": exact, "lookalike": look, "cost": round(cost, 2),
                                  "sim": round(sim, 3), "coverage": round(coverage, 3)}


def colour_score(obs, reg):
    if obs in UNKNOWN or reg in UNKNOWN:
        return None
    if obs == reg:
        return 1.0
    if any(obs in g and reg in g for g in NEAR_COLOURS):
        return 0.5
    return 0.0


def type_score(obs, reg):
    if obs in UNKNOWN or reg in UNKNOWN:
        return None
    obs_set = set(obs.split("/"))          # "motorcycle/scooter" from UVH-26 matches either
    if reg in obs_set:
        return 1.0
    if any(reg in g and obs_set & g for g in COMPATIBLE_TYPES):
        return 0.5
    return 0.0


def _reasons(info, cs, ts, obs_colour, obs_type, row):
    r = []
    k = info["known"]
    if k == 0:
        r.append("no plate characters readable")
    else:
        unread = f"; {info.get('n_unknown', 0)} unreadable" if info.get("n_unknown") else ""
        r.append(f"plate: {info['exact']} of {k} readable characters match exactly" +
                 (f", {info['lookalike']} look-alike" if info["lookalike"] else "") + unread)
        if info.get("cost") and info["cost"] >= 1:
            r.append(f"plate differs from {row['registration_number']} (edit cost {info['cost']})")
    if cs is None:
        r.append("colour not compared (unknown)")
    else:
        r.append({1.0: f"colour {obs_colour} matches", 0.5: f"colour close: observed {obs_colour}, registry {row['vehicle_colour']}",
                  0.0: f"colour conflict: observed {obs_colour}, registry {row['vehicle_colour']}"}[cs])
    if ts is None:
        r.append("type not compared (unknown)")
    else:
        r.append({1.0: f"type {row['vehicle_type']} matches", 0.5: f"type compatible: observed {obs_type}, registry {row['vehicle_type']}",
                  0.0: f"type conflict: observed {obs_type}, registry {row['vehicle_type']}"}[ts])
    if is_demo(row):
        r.append("demo registry record (synthetic, not used in the evaluation)")
    return r


def match(plate: str, colour: str = "unknown", vtype: str = "unknown", registry=None, cfg=None) -> MatchResult:
    cfg = cfg or load_config()
    q, known, cands = rank(plate, colour, vtype, registry, cfg)
    return decide(q, colour, vtype, known, cands, cfg)


def rank(plate: str, colour: str = "unknown", vtype: str = "unknown", registry=None, cfg=None):
    """Score and rank registry vehicles (threshold-free). Returns (normalised plate, known chars, top-K candidates)."""
    cfg = (cfg or load_config())["match"]
    registry = load_registry() if registry is None else registry
    q = normalise(plate)
    w = cfg["weights"]
    known = sum(1 for c in q if c != "?")
    scored = []
    for row in registry:
        ps, info = plate_score(q, row["registration_number"], cfg["lookalike_cost"])
        info["n_unknown"] = q.count("?")
        if known >= cfg["min_known_for_match"] and info.get("sim", 0) < cfg["min_plate_sim_candidate"]:
            continue
        cs, ts = colour_score(colour, row["vehicle_colour"]), type_score(vtype, row["vehicle_type"])
        num, den = w["plate"] * ps, w["plate"]
        if cs is not None:
            num += w["colour"] * cs; den += w["colour"]
        if ts is not None:
            num += w["type"] * ts; den += w["type"]
        score = 100.0 * num / den
        scored.append((score, ps, cs, ts, row, info))
    scored.sort(key=lambda x: (-x[0], -x[1], x[4]["synthetic_vehicle_id"]))
    top = scored[:cfg["top_k"]]
    cands = [Candidate(i + 1, row["synthetic_vehicle_id"], row["registration_number"], round(s, 1), round(ps, 3),
                       cs, ts, _reasons(info, cs, ts, colour, vtype, row))
             for i, (s, ps, cs, ts, row, info) in enumerate(top)]
    return q, known, cands


def decide(q, colour, vtype, known, cands, cfg=None) -> MatchResult:
    """Apply the decision rules (thresholds) to ranked candidates."""
    cfg = (cfg or load_config())["match"]
    if not cands:
        decision, why = "no_confident_match", "no registry vehicle is close to the observed plate"
    elif known < cfg["min_known_for_match"]:
        # too little plate evidence: this is "can't tell", not "several plausible candidates"
        decision, why = ("no_confident_match",
                         f"only {known} plate character(s) readable; at least {cfg['min_known_for_match']} are needed for a confident match")
    elif cands[0].match_score < cfg["t_abs"]:
        decision, why = "no_confident_match", f"best match score {cands[0].match_score} is below the threshold {cfg['t_abs']}"
    elif len(cands) > 1 and cands[0].match_score - cands[1].match_score < cfg["t_margin"]:
        decision, why = "ambiguous", (f"top two candidates are too close ({cands[0].match_score} against "
                                      f"{cands[1].match_score}, margin under {cfg['t_margin']})")
    else:
        decision, why = "match", f"best match score {cands[0].match_score}, clear of the next candidate"
    return MatchResult(decision, why, {"plate": q, "colour": colour, "type": vtype, "known_chars": known}, cands)
