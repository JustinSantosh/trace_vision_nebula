"""Calibrate the matcher's decision thresholds (t_abs, t_margin) on the synthetic registry test cases.

Split by anchor vehicle (every 2nd anchor -> calibration, the rest -> holdout) so that no anchor's cases are used
both to tune and to report. The tuned values are reported on the HOLDOUT split; the calibration score is shown
only for reference.

Correct means:
  expected match:<id>  -> decision == "match" and rank-1 == <id>
  expected ambiguous   -> decision != "match" (a confident single answer would be wrong)
  expected no_match    -> decision == "no_confident_match"

Usage:  python -m tracevision.calibrate [--write-config]
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict

import yaml

from . import PACKAGE_DIR, ROOT, load_config
from .match import decide, load_registry, rank

CASES = ROOT / "TRACEVISION_DATA/evaluation/registry_test_cases.csv"
REPORT = ROOT / "TRACEVISION_DATA/reports/p3_match_calibration.json"


def load_cases():
    with open(CASES, encoding="utf-8") as f:
        cases = [c for c in csv.DictReader(f) if c["case_source"] == "synthetic_query"]
    anchors = sorted({c["expected_candidates"].split(";")[0] for c in cases if c["expected_candidates"]})
    calib_anchors = set(anchors[0::2])
    split, nm = {}, 0
    for c in cases:
        a = c["expected_candidates"].split(";")[0] if c["expected_candidates"] else None
        if a is None:
            split[c["case_id"]] = "calib" if nm % 2 == 0 else "holdout"; nm += 1
        else:
            split[c["case_id"]] = "calib" if a in calib_anchors else "holdout"
    return cases, split


def correct(case, res):
    exp = case["expected_outcome"]
    if exp.startswith("match:"):
        return res.decision == "match" and res.candidates and res.candidates[0].synthetic_vehicle_id == exp.split(":", 1)[1]
    if exp == "ambiguous":
        return res.decision != "match"
    return res.decision == "no_confident_match"


PRE_CALIBRATION = {"t_abs": 75.0, "t_margin": 5.0}   # hand-set design values before calibration


def _with(cfg, **match_overrides):
    c = json.loads(json.dumps(cfg)); c["match"].update(match_overrides); return c


_RANKED = {}


def _ranked(c, cfg, registry):
    # ranking does not depend on t_abs / t_margin, so it is computed once per case
    if c["case_id"] not in _RANKED:
        _RANKED[c["case_id"]] = rank(c["query_plate"], c["query_colour"], c["query_type"], registry=registry, cfg=cfg)
    return _RANKED[c["case_id"]]


def evaluate(cases, ids, cfg, registry):
    per = defaultdict(lambda: [0, 0]); by_scen = defaultdict(lambda: [0, 0]); top1 = top5 = nmatch = 0; wrong = []
    for c in cases:
        if c["case_id"] not in ids:
            continue
        q, known, cands = _ranked(c, cfg, registry)
        r = decide(q, c["query_colour"], c["query_type"], known, cands, cfg)
        kind = c["expected_outcome"].split(":")[0]
        ok = correct(c, r)
        per[kind][0] += ok; per[kind][1] += 1
        by_scen[c["scenario"]][0] += ok; by_scen[c["scenario"]][1] += 1
        if kind == "match":
            nmatch += 1
            ids_ = [x.synthetic_vehicle_id for x in r.candidates]
            tgt = c["expected_outcome"].split(":", 1)[1]
            top1 += bool(ids_) and ids_[0] == tgt; top5 += tgt in ids_
        if not ok:
            wrong.append({"case": c["case_id"], "scenario": c["scenario"], "query": c["query_plate"], "expected": c["expected_outcome"],
                          "got": r.decision, "top": [(x.synthetic_vehicle_id, x.match_score) for x in r.candidates[:3]]})
    acc = {k: round(v[0] / v[1], 3) for k, v in per.items()}
    return {"balanced_accuracy": round(sum(acc.values()) / len(acc), 3) if acc else 0, "accuracy_by_expected": acc,
            "counts_by_expected": {k: v[1] for k, v in per.items()},
            "accuracy_by_scenario": {k: f"{v[0]}/{v[1]}" for k, v in sorted(by_scen.items())},
            "match_cases_top1": f"{top1}/{nmatch}", "match_cases_top5": f"{top5}/{nmatch}", "errors": wrong}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-config", action="store_true")
    a = ap.parse_args()
    base = load_config(); registry = load_registry(demo=False); cases, split = load_cases()
    calib = {k for k, v in split.items() if v == "calib"}; hold = {k for k, v in split.items() if v == "holdout"}
    grid = []
    for t_abs in [x / 2 for x in range(100, 181, 5)]:          # 50 .. 90 step 2.5
        for t_margin in [float(x) for x in range(0, 21)]:       # 0 .. 20
            cfg = json.loads(json.dumps(base)); cfg["match"]["t_abs"] = t_abs; cfg["match"]["t_margin"] = t_margin
            grid.append((evaluate(cases, calib, cfg, registry)["balanced_accuracy"], t_abs, t_margin))
    best_score = max(g[0] for g in grid)
    plateau = [g for g in grid if g[0] == best_score]
    # pick the centre of the best plateau (robust), not an edge
    plateau.sort(key=lambda g: (g[1], g[2]))
    _, t_abs, t_margin = plateau[len(plateau) // 2]
    cfg = json.loads(json.dumps(base)); cfg["match"]["t_abs"] = t_abs; cfg["match"]["t_margin"] = t_margin
    out = {"cases": len(cases), "calib_cases": len(calib), "holdout_cases": len(hold),
           "grid": {"t_abs": "50..90 step 2.5", "t_margin": "0..20 step 1", "objective": "balanced accuracy on calibration split"},
           "best_calibration_balanced_accuracy": best_score, "plateau_size": len(plateau),
           "chosen": {"t_abs": t_abs, "t_margin": t_margin},
           "calibration": evaluate(cases, calib, cfg, registry), "holdout": evaluate(cases, hold, cfg, registry),
           # fixed hand-set starting values (from the design), so the report is identical on every rerun
           "before_calibration_defaults": {**PRE_CALIBRATION, "holdout": evaluate(cases, hold, _with(base, **PRE_CALIBRATION), registry)["balanced_accuracy"]}}
    REPORT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("chosen", "best_calibration_balanced_accuracy", "plateau_size")}))
    for s in ("calibration", "holdout"):
        o = out[s]; print(s, o["balanced_accuracy"], o["accuracy_by_expected"], o["counts_by_expected"], "top1", o["match_cases_top1"], "top5", o["match_cases_top5"])
    print("holdout errors:"); [print("  ", e) for e in out["holdout"]["errors"]]
    if a.write_config:
        p = PACKAGE_DIR / "config.yaml"; txt = p.read_text(encoding="utf-8")
        import re
        txt = re.sub(r"t_abs: [0-9.]+", f"t_abs: {t_abs}", txt); txt = re.sub(r"t_margin: [0-9.]+", f"t_margin: {t_margin}", txt)
        p.write_text(txt, encoding="utf-8"); print("config.yaml updated")


if __name__ == "__main__":
    main()
