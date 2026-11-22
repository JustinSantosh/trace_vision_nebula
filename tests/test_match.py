"""Unit tests for registry matching (tracevision/match.py) on a small hand-made registry."""
from tracevision.match import match, type_score, colour_score

REG = [
    {"synthetic_vehicle_id": "A", "registration_number": "CG04AB1234", "vehicle_colour": "white", "vehicle_type": "car"},
    {"synthetic_vehicle_id": "B", "registration_number": "CG04AB1284", "vehicle_colour": "white", "vehicle_type": "car"},
    {"synthetic_vehicle_id": "C", "registration_number": "CG04XY9999", "vehicle_colour": "red", "vehicle_type": "SUV"},
    {"synthetic_vehicle_id": "D", "registration_number": "MH12CD5678", "vehicle_colour": "black", "vehicle_type": "motorcycle"},
    {"synthetic_vehicle_id": "E", "registration_number": "MH12CD5679", "vehicle_colour": "black", "vehicle_type": "scooter"},
]


def top(r):
    return r.candidates[0].synthetic_vehicle_id if r.candidates else None


def test_exact_plate_is_a_confident_match():
    r = match("CG04AB1234", "white", "car", registry=REG)
    assert r.decision == "match" and top(r) == "A" and r.candidates[0].match_score == 100.0


def test_wildcard_that_two_plates_fit_is_ambiguous():
    r = match("CG04AB12?4", "white", "car", registry=REG)
    assert r.decision == "ambiguous" and {c.synthetic_vehicle_id for c in r.candidates[:2]} == {"A", "B"}


def test_lookalike_read_still_finds_the_vehicle():
    r = match("CG04A81234", "white", "car", registry=REG)   # B read as 8
    assert top(r) == "A" and r.decision == "match"
    assert any("look-alike" in x for x in r.candidates[0].reasons)


def test_all_unknown_plate_is_never_a_confident_match():
    r = match("??????????", "white", "car", registry=REG)
    assert r.decision != "match"


def test_too_few_known_characters_is_not_a_match():
    r = match("??????9999", "red", "SUV", registry=REG)
    assert r.decision != "match" and "readable" in r.decision_reason


def test_plate_not_in_registry_gives_no_confident_match():
    r = match("KA01ZZ0001", "blue", "bus", registry=REG)
    assert r.decision == "no_confident_match"


def test_empty_registry():
    r = match("CG04AB1234", "white", "car", registry=[])
    assert r.decision == "no_confident_match" and r.candidates == []


def test_colour_conflict_lowers_score_but_plate_dominates():
    r = match("CG04AB1234", "red", "car", registry=REG)
    assert top(r) == "A" and r.candidates[0].match_score < 100
    assert any("colour conflict" in x for x in r.candidates[0].reasons)


def test_unknown_colour_and_type_are_not_penalised():
    r = match("CG04AB1234", "unknown", "unknown", registry=REG)
    assert top(r) == "A" and r.candidates[0].match_score == 100.0
    assert r.candidates[0].colour_score is None and r.candidates[0].type_score is None


def test_uvh26_two_wheeler_matches_motorcycle_or_scooter():
    assert type_score("motorcycle/scooter", "motorcycle") == 1.0
    assert type_score("motorcycle/scooter", "scooter") == 1.0
    assert type_score("car", "SUV") == 0.5 and type_score("car", "bus") == 0.0


def test_near_colours():
    assert colour_score("white", "silver") == 0.5 and colour_score("white", "black") == 0.0
    assert colour_score("unknown", "white") is None


def test_every_candidate_has_reasons_and_a_match_score_not_a_probability():
    r = match("MH12CD567?", "black", "motorcycle/scooter", registry=REG)
    assert r.candidates and all(c.reasons for c in r.candidates)
    d = r.to_dict()
    assert "match_score" in d["candidates"][0] and "probability" not in str(d).lower()


def test_ranking_is_deterministic():
    a = [c.synthetic_vehicle_id for c in match("MH12CD567?", "black", "unknown", registry=REG).candidates]
    b = [c.synthetic_vehicle_id for c in match("MH12CD567?", "black", "unknown", registry=list(reversed(REG))).candidates]
    assert a == b
