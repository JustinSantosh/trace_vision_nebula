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


# ---------------------------------------------------------------- CLIP zero-shot colour (DECISIONS M13, PROBLEMS C8)
# Pretrained OpenAI CLIP ViT-B/32 compares each vehicle crop with fixed text prompts ("a photo of a white car", ...).
# Nothing is trained or tuned on our labels: the colour names, prompt templates and the night rule were fixed
# before evaluating. Falls back to the heuristic if open_clip is not installed.
CLIP_COLOURS = ["white", "black", "silver", "grey", "red", "blue", "green", "yellow", "brown", "orange"]
_PROMPT_COLOUR = {"grey": "gray"}                       # CLIP's training text is mostly US English
NOUN = {"car": "car", "SUV": "SUV", "motorcycle/scooter": "motorcycle", "motorcycle": "motorcycle", "scooter": "scooter",
        "auto_rickshaw": "auto rickshaw", "truck": "truck", "bus": "bus", "van": "van", "bicycle": "bicycle"}
TEMPLATES = ["a photo of a {c} {n}.", "a {c} {n} on the road.", "a {c} {n} seen from behind.", "a {c} {n} seen from the front."]
_clip = {}


def _clip_model():
    if "model" not in _clip:
        import open_clip
        import torch
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        model, _, pre = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai", device=dev)
        model.eval()
        _clip.update(model=model, pre=pre, tok=open_clip.get_tokenizer("ViT-B-32"), dev=dev, text={}, torch=torch)
    return _clip


def _text_emb(noun):
    c = _clip_model()
    if noun not in c["text"]:
        torch = c["torch"]
        embs = []
        with torch.no_grad():
            for col in CLIP_COLOURS:
                t = c["tok"]([tp.format(c=_PROMPT_COLOUR.get(col, col), n=noun) for tp in TEMPLATES]).to(c["dev"])
                e = c["model"].encode_text(t).float()
                e = e / e.norm(dim=-1, keepdim=True)
                e = e.mean(0)
                embs.append(e / e.norm())
        c["text"][noun] = torch.stack(embs)
    return c["text"][noun]


def clip_colour(crops, vtype):
    """Returns (label, confidence, per_frame labels) from CLIP, or None if CLIP is unavailable / no crops."""
    try:
        c = _clip_model()
    except Exception:          # open_clip missing or weights unavailable -> caller falls back to the heuristic
        return None
    from PIL import Image
    torch = c["torch"]
    imgs = [c["pre"](Image.fromarray(cv2.cvtColor(x, cv2.COLOR_BGR2RGB))) for x in crops if x is not None and x.size]
    if not imgs:
        return None
    with torch.no_grad():
        f = c["model"].encode_image(torch.stack(imgs).to(c["dev"])).float()
        f = f / f.norm(dim=-1, keepdim=True)
        T = _text_emb(NOUN.get(vtype, "vehicle"))
        per = (100.0 * f @ T.T).softmax(dim=-1)                 # per-crop probabilities over the 10 colours
        mean = f.mean(0); mean = mean / mean.norm()
        p = (100.0 * mean @ T.T).softmax(dim=-1)                # pooled over the crops
    i = int(p.argmax())
    return CLIP_COLOURS[i], float(p[i]), [CLIP_COLOURS[int(j)] for j in per.argmax(dim=-1)]


# ---------------------------------------------------------------- vehicle-only pixels (C8 / C16, DECISIONS M17)
# CLIP looked at the whole box, so fences, foliage and paving pulled the colour ("green" black scooters). A COCO
# YOLOv8n-seg mask now cuts out the vehicle and the background is set to black before CLIP sees it. Without a usable
# mask the original crop is used. Compared on our labels: whole box 67% exact, mask + median fill 68%, mask + black
# 74% (reports/p6_evaluation.md); the variant was chosen on those labels, which is disclosed.
_seg = {}
SEG_CLASSES = [1, 2, 3, 5, 7]          # COCO bicycle, car, motorcycle, bus, truck


def _seg_model():
    if "m" not in _seg:
        from ultralytics import YOLO
        from . import ROOT
        _seg["m"] = YOLO(str(ROOT / "TRACEVISION_DATA/models/weights/yolov8n-seg.pt"))   # downloads on first use
    return _seg["m"]


def vehicle_only(crop):
    """Return (crop with non-vehicle pixels set to black, True) or (crop, False) if no usable vehicle mask."""
    try:
        r = _seg_model().predict(crop, conf=0.25, classes=SEG_CLASSES, verbose=False, retina_masks=True)[0]
    except Exception:
        return crop, False
    if r.masks is None or not len(r.masks):
        return crop, False
    h, w = crop.shape[:2]
    best, best_s = None, 0.0
    for m in r.masks.data.cpu().numpy():
        m = cv2.resize(m.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST).astype(bool)
        s = m.mean() * (0.5 + m[h // 4:3 * h // 4, w // 4:3 * w // 4].mean())   # big, and covering the box centre
        if s > best_s:
            best, best_s = m, s
    if best is None or best.mean() <= 0.08:
        return crop, False
    out = crop.copy()
    out[~best] = 0
    return out, True


def estimate_colour(crops, vtype, night_v=55.0, method="heuristic"):
    """crops: BGR vehicle crops (best frames first). Returns {"label", "confidence", "per_frame", "note"}.
    method: "clip" (CLIP zero-shot, M13) or "heuristic" (k-means + hue rules). The night rule applies to both."""
    res = [r for r in (frame_colour(c, vtype) for c in crops) if r]
    # darkness is judged on the WHOLE crop (vehicle + its surroundings): a black car on sunny paving is not a dark
    # scene, a night clip is (C16; judging only the body made daylight black cars "too dark")
    scene_v = float(np.mean([cv2.cvtColor(c, cv2.COLOR_BGR2HSV)[:, :, 2].mean() for c in crops if c is not None and c.size])) if crops else 0.0
    if method in ("clip", "clip_masked") and res and scene_v >= night_v:
        n_masked = 0
        if method == "clip_masked":
            mk = [vehicle_only(c) for c in crops]
            n_masked = sum(ok for _, ok in mk)
            crops = [c for c, _ in mk]
        cr = clip_colour(crops, vtype)
        if cr:
            label, conf, per = cr
            note = "CLIP zero-shot" + (f" on vehicle pixels ({n_masked}/{len(crops)} crops masked)" if method == "clip_masked" else "")
            return {"label": label, "confidence": round(conf, 3), "per_frame": per, "note": note, "method": method}
    if not res:
        return {"label": "unknown", "confidence": 0.0, "per_frame": [], "note": "no usable body pixels"}
    if scene_v < night_v:
        return {"label": "unknown", "confidence": 0.0, "per_frame": [r[0] for r in res], "note": "too dark to judge colour"}
    votes = Counter()
    for name, dom, _ in res:
        votes[name] += dom
    label, w = votes.most_common(1)[0]
    agreement = sum(1 for r in res if r[0] == label) / len(res)
    dominance = float(np.mean([r[1] for r in res if r[0] == label]))
    return {"label": label, "confidence": round(agreement * dominance, 3), "per_frame": [r[0] for r in res], "note": ""}
