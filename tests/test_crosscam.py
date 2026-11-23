"""Cross-camera re-identification: plate similarity, vetoes and the appearance-only guard (no models needed)."""
import numpy as np

from tracevision.crosscam import DEFAULTS, plate_similarity, score_pair

CAL = {"neg_median": 0.87, "pos_median": 0.96, "neg_p99": 0.965}


def sig(plate="", vtype="car", colour="white", emb=None):
    return {"plate": plate, "known": sum(c != "?" for c in plate), "type": vtype, "colour": colour, "emb": emb}


def unit(v):
    v = np.asarray(v, dtype=float)
    return v / np.linalg.norm(v)


def test_identical_plates():
    assert plate_similarity("CG04NL3024", "CG04NL3024") == (1.0, 10)


def test_unknowns_and_truncated_ends_are_free():
    s, k = plate_similarity("??0S9584", "CG04QS9584")      # leading chars lost, 0/Q look-alike
    assert s > 0.9 and k == 6
    s, k = plate_similarity("CG04DK1578", "??????K1578")
    assert s == 1.0 and k == 5


def test_different_plates_score_low():
    assert plate_similarity("MH12AB1234", "CG04NL3024")[0] < 0.3
    assert plate_similarity("CG14MW3529", "CG04QS9584")[0] < 0.6


def test_short_tail_is_not_enough_plate_evidence():
    # '9584' shares only 4 read characters -> plate is not used (needs min_known = 5), appearance decides
    e = unit([1, 0, 0])
    score, parts, _, ev = score_pair(sig("9584", emb=e), sig("CG04QS9584", emb=e), CAL, dict(DEFAULTS))
    assert "plate" not in parts and ev.startswith("appearance")


def test_plate_conflict_vetoes_even_identical_looks():
    e = unit([1, 0, 0])
    score, _, reasons, ev = score_pair(sig("MH12AB1234", emb=e), sig("CG04NL3024", emb=e), CAL, dict(DEFAULTS))
    assert ev == "veto" and score == 0.0 and "veto" in reasons[0]


def test_plate_agreement_gives_strong_link():
    e = unit([1, 0, 0])
    score, parts, _, ev = score_pair(sig("CG04NL3024", emb=e), sig("CG04NL3024", emb=e), CAL, dict(DEFAULTS))
    assert ev == "plate + appearance" and score > 95


def test_unknown_attributes_are_not_penalised():
    e = unit([1, 0, 0])
    s1, *_ = score_pair(sig(emb=e, colour="unknown"), sig(emb=e, colour="white"), CAL, dict(DEFAULTS))
    s2, *_ = score_pair(sig(emb=e), sig(emb=e), CAL, dict(DEFAULTS))
    assert abs(s1 - s2) < 1e-6


def test_no_evidence_no_score():
    score, _, _, ev = score_pair(sig(), sig(), CAL, dict(DEFAULTS))
    assert score == 0.0 and ev == "none"


def test_partial_plate_consistent_with_full_plate():
    # clip15 white SUV read 'C?14???5??' vs clip14 'CG14MW3529': every jointly read character agrees
    s, k = plate_similarity("C?14???5??", "CG14MW3529")
    assert s == 1.0 and k == 4          # consistent, but only 4 characters: never enough for a plate-confirmed link


def test_duplicate_tracks_fold_nested_box(tmp_path):
    import json
    from tracevision.crosscam import duplicate_tracks
    big = [[f, 100, 100, 400, 400] for f in range(0, 40, 2)]
    small = [[f, 150, 150, 350, 380] for f in range(0, 40, 2)]          # inside the big box, same vehicle
    other = [[f, 500, 100, 700, 400] for f in range(0, 40, 2)]          # a different vehicle beside it
    tiny = [[f, 200, 300, 240, 340] for f in range(0, 40, 2)]           # small object in front: area ratio too small
    vt = lambda tid, tr, t: {"track_id": tid, "track": tr, "type": {"label": t}}
    (tmp_path / "result.json").write_text(json.dumps({"vehicles": [
        vt(1, big, "SUV"), vt(2, small[:-3], "SUV"), vt(3, other, "SUV"), vt(4, tiny, "motorcycle/scooter")]}))
    assert duplicate_tracks(tmp_path) == {2: 1}
