"""Unit tests for multi-frame plate fusion (tracevision/fuse.py)."""
from tracevision.fuse import fuse


def read(text, prob=0.98, quality=1.0, frame=0, top3=None):
    chars = []
    for i, c in enumerate(text):
        d = {"char": c, "prob": prob}
        if top3 and i in top3:
            d["top3"] = top3[i]
        chars.append(d)
    return {"frame": frame, "quality": quality, "chars": chars}


def test_single_clear_read_is_kept():
    f = fuse([read("CG04AB1234")])
    assert f.text == "CG04AB1234" and f.unknown_positions == [] and f.template == "standard"


def test_majority_wins_when_confident():
    f = fuse([read("CG04AB1234", frame=1), read("CG04AB1284", prob=0.9, frame=2), read("CG04AB1234", frame=3)])
    assert f.text == "CG04AB1234"
    assert f.positions[8].frames == [1, 3]          # evidence frames recorded for the report


def test_tie_gives_question_mark_not_a_guess():
    f = fuse([read("CG04AB1234"), read("CG04AB1284")])
    assert f.text == "CG04AB12?4"
    assert f.unknown_positions == [9]
    assert f.positions[8].best_candidate in {"3", "8"}   # kept for the report only


def test_low_confidence_read_gives_all_question_marks():
    f = fuse([read("CG04AB1234", prob=0.6)])
    assert set(f.text) == {"?"}


def test_low_quality_frames_count_less():
    reads = [read("CG04AB1234", quality=1.0), read("CG04AB1284", quality=0.2), read("CG04AB1284", quality=0.2)]
    assert fuse(reads).text == "CG04AB1234"


def test_cross_class_lookalike_alone_is_not_enough():
    # a single wrong-class character ('8' where the format needs a letter) is folded to its look-alike
    # ('B') at half weight -> confidence too low -> '?' (inference by format is not a reading)
    f = fuse([read("CG04A81234")])
    assert f.text == "CG04A?1234" and f.positions[5].best_candidate == "B"
    assert fuse([read("C604AB1234")]).positions[1].best_candidate == "G"
    assert fuse([read("CG04ABI234")]).positions[6].best_candidate == "1"


def test_cross_class_lookalike_supported_by_other_reads():
    # one read says '8', two say 'B' -> 'B'
    f = fuse([read("CG04A81234"), read("CG04AB1234"), read("CG04AB1234")])
    assert f.text == "CG04AB1234"


def test_dropped_character_in_one_read_is_aligned_not_shifted():
    f = fuse([read("CG04AB1234"), read("CG04AB234"), read("CG04AB1234")])
    assert f.text == "CG04AB1234"
    assert any("disagree on length" in w for w in f.warnings)


def test_top3_alternatives_can_create_doubt():
    # top-1 says 3 with 0.55; the alternative 8 has 0.44 -> share of 3 too small -> '?'
    t3 = {8: [["3", 0.55], ["8", 0.44], ["B", 0.01]]}
    f = fuse([read("CG04AB1234", top3=t3)])
    assert f.text[8] == "?"


def test_bh_series_template():
    f = fuse([read("22BH1234AA")])
    assert f.template == "bh" and f.text == "22BH1234AA"


def test_unknown_state_code_warns_but_is_not_corrected():
    f = fuse([read("XY04AB1234")])
    assert f.text.startswith("XY") and any("state code" in w for w in f.warnings)


def test_no_reads():
    f = fuse([])
    assert f.text == "" and f.n_reads == 0


def test_never_emits_a_character_nobody_read():
    reads = [read("CG04AB1234"), read("CG04AB1284"), read("CG04AB1294")]
    f = fuse(reads)
    seen = {r["chars"][8]["char"] for r in reads}
    assert f.text[8] == "?" or f.text[8] in seen
