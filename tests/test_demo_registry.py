"""Demo registry layer (M21): kept out of the evaluation; partly read plates get a ranked shortlist, not a match."""
import random

from tracevision import load_config
from tracevision.match import decide, is_demo, load_registry, rank

from tracevision import demo_registry as gdr


def test_evaluation_registry_has_no_demo_rows():
    assert not any(is_demo(r) for r in load_registry(demo=False))


def _row(rid, plate, vtype, colour):
    return {"synthetic_vehicle_id": rid, "registration_number": plate, "vehicle_type": vtype, "vehicle_colour": colour,
            "source": "demo_possible"}


def test_partial_plate_gets_five_possible_matches_not_a_match():
    cfg = load_config()
    q = "MH4?K0516?"
    rng = random.Random(1)
    rows = [_row(f"SD{i}", gdr.fill(rng, q), t, c) for i, (c, t) in
            enumerate([("white", "truck"), ("white", "truck"), ("white", "bus"), ("red", "truck"), ("blue", "car")])]
    assert all(gdr.agrees(q, r["registration_number"]) for r in rows)
    qq, known, cands = rank(q, "white", "truck", rows, cfg)
    m = decide(qq, "white", "truck", known, cands, cfg)
    assert len(m.candidates) == 5
    assert m.decision == "ambiguous"
    assert any("demo registry record" in x for x in m.candidates[0].reasons)


def test_fill_keeps_known_characters_and_format():
    rng = random.Random(3)
    p = gdr.fill(rng, "??0??K1578")
    assert len(p) == 10 and p[2] == "0" and p.endswith("K1578") and p[:2].isalpha() and p[3].isdigit()


def test_full_read_gets_one_off_possibles_not_itself():
    b = gdr._Builder([])
    b.rows, b.taken = [], set()
    b.main = []
    assert b.possible("HR55AB1605", "SUV", "silver", "t") == 5
    plates = [r["registration_number"] for r in b.rows]
    assert "HR55AB1605" not in plates
    assert all(sum(x != y for x, y in zip(p, "HR55AB1605")) == 1 for p in plates)
