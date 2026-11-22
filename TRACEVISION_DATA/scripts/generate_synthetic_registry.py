#!/usr/bin/env python
"""Phase 0F - seeded, reproducible SYNTHETIC vehicle registry plus registry test cases.

Privacy: every record is fictional and marked synthetic = true. Plates of evaluation-clip vehicles appear
ONLY as `source = evaluation_seed` rows (their make / model / year / id are fictional unless the label says
the make/model is verified). No owner names, phones or addresses exist anywhere. This registry is NOT
connected to any government database.

Records
  * base fictional vehicles (realistic Indian state codes, weighted to CG and its neighbours)
  * anchors: every labelled vehicle with in_registry = yes (evaluation_seed). Without labels yet, a few
    FICTIONAL anchors are created instead so the matcher can be built now (re-run after labelling).
  * decoys around every anchor (all fictional) for the spec's cases:
      partial plate match (2 chars differ) · candidates differing only at the query's unknown positions ·
      within-class confusable plates (O/D/Q, B/R/P, I/T/L, 8/6/3/0, 5/6, 2/7, 1/7) · same colour + near plate
      but different type · same make/model/colour/type ("similar-looking") with a different plate
  * vehicles labelled in_registry = no are guaranteed absent (and > 2 edits from every registry plate)

Outputs
  registry/synthetic_vehicle_registry.csv  (spec fields only - nothing that leaks the answer)
  evaluation/registry_test_cases.csv       clip cases (query filled by the pipeline at run time) +
                                           synthetic query cases with the expected outcome per scenario
  evaluation/registry_decoy_map.csv        which decoy was built against which anchor and why (eval only)
  reports/synthetic_registry_stats.json

Expected outcomes are written as  match:<synthetic_vehicle_id> | no_match | ambiguous  (ambiguous =
several plausible candidates, a confident single answer would be wrong). Scores are "match scores", not
probabilities.

Deps   standard library only
Usage
  python TRACEVISION_DATA/scripts/generate_synthetic_registry.py --n-base 30 --out-registry <tmp> ...   # smoke test
  python TRACEVISION_DATA/scripts/generate_synthetic_registry.py                                         # uses evaluation/test_clip_labels.csv if present
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import string
from collections import Counter
from pathlib import Path

STATES = (["CG"] * 8 + ["MP", "MH", "OD", "JH", "UP", "TG", "AP"] * 3 +
          ["DL", "KA", "TN", "KL", "HR", "RJ", "GJ", "WB", "BR", "PB", "AS", "UK", "HP", "GA"])
COLOURS = ["white", "white", "white", "silver", "silver", "grey", "black", "red", "blue", "brown", "green", "yellow", "orange"]
MAKES = {
    "car": [("Maruti Suzuki", "Swift"), ("Maruti Suzuki", "Baleno"), ("Maruti Suzuki", "Dzire"), ("Hyundai", "i20"),
            ("Hyundai", "Grand i10"), ("Tata", "Tiago"), ("Honda", "City"), ("Tata", "Altroz")],
    "SUV": [("Mahindra", "Scorpio"), ("Hyundai", "Creta"), ("Tata", "Nexon"), ("Kia", "Seltos"), ("Mahindra", "XUV700"),
            ("Toyota", "Fortuner"), ("Maruti Suzuki", "Brezza")],
    "motorcycle": [("Hero", "Splendor Plus"), ("Bajaj", "Pulsar 150"), ("Honda", "Shine"), ("Royal Enfield", "Classic 350"), ("TVS", "Apache RTR 160")],
    "scooter": [("Honda", "Activa 6G"), ("TVS", "Jupiter"), ("Suzuki", "Access 125"), ("Ola", "S1")],
    "auto_rickshaw": [("Bajaj", "RE"), ("Piaggio", "Ape City"), ("Mahindra", "Treo")],
    "truck": [("Tata", "Ultra 1918"), ("Ashok Leyland", "Ecomet"), ("Eicher", "Pro 2049"), ("BharatBenz", "1617R")],
    "bus": [("Tata", "Starbus"), ("Ashok Leyland", "Viking"), ("Eicher", "Skyline")],
    "van": [("Maruti Suzuki", "Eeco"), ("Force", "Traveller")],
}
TYPE_W = {"car": 30, "SUV": 18, "motorcycle": 20, "scooter": 12, "auto_rickshaw": 7, "truck": 6, "bus": 3, "van": 4}
TYPE_COLOURS = {"auto_rickshaw": ["green", "yellow", "black"], "bus": ["white", "red", "blue", "yellow"],
                "truck": ["orange", "yellow", "white", "blue"]}
LET_CONF = {"O": "DQ", "D": "O", "Q": "O", "B": "RP", "R": "BP", "P": "R", "I": "TL", "T": "I", "L": "I",
            "S": "", "Z": "", "C": "G", "G": "C", "M": "N", "N": "M", "V": "U", "U": "V", "E": "F", "F": "E", "H": "K", "K": "H"}
DIG_CONF = {"8": "630", "6": "85", "3": "8", "0": "86", "5": "6", "2": "7", "1": "7", "7": "12", "9": "8", "4": "1"}
X_CLASS = {"0": "O", "O": "0", "1": "I", "I": "1", "8": "B", "B": "8", "5": "S", "S": "5", "2": "Z", "Z": "2", "D": "0"}
REG_COLS = ["synthetic_vehicle_id", "registration_number", "state_code", "vehicle_type", "vehicle_colour",
            "manufacturer", "model", "model_year", "source", "synthetic"]
CASE_COLS = ["case_id", "case_source", "scenario", "clip_id", "target_vehicle_id", "query_plate", "query_colour",
             "query_type", "expected_outcome", "expected_candidates", "notes"]


def is_digit_pos(plate, i):
    return plate[i].isdigit()


def lev(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


class Gen:
    def __init__(self, seed):
        self.r = random.Random(seed)
        self.plates = set()
        self.rows = []
        self.blocked = []  # plates that must stay absent (in_registry = no)
        self.ids = set()

    def plate(self, state=None):
        r = self.r
        while True:
            st = state or r.choice(STATES)
            if r.random() < 0.04:
                p = f"{r.randint(21, 26)}BH{r.randint(0, 9999):04d}{''.join(r.choices('ABCDEFGHJKLMNPRSTUVWXYZ', k=r.choice([1, 2])))}"
            else:
                series = "".join(r.choices("ABCDEFGHJKLMNPRSTUVWXYZ", k=r.choice([1, 2, 2, 2])))
                p = f"{st}{r.randint(1, 35 if st != 'CG' else 30):02d}{series}{r.randint(1, 9999):04d}"
            if self.ok(p):
                return p

    def ok(self, p, min_dist_blocked=3):
        return p not in self.plates and all(lev(p, b) >= min_dist_blocked for b in self.blocked)

    def add(self, plate, vtype, colour, make=None, model=None, source="fictional", year=None):
        r = self.r
        if make is None:
            make, model = r.choice(MAKES.get(vtype, MAKES["car"]))
        while True:  # random ids: creation order (anchors first) must not be readable from the id
            rid = f"SV{r.randint(0, 999999):06d}"
            if rid not in self.ids:
                break
        self.ids.add(rid)
        st = plate[:2] if plate[:2].isalpha() else "BH"
        self.rows.append({"synthetic_vehicle_id": rid, "registration_number": plate, "state_code": st,
                          "vehicle_type": vtype, "vehicle_colour": colour, "manufacturer": make, "model": model,
                          "model_year": year or r.randint(2008, 2025), "source": source, "synthetic": "true"})
        self.plates.add(plate)
        return rid

    def rand_vehicle(self):
        t = self.r.choices(list(TYPE_W), weights=list(TYPE_W.values()))[0]
        return t, self.r.choice(TYPE_COLOURS.get(t, COLOURS))

    def mutate(self, plate, positions, confusable=False):
        p = list(plate)
        for i in positions:
            ch = p[i]
            if confusable:
                pool = (DIG_CONF if ch.isdigit() else LET_CONF).get(ch, "")
                if pool:
                    p[i] = self.r.choice(pool); continue
            pool = string.digits if ch.isdigit() else "ABCDEFGHJKLMNPRSTUVWXYZ"
            p[i] = self.r.choice([c for c in pool if c != ch])
        return "".join(p)

    def variant(self, plate, positions, confusable=False, tries=200):
        for _ in range(tries):
            q = self.mutate(plate, positions, confusable)
            if q != plate and self.ok(q):
                return q
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", default="TRACEVISION_DATA/evaluation/test_clip_labels.csv")
    ap.add_argument("--out-registry", default="TRACEVISION_DATA/registry/synthetic_vehicle_registry.csv")
    ap.add_argument("--out-cases", default="TRACEVISION_DATA/evaluation/registry_test_cases.csv")
    ap.add_argument("--out-decoys", default="TRACEVISION_DATA/evaluation/registry_decoy_map.csv")
    ap.add_argument("--out-stats", default="TRACEVISION_DATA/reports/synthetic_registry_stats.json")
    ap.add_argument("--n-base", type=int, default=250, help="plain fictional background vehicles")
    ap.add_argument("--fictional-anchors", type=int, default=12, help="anchors to create when there are no labels yet")
    ap.add_argument("--seed", type=int, default=20261122)
    a = ap.parse_args()
    g = Gen(a.seed)

    labels = []
    if Path(a.labels).exists():
        with open(a.labels, newline="", encoding="utf-8-sig") as f:
            labels = [{k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f) if (r.get("target_vehicle_id") or "").strip()]
    mode = "evaluation_seeded" if labels else "fictional_only"
    for r in labels:  # block no-match vehicles first
        if r.get("in_registry") == "no" and r.get("plate_text_truth"):
            g.blocked.append(r["plate_text_truth"])  # '?' never matches a real char, so distance stays conservative

    anchors, skipped = [], []
    for r in labels:
        if r.get("in_registry") != "yes":
            continue
        plate = r.get("plate_text_truth", "")
        full = plate if plate and "?" not in plate else r.get("registry_plate_full", "")
        if not full:
            skipped.append(r["target_vehicle_id"]); continue
        verified = "verified" in r.get("notes", "").lower()
        if full in g.plates:  # same vehicle in two clips (cross-camera) -> one registry row
            rid = next(x["synthetic_vehicle_id"] for x in g.rows if x["registration_number"] == full)
        else:
            rid = g.add(full, r.get("vehicle_type") or "car", r.get("colour") or "unknown",
                        r.get("make") if verified and r.get("make") else None,
                        r.get("model") if verified and r.get("model") else None, source="evaluation_seed")
        anchors.append({"rid": rid, "plate": full, "type": r.get("vehicle_type") or "car", "colour": r.get("colour") or "unknown",
                        "clip_id": r["clip_id"], "tvid": r["target_vehicle_id"], "query_plate_truth": plate})
    if not labels:
        for _ in range(a.fictional_anchors):
            t, c = g.rand_vehicle()
            p = g.plate(state=g.r.choice(["CG", "CG", "MP", "MH", "OD"]))
            anchors.append({"rid": g.add(p, t, c), "plate": p, "type": t, "colour": c, "clip_id": "", "tvid": "", "query_plate_truth": ""})

    decoys, cases = [], []
    def case(scen, qp, qc, qt, outcome, cands, notes="", src="synthetic_query", clip="", tv=""):
        cases.append({"case_id": f"RC{len(cases) + 1:04d}", "case_source": src, "scenario": scen, "clip_id": clip,
                      "target_vehicle_id": tv, "query_plate": qp, "query_colour": qc, "query_type": qt,
                      "expected_outcome": outcome, "expected_candidates": ";".join(cands), "notes": notes})

    seen_anchor = set()
    for an in anchors:
        if an["rid"] in seen_anchor:
            continue
        seen_anchor.add(an["rid"])
        P, t, c, rid = an["plate"], an["type"], an["colour"], an["rid"]
        n = len(P)
        def dec(kind, plate, vt, col, mk=None, mdl=None):
            if plate is None:
                return None
            d = g.add(plate, vt, col, mk, mdl)
            decoys.append({"anchor_id": rid, "decoy_id": d, "kind": kind, "plate": plate})
            return d
        tail = list(range(n - 4, n))
        # partial plate match: 2 characters differ, same type/colour
        d_partial = dec("partial_2chars", g.variant(P, g.r.sample(range(2, n), 2)), t, c)
        # unknown positions: decoy differs ONLY at the two positions the query will hide
        hid = g.r.sample(tail, 2)
        alt_col = g.r.choice([x for x in COLOURS if x != c])
        d_hidden = dec("differs_only_at_unknown_positions", g.variant(P, hid), t, alt_col)
        # confusable candidate (within class, registry plates stay valid)
        conf_pos = [i for i in range(2, n) if (DIG_CONF if P[i].isdigit() else LET_CONF).get(P[i])]
        d_conf = dec("confusable_1char", g.variant(P, [g.r.choice(conf_pos)], confusable=True) if conf_pos else None, t, c)
        # similar colour, different type, near plate
        other_t = g.r.choice([x for x in TYPE_W if x != t])
        d_type = dec("same_colour_other_type", g.variant(P, [g.r.choice(tail)]), other_t, c)
        # similar-looking vehicles: same make/model/colour/type, different plate (2 of them)
        same = next(x for x in g.rows if x["synthetic_vehicle_id"] == rid)
        look = [dec("similar_looking", g.plate(state=P[:2] if P[:2].isalpha() else None), t, c, same["manufacturer"], same["model"]) for _ in range(2)]

        q_hidden = "".join("?" if i in hid else ch for i, ch in enumerate(P))
        case("exact_match", P, c, t, f"match:{rid}", [rid])
        if d_partial:
            case("partial_plate_match", P[:-3] + "???", c, t, f"match:{rid}", [rid, d_partial],
                 "last 3 unknown; type+colour should rank the anchor first, the partial decoy may rank high")
        if d_hidden:
            case("unknown_characters", q_hidden, c, t, f"match:{rid}", [rid, d_hidden],
                 "decoy fits every known character; only colour separates them")
            case("unknown_characters_no_colour", q_hidden, "unknown", t, "ambiguous", [rid, d_hidden],
                 "plate alone cannot separate anchor and decoy -> should not claim a confident single match")
        xpos = [i for i in range(n) if P[i] in X_CLASS]
        if xpos:
            i = g.r.choice(xpos)
            q = P[:i] + X_CLASS[P[i]] + P[i + 1:]
            case("cross_class_ocr_confusion", q, c, t, f"match:{rid}", [rid] + ([d_conf] if d_conf else []),
                 f"query has {P[i]}->{X_CLASS[P[i]]} at position {i + 1}; look-alike credit should recover the anchor")
        if d_conf:
            case("confusable_candidates", P, c, t, f"match:{rid}", [rid, d_conf], "exact plate must beat its confusable twin")
        case("conflicting_colour", P, alt_col if alt_col != c else "black", t, f"match:{rid}", [rid],
             "plate is exact, colour disagrees -> still the anchor, with a colour-conflict reason and a lower match score")
        if d_type:
            case("similar_colour_different_type", P[:-2] + "??", c, t, f"match:{rid}", [rid, d_type],
                 "decoy shares colour and nearly the plate but is a different type")
        lk = [x for x in look if x]
        if lk:
            case("similar_looking_vehicles", P[:2] + "?" * (n - 2), c, t, "ambiguous", [rid] + lk,
                 "only the state code is readable; several identical-looking vehicles -> no confident single match")
        case("multiple_plausible", "?" * (n - 4) + P[-4:], "unknown", "unknown",
             "ambiguous", [rid] + [x["synthetic_vehicle_id"] for x in g.rows if x["registration_number"].endswith(P[-4:]) and x["synthetic_vehicle_id"] != rid],
             "only the last 4 digits are known")

    for _ in range(a.n_base):
        t, c = g.rand_vehicle()
        g.add(g.plate(), t, c)

    # no-match synthetic queries (valid plates far from every registry plate)
    for _ in range(max(3, len(seen_anchor) // 3)):
        for _ in range(500):
            q = g.plate()
            if all(lev(q, p) >= 3 for p in g.plates):
                break
        g.plates.discard(q)  # g.plate() does not register; keep it absent
        t, c = g.rand_vehicle()
        case("no_matching_entry", q, c, t, "no_match", [], "plate is >= 3 edits from every registry plate")

    # clip cases: the pipeline fills the query at run time
    for r in labels:
        an = next((x for x in anchors if x["tvid"] == r["target_vehicle_id"]), None)
        if r.get("in_registry") == "no":
            outcome, cands = "no_match", []
        elif an:
            outcome, cands = f"match:{an['rid']}", [an["rid"]]
        else:
            outcome, cands = "unseedable_full_plate_unknown", []
        case("clip", "<from pipeline>", "<from pipeline>", "<from pipeline>", outcome, cands,
             f"ground truth plate {r.get('plate_text_truth') or '(none)'}", src="clip", clip=r.get("clip_id", ""), tv=r["target_vehicle_id"])

    # absent check
    leaks = [b for b in g.blocked if b in g.plates]
    if leaks:
        raise SystemExit(f"BUG: in_registry=no plates present in registry: {leaks}")
    g.r.shuffle(g.rows)  # row order must not reveal anchors/decoys
    for p, ah in [(a.out_registry, REG_COLS), (a.out_cases, CASE_COLS), (a.out_decoys, ["anchor_id", "decoy_id", "kind", "plate"])]:
        Path(p).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out_registry, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=REG_COLS); w.writeheader(); w.writerows(g.rows)
    with open(a.out_cases, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CASE_COLS); w.writeheader(); w.writerows(cases)
    with open(a.out_decoys, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["anchor_id", "decoy_id", "kind", "plate"]); w.writeheader(); w.writerows(decoys)
    stats = {"mode": mode, "seed": a.seed, "records": len(g.rows), "anchors": len(seen_anchor),
             "evaluation_seed_rows": sum(r["source"] == "evaluation_seed" for r in g.rows),
             "decoys": len(decoys), "decoy_kinds": dict(Counter(d["kind"] for d in decoys)),
             "test_cases": len(cases), "scenarios": dict(Counter(c["scenario"] for c in cases)),
             "outcomes": dict(Counter(c["expected_outcome"].split(":")[0] for c in cases)),
             "types": dict(Counter(r["vehicle_type"] for r in g.rows)), "states_top10": dict(Counter(r["state_code"] for r in g.rows).most_common(10)),
             "in_registry_no_blocked": len(g.blocked), "skipped_unseedable": skipped,
             "unique_plates": len({r["registration_number"] for r in g.rows}) == len(g.rows)}
    Path(a.out_stats).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out_stats).write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(json.dumps({k: stats[k] for k in ("mode", "records", "anchors", "evaluation_seed_rows", "decoys", "test_cases", "outcomes", "unique_plates", "skipped_unseedable")}))


if __name__ == "__main__":
    main()
