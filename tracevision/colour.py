"""Vehicle colour from body pixels (PIPELINE.md section 5). Output is one of the 12 allowed names plus a confidence.

Heuristic, not a trained model: k-means (k=3) on the body region of the best vehicle crops, dominant cluster
mapped to a name by hue / saturation / lightness rules. In low light it answers "unknown" rather than guess.
"""
from __future__ import annotations

from collections import Counter

import cv2
import numpy as np

TWO_WHEEL = {"motorcycle", "scooter", "motorcycle/scooter", "bicycle"}


def body_region(crop, vtype):
    h, w = crop.shape[:2]
    if vtype in TWO_WHEEL:                       # rider dominates the top; use the middle band
        return crop[int(h * 0.35):int(h * 0.75), int(w * 0.2):int(w * 0.8)]
    # cars seen from behind/front: 30-65% of the height is the boot lid / bonnet band (body paint);
    # above is glass, below is bumper plastic, plate and road (P4 smoke test: wider band read paint as black/grey)
    return crop[int(h * 0.30):int(h * 0.65), int(w * 0.15):int(w * 0.85)]


def name_of(bgr):
    hsv = cv2.cvtColor(np.uint8([[bgr]]), cv2.COLOR_BGR2HSV)[0, 0].astype(float)
    hue, s, v = hsv[0], hsv[1] / 255.0, hsv[2] / 255.0
    if v >= 0.70 and s < 0.30:                   # bright and washed out (haze, overexposure) -> white, not a pastel hue
        return "white"
    if s < 0.20 or v < 0.15:                     # achromatic
        if v >= 0.75:
            return "white"
        if v >= 0.50:
            return "silver"
        if v >= 0.25:
            return "grey"
        return "black"
    if (hue < 10 or hue >= 170):
        return "brown" if v < 0.45 else "red"
    if hue < 20:
        return "brown" if v < 0.55 else "orange"
    if hue < 34:
        return "yellow" if v >= 0.5 else "brown"
    if hue < 85:
        return "green"
    if hue < 130:
        return "blue"
    return "other"


def frame_colour(crop, vtype, k=3, seed=0):
    reg = body_region(crop, vtype)
    if reg.size == 0 or min(reg.shape[:2]) < 8:
        return None
    px = reg.reshape(-1, 3).astype(np.float32)
    hsv = cv2.cvtColor(reg, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    keep = ~((hsv[:, 1] < 30) & (hsv[:, 2] > 245))   # drop specular highlights
    px = px[keep]
    if len(px) < 30:
        return None
    if len(px) > 3000:
        px = px[np.random.default_rng(seed).choice(len(px), 3000, replace=False)]
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    cv2.setRNGSeed(seed)
    _, lab, centers = cv2.kmeans(px, k, None, crit, 2, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(lab.ravel(), minlength=k)
    i = int(counts.argmax())
    return name_of(centers[i]), float(counts[i] / counts.sum()), float(hsv[:, 2].mean())


def estimate_colour(crops, vtype, night_v=55.0):
    """crops: BGR vehicle crops (best frames first). Returns {"label", "confidence", "per_frame", "note"}."""
    res = [r for r in (frame_colour(c, vtype) for c in crops) if r]
    if not res:
        return {"label": "unknown", "confidence": 0.0, "per_frame": [], "note": "no usable body pixels"}
    if np.mean([r[2] for r in res]) < night_v:
        return {"label": "unknown", "confidence": 0.0, "per_frame": [r[0] for r in res], "note": "too dark to judge colour"}
    votes = Counter()
    for name, dom, _ in res:
        votes[name] += dom
    label, w = votes.most_common(1)[0]
    agreement = sum(1 for r in res if r[0] == label) / len(res)
    dominance = float(np.mean([r[1] for r in res if r[0] == label]))
    return {"label": label, "confidence": round(agreement * dominance, 3), "per_frame": [r[0] for r in res], "note": ""}
