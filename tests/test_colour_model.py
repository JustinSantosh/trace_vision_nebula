"""Unit tests for Colour Recognition methods (heuristic, zero-shot clip, linear probe) (Part 11)."""

import numpy as np
import pytest
from tracevision import colour


def test_allowed_labels():
    for c in colour.ALLOWED_COLOURS:
        assert isinstance(c, str)
    assert "other" in colour.ALLOWED_COLOURS
    assert "unknown" in colour.ALLOWED_COLOURS


def test_heuristic_fallback_on_clean_crops():
    # Synthetic white image: 200x200 BGR white (240, 240, 240)
    white_crop = np.full((200, 200, 3), 240, dtype=np.uint8)
    res = colour.estimate_colour([white_crop], "car", method="heuristic")
    assert res["label"] in ("white", "silver")
    assert res["confidence"] > 0.5


def test_heuristic_fallback_on_night_crops():
    # Dark crop: average brightness < 55
    dark_crop = np.full((100, 100, 3), 20, dtype=np.uint8)
    res = colour.estimate_colour([dark_crop], "car", method="heuristic", night_v=55.0)
    assert res["label"] == "unknown"
    assert "too dark" in res["note"]


def test_empty_and_tiny_crops():
    # Empty crops list
    res_empty = colour.estimate_colour([], "car")
    assert res_empty["label"] == "unknown"
    assert res_empty["confidence"] == 0.0

    # Sub-8px crop
    tiny_crop = np.zeros((4, 4, 3), dtype=np.uint8)
    res_tiny = colour.estimate_colour([tiny_crop], "car")
    assert res_tiny["label"] == "unknown"


def test_linear_probe_lazy_loading_and_inference():
    # Test that linear probe loads and produces valid output
    p = colour._linear_probe_model()
    assert p is not None
    assert "weight" in p
    assert "bias" in p
    assert p["weight"].shape[1] == 512

    # Run inference with linear probe on a clean crop
    blue_crop = np.zeros((224, 224, 3), dtype=np.uint8)
    blue_crop[:, :, 0] = 220 # High Blue channel in BGR
    res = colour.estimate_colour([blue_crop], "car", method="linear_probe")
    assert res is not None
    assert res["label"] in colour.ALLOWED_COLOURS
    assert "method" in res
    assert res["method"] in ("linear_probe", "clip", "heuristic")


def test_linear_probe_multi_frame_aggregation():
    # Test multi-frame aggregation with two crops
    crop1 = np.full((224, 224, 3), 230, dtype=np.uint8)
    crop2 = np.full((224, 224, 3), 240, dtype=np.uint8)
    res = colour.estimate_colour([crop1, crop2], "car", method="linear_probe")
    assert res is not None
    assert len(res["per_frame"]) == 2
    assert res["label"] in colour.ALLOWED_COLOURS


def test_fallback_when_probe_unavailable(monkeypatch):
    # Simulate missing linear probe weights
    monkeypatch.setattr(colour, "_linear_probe_model", lambda: None)
    white_crop = np.full((200, 200, 3), 240, dtype=np.uint8)
    res = colour.estimate_colour([white_crop], "car", method="linear_probe")
    # Should safely fall back to CLIP or heuristic without raising an exception
    assert res is not None
    assert res["label"] in colour.ALLOWED_COLOURS

