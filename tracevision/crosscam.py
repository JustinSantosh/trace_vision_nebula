"""Cross-camera vehicle re-identification (bonus feature; DECISIONS M14, PROBLEMS A6).

Given two analysed clips (runs/<clip>/result.json from the pipeline), link each vehicle in clip A to the same
physical vehicle in clip B, or say there is no confident link. Evidence, strongest first:

  plate       both fused plates have >= min_known readable characters -> symmetric wildcard / look-alike
              similarity. Clearly different plates (similarity < plate_veto) VETO a link, whatever the looks.
  appearance  cosine similarity of CLIP ViT-B/32 image embeddings (mean over up to n_crops crops spread over
              each track), mapped to 0..1 with a scale calibrated on clips 01-11 only (same track at different
              times vs different vehicles in the same clip). See `calibrate`.
  type/colour small weights; unknown attributes are dropped from the weighting, never penalised.

link score = 100 x weighted mean (heuristic ranking score, NOT a probability). Decision per vehicle in A:
  link        top score >= t_link, margin to the 2nd >= t_margin, and A<->B is a MUTUAL best match
  ambiguous   top two candidates within t_margin
  no_link     otherwise (including every plate veto)
Each link states its evidence ("plate + appearance" or "appearance only", the weaker kind) and reasons.

    python -m tracevision.crosscam clip12 clip13          # link two clips -> runs/crosscam/clip12__clip13.json
    python -m tracevision.crosscam --pairs                 # every pair of clips that share a pair id in clips.csv
    python -m tracevision.crosscam --calibrate             # appearance scale from clips 01-11 -> reports/
"""
from __future__ import annotations

import argparse
import csv
import json
from itertools import combinations
from pathlib import Path

import cv2
import numpy as np

from . import ROOT, load_config
from .match import COMPATIBLE_TYPES, NEAR_COLOURS, UNKNOWN
from .plates import is_lookalike

RUNS = ROOT / "runs"
VIDEOS = ROOT / "TRACEVISION_DATA/raw/test_videos"
CLIPS_CSV = ROOT / "TRACEVISION_DATA/evaluation/clips.csv"
CALIB = ROOT / "TRACEVISION_DATA/reports/crosscam_calibration.json"
DEFAULTS = {"min_known": 5, "plate_veto": 0.6, "lookalike_cost": 0.4, "n_crops": 6,
            "w_plate": {"plate": 0.60, "appearance": 0.25, "type": 0.075, "colour": 0.075},
            "w_noplate": {"appearance": 0.70, "type": 0.15, "colour": 0.15},
            "t_link": 70.0, "t_margin": 8.0, "appearance_only_min": "neg_p99",
            "plate_confirm": 0.9, "pair_min_score": 50.0}


def cfg_of(cfg=None):
    c = dict(DEFAULTS)
    c.update((cfg or load_config()).get("crosscam", {}))
    return c


# ------------------------------------------------------------------ evidence
def plate_similarity(a: str, b: str, lookalike_cost=0.4):
    """Symmetric plate similarity for two partly-read plates.
    '?' on EITHER side matches anything for free, and characters hanging off either END of the alignment are free
    (semi-global alignment): OCR on a partial plate typically loses characters at the ends, and a shorter read is
    not evidence of a different plate. Inner gaps and substitutions cost 1 (look-alikes cost `lookalike_cost`).
    Returns (similarity 0..1 over the characters BOTH sides read at aligned positions, that count). The caller
    requires a minimum count, so a short tail (e.g. '9584') cannot link two different plates."""
    # Maximise agreement S = sum over aligned pairs read on both sides of (1 - substitution cost), minus 1 per
    # inner gap; then similarity = S / (number of such pairs) = 1 - cost / joint. End gaps are free (boundaries 0,
    # best cell taken anywhere on the last row / column).
    n, m = len(a), len(b)
    NEG = (-1e9, 0)
    D = [[(0.0, 0)] * (m + 1) for _ in range(n + 1)]   # (S, joint)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            x, y = a[i - 1], b[j - 1]
            both = x != "?" and y != "?"
            gain = 0.0 if not both else (1.0 if x == y else (1.0 - lookalike_cost if is_lookalike(x, y) else 0.0))
            s, k = D[i - 1][j - 1]
            opts = [(s + gain, k + both)]
            s, k = D[i - 1][j]; opts.append((s - 1.0, k))       # gap (inner, or overridden by the free end below)
            s, k = D[i][j - 1]; opts.append((s - 1.0, k))
            D[i][j] = max(opts)
    ends = [D[i][m] for i in range(n + 1)] + [D[n][j] for j in range(m + 1)]
    S, joint = max(ends, key=lambda t: (t[0], t[1])) if ends else NEG
    if joint == 0:
        return 0.0, 0
    return max(0.0, S / joint), joint


def type_sim(a, b):
    if a in UNKNOWN or b in UNKNOWN:
        return None
    A, B = set(a.split("/")), set(b.split("/"))
    if A & B:
        return 1.0
    return 0.5 if any(A & g and B & g for g in COMPATIBLE_TYPES) else 0.0


def colour_sim(a, b):
    if a in UNKNOWN or b in UNKNOWN:
        return None
    if a == b:
        return 1.0
    return 0.5 if any(a in g and b in g for g in NEAR_COLOURS) else 0.0


def appearance_sim(cos, calib):
    """Map CLIP cosine to 0..1: 0 at the negatives' median, 1 at the positives' median (clipped)."""
    lo, hi = calib["neg_median"], calib["pos_median"]
    return float(np.clip((cos - lo) / max(hi - lo, 1e-6), 0.0, 1.0))


# ------------------------------------------------------------------ appearance embeddings
def _video_of(run_dir: Path, result):
    ups = [p for p in run_dir.glob("upload.*")]
    if ups:
        return ups[0]
    return VIDEOS / f"{result['clip_id']}.mp4"


def _pick(track, n):
    """Up to n detections spread over the track, preferring large boxes."""
    t = sorted(track, key=lambda d: d[0])
    if len(t) <= n:
        return t
    chunks = np.array_split(np.arange(len(t)), n)
    return [max((t[i] for i in c), key=lambda d: (d[3] - d[1]) * (d[4] - d[2])) for c in chunks]


def _crops(video: Path, wants):
    """wants: {frame: [(key, box)]} -> {key: [crop, ...]} (one sequential pass with seeks)."""
    out = {}
    cap = cv2.VideoCapture(str(video))
    for fi in sorted(wants):
        cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
        ok, f = cap.read()
        if not ok:
            continue
        H, W = f.shape[:2]
        for key, (x1, y1, x2, y2) in wants[fi]:
            px, py = 0.04 * (x2 - x1), 0.04 * (y2 - y1)
            c = f[max(0, int(y1 - py)):min(H, int(y2 + py)), max(0, int(x1 - px)):min(W, int(x2 + px))]
            if c.size and min(c.shape[:2]) >= 16:
                out.setdefault(key, []).append(c)
    cap.release()
    return out


def embed(crops):
    """Mean L2-normalised CLIP image embedding of the crops (uses the colour module's CLIP model)."""
    from PIL import Image
    from .colour import _clip_model
    c = _clip_model()
    torch = c["torch"]
    x = torch.stack([c["pre"](Image.fromarray(cv2.cvtColor(k, cv2.COLOR_BGR2RGB))) for k in crops]).to(c["dev"])
    with torch.no_grad():
        f = c["model"].encode_image(x).float()
    f = f / f.norm(dim=-1, keepdim=True)
    m = f.mean(0)
    return (m / m.norm()).cpu().numpy()


def signatures(run_dir, n_crops=6):
    run_dir = Path(run_dir)
    r = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    video = _video_of(run_dir, r)
    wants = {}
    for v in r["vehicles"]:
        for d in _pick(v["track"], n_crops):
            wants.setdefault(d[0], []).append((v["track_id"], d[1:5]))
    crops = _crops(video, wants)
    out = []
    for v in r["vehicles"]:
        p = v["plate"].get("fused") or ""
        out.append({"clip_id": r["clip_id"], "track_id": v["track_id"], "type": v["type"]["label"],
                    "colour": v["colour"]["label"], "plate": p, "known": sum(ch != "?" for ch in p),
                    "frames": [v["first_frame"], v["last_frame"]],
                    "emb": embed(crops[v["track_id"]]) if v["track_id"] in crops else None})
    return r, out


# ------------------------------------------------------------------ linking
def score_pair(a, b, calib, c):
    parts, reasons = {}, []
    if a["emb"] is not None and b["emb"] is not None:
        cos = float(a["emb"] @ b["emb"])
        parts["appearance"] = appearance_sim(cos, calib)
        reasons.append(f"appearance similarity {parts['appearance']:.2f} (CLIP cosine {cos:.3f})")
    plate_used = False
    if a["known"] >= c["min_known"] and b["known"] >= c["min_known"]:
        sim, joint = plate_similarity(a["plate"], b["plate"], c["lookalike_cost"])
        if joint >= c["min_known"]:
            if sim < c["plate_veto"]:
                return 0.0, parts, [f"plates differ: {a['plate']} vs {b['plate']} (similarity {sim:.2f}) - veto"], "veto"
            parts["plate"], plate_used = sim, True
            reasons.insert(0, f"plates agree: {a['plate']} vs {b['plate']} (similarity {sim:.2f} on {joint} readable characters)")
    ts, cs = type_sim(a["type"], b["type"]), colour_sim(a["colour"], b["colour"])
    if ts is not None:
        parts["type"] = ts
        reasons.append(f"type {a['type']} vs {b['type']} ({ts:.1f})")
    if cs is not None:
        parts["colour"] = cs
        reasons.append(f"colour {a['colour']} vs {b['colour']} ({cs:.1f})")
    w = c["w_plate"] if plate_used else c["w_noplate"]
    ws = {k: w[k] for k in parts if k in w}
    if not ws or ("appearance" not in parts and not plate_used):
        return 0.0, parts, reasons + ["not enough evidence"], "none"
    score = 100.0 * sum(ws[k] * parts[k] for k in ws) / sum(ws.values())
    return score, parts, reasons, ("plate + appearance" if plate_used else "appearance only (weaker evidence)")


def link(run_a, run_b, cfg=None, calib=None):
    c = cfg_of(cfg)
    calib = calib or json.loads(CALIB.read_text(encoding="utf-8"))
    ra, A = signatures(run_a, c["n_crops"])
    rb, B = signatures(run_b, c["n_crops"])
    S = {(i, j): score_pair(a, b, calib, c) for i, a in enumerate(A) for j, b in enumerate(B)}
    pkey = lambda i, j: (S[i, j][3] == "plate + appearance", S[i, j][0])
    best_a = {j: max(range(len(A)), key=lambda i: pkey(i, j)) for j in range(len(B))} if A else {}
    out = []
    plate_ok = lambda i, j: S[i, j][3] == "plate + appearance"
    for i, a in enumerate(A):
        # plate evidence dominates identity (as in the registry matcher): candidates whose plate AGREES rank above
        # candidates with no plate evidence, and ambiguity is judged among them
        ranked = sorted(range(len(B)), key=lambda j: (-plate_ok(i, j), -S[i, j][0]))
        if ranked and plate_ok(i, ranked[0]):
            ranked = [j for j in ranked if plate_ok(i, j)] + [j for j in ranked if not plate_ok(i, j)]
        cands = [{"clip_id": B[j]["clip_id"], "track_id": B[j]["track_id"], "link_score": round(S[i, j][0], 1),
                  "evidence": S[i, j][3], "parts": {k: round(v, 3) for k, v in S[i, j][1].items()},
                  "reasons": S[i, j][2]} for j in ranked[:3]]
        decision, why = "no_link", "no candidate"
        if ranked:
            top = S[i, ranked[0]][0]
            rivals = [j for j in ranked[1:] if plate_ok(i, j) == plate_ok(i, ranked[0])]
            second = S[i, rivals[0]][0] if rivals else 0.0
            if top < c["t_link"]:
                decision, why = "no_link", f"best link score {top:.1f} is below {c['t_link']}"
            elif top - second < c["t_margin"]:
                decision, why = "ambiguous", f"top two candidates within {c['t_margin']} ({top:.1f} vs {second:.1f})"
            elif best_a.get(ranked[0]) != i:
                decision, why = "no_link", "not a mutual best match (another vehicle in A fits that candidate better)"
            elif S[i, ranked[0]][3].startswith("appearance") and \
                    float(a["emb"] @ B[ranked[0]]["emb"]) < calib[c["appearance_only_min"]]:
                # appearance alone overlaps a lot between same/different vehicles (calibration): demand a cosine above
                # 99% of different-vehicle pairs before linking without plate support
                decision, why = "no_link", (f"appearance only and not distinctive enough (CLIP cosine "
                                            f"{float(a['emb'] @ B[ranked[0]]['emb']):.3f} < {calib[c['appearance_only_min']]:.3f}, "
                                            f"the 99th percentile of different-vehicle pairs)")
            else:
                decision, why = "link", f"link score {top:.1f}, clear of the next candidate, mutual best match ({S[i, ranked[0]][3]})"
        out.append({"clip_id": a["clip_id"], "track_id": a["track_id"], "type": a["type"], "colour": a["colour"],
                    "plate": a["plate"], "decision": decision, "decision_reason": why,
                    "linked_to": cands[0] if decision == "link" else None, "candidates": cands})
    return {"clip_a": ra["clip_id"], "clip_b": rb["clip_id"], "settings": {k: v for k, v in c.items()},
            "calibration": calib, "links": out,
            "note": "link_score is a heuristic ranking score, not a probability. Plate vetoes are never overridden by looks."}


# ------------------------------------------------------------------ calibration (clips 01-11 only)
def calibrate(clips=None, n_crops=4, min_gap_s=1.0):
    """Positives: the same track, early crops vs late crops (>= min_gap_s apart; the moving camera changes the
    view). Negatives: different vehicles of the same clip. Only clips 01-11 - the cross-camera pairs are the test."""
    clips = clips or [f"clip{i:02d}" for i in range(1, 12)]
    pos, neg = [], []
    for cid in clips:
        rd = RUNS / cid
        r = json.loads((rd / "result.json").read_text(encoding="utf-8"))
        fps = r["video"]["fps"]
        wants, halves = {}, {}
        for v in r["vehicles"]:
            t = sorted(v["track"], key=lambda d: d[0])
            if len(t) < 2 * n_crops or (t[-1][0] - t[0][0]) / fps < 2 * min_gap_s:
                continue
            h = len(t) // 2
            for tag, seg in (("early", t[:h]), ("late", t[h:])):
                for d in _pick(seg, n_crops):
                    wants.setdefault(d[0], []).append(((v["track_id"], tag), d[1:5]))
            halves[v["track_id"]] = True
        crops = _crops(_video_of(rd, r), wants)
        E = {k: embed(cs) for k, cs in crops.items() if len(cs) >= 2}
        ids = [t for t in halves if (t, "early") in E and (t, "late") in E]
        for t in ids:
            pos.append(float(E[t, "early"] @ E[t, "late"]))
        for t1, t2 in combinations(ids, 2):
            neg.append(float(E[t1, "early"] @ E[t2, "late"]))
            neg.append(float(E[t2, "early"] @ E[t1, "late"]))
    pos, neg = np.array(pos), np.array(neg)
    res = {"clips": clips, "n_pos": int(len(pos)), "n_neg": int(len(neg)),
           "pos_median": float(np.median(pos)), "neg_median": float(np.median(neg)),
           "pos_p10": float(np.percentile(pos, 10)), "neg_p90": float(np.percentile(neg, 90)),
           "neg_p99": float(np.percentile(neg, 99)), "pos_min": float(pos.min()), "neg_max": float(neg.max()),
           "note": "appearance_sim = clip((cos - neg_median) / (pos_median - neg_median), 0, 1). Calibrated on clips 01-11 "
                   "only (same track early vs late crops = positives; different vehicles in the same clip = negatives)."}
    CALIB.write_text(json.dumps(res, indent=2), encoding="utf-8")
    return res


# ------------------------------------------------------------------ declared same-scene pairs (M16)
def _reads_of(run_dir, track_id):
    r = json.loads((Path(run_dir) / "result.json").read_text(encoding="utf-8"))
    v = next(x for x in r["vehicles"] if x["track_id"] == track_id)
    out = []
    for rd in v["plate"].get("per_frame_reads", []):
        t, ps = rd.get("text") or "", rd.get("char_probs") or []
        if t and len(ps) == len(t):
            out.append({"frame": rd["frame"], "quality": rd.get("quality", 1.0), "height_px": rd.get("height_px"),
                        "text": t, "chars": [{"char": ch, "prob": p, "top3": [[ch, p]]} for ch, p in zip(t, ps)]})
    return v, out


def _pool(v_a, v_b, reads, registry, cfg):
    """One final answer for a physical vehicle seen by two cameras: fused plate over BOTH cameras' reads,
    pooled type and colour, one registry check."""
    from .fuse import fuse
    from .match import decide, rank
    fused = fuse(reads, cfg).text if reads else ""
    ta, tb = v_a["type"], v_b["type"]
    vtype = ta["label"] if (type_sim(ta["label"], tb["label"]) or 0) >= 0.5 and ta.get("detector_conf_mean", 0) >= tb.get("detector_conf_mean", 0) \
        else (tb["label"] if (type_sim(ta["label"], tb["label"]) or 0) >= 0.5 else
              max((ta, tb), key=lambda t: t.get("detector_conf_mean", 0))["label"])
    ca, cb = v_a["colour"], v_b["colour"]
    colour = ca["label"] if ca["label"] == cb["label"] else max((ca, cb), key=lambda c: c.get("confidence", 0))["label"]
    res = {"plate": fused or None, "type": vtype, "colour": colour, "reads_pooled": len(reads),
           "decision": "no_confident_match", "registry_top1": None, "match_score": None, "reason": "no readable plate in either camera"}
    if fused and fused.strip("?"):
        q, known, cands = rank(fused, colour, vtype, registry, cfg)
        m = decide(q, colour, vtype, known, cands, cfg)
        res.update(decision=m.decision, reason=m.decision_reason,
                   registry_top1=(m.candidates[0].registration_number if m.candidates else None),
                   match_score=(round(m.candidates[0].match_score, 1) if m.candidates else None))
    return res


def duplicate_tracks(run_dir, min_contain=0.85, min_frac=0.7, min_area_ratio=0.3):
    """C12: one vehicle sometimes gets a second, nested box. Track S is a duplicate of track L when, on >= min_frac of
    S's frames that L also has, S's box lies >= min_contain inside L's box, S is not tiny relative to L
    (area ratio >= min_area_ratio, so a small vehicle in front of a big one is not swallowed) and the types are
    compatible. Returns {duplicate_track_id: kept_track_id}."""
    r = json.loads((Path(run_dir) / "result.json").read_text(encoding="utf-8"))
    vs = r["vehicles"]
    tb = {v["track_id"]: {t[0]: t[1:5] for t in v["track"]} for v in vs}
    area = lambda b: max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    dup = {}
    for x, p in enumerate(vs):
        for q in vs[x + 1:]:
            if (type_sim(p["type"]["label"], q["type"]["label"]) or 0) < 0.5:
                continue
            P, Q = tb[p["track_id"]], tb[q["track_id"]]
            fs = [f for f in P if f in Q]
            if len(fs) < 3 or len(fs) < min_frac * min(len(P), len(Q)):
                continue
            ok = 0
            for f in fs:     # on each shared frame: is the smaller box (whichever it is) inside the larger one?
                a, b = sorted((P[f], Q[f]), key=area)
                ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
                if area(a) and area(b) and ix * iy / area(a) >= min_contain and area(a) / area(b) >= min_area_ratio:
                    ok += 1
            if ok >= min_frac * len(fs):     # duplicates: fold the track with fewer detections into the other
                small, big = (p, q) if len(P) < len(Q) else (q, p)
                dup[small["track_id"]] = big["track_id"]
    # resolve chains (a -> b -> c) to the outermost track
    for k in list(dup):
        seen = {k}
        while dup[k] in dup and dup[k] not in seen:
            seen.add(dup[k]); dup[k] = dup[dup[k]]
    return dup


def link_pair(run_a, run_b, cfg=None, calib=None):
    """Clips the owner declared a SAME-SCENE pair (same vehicles, two angles; clips.csv cam_parking_pairN_a/b).
    1. plate-confirmed links: plate similarity >= plate_confirm on >= min_known jointly read characters (one-to-one)
    2. the rest: one-to-one assignment (Hungarian) maximising the link score; accepted only if the types are
       compatible, no plate veto, and score >= pair_min_score -> 'probable' (appearance / elimination)
    3. per link: pooled evidence -> one final answer (fused plate over both cameras, type, colour, registry).
       A registry identity is CONFIDENT only for plate-confirmed links; for probable links it is reported as a
       candidate inherited through the link, never as a match."""
    from scipy.optimize import linear_sum_assignment
    from .match import load_registry
    full_cfg = cfg or load_config()
    c = cfg_of(full_cfg)
    calib = calib or json.loads(CALIB.read_text(encoding="utf-8"))
    ra, A = signatures(run_a, c["n_crops"])
    rb, B = signatures(run_b, c["n_crops"])
    # fold duplicate (nested) tracks into the track they sit inside: their plate becomes the group's best plate
    dups = {}
    for side, run, sig in (("a", run_a, A), ("b", run_b, B)):
        d = duplicate_tracks(run)
        dups[side] = d
        by_id = {s["track_id"]: s for s in sig}
        for small, big in d.items():
            if small in by_id and big in by_id and by_id[small]["known"] > by_id[big]["known"]:
                by_id[big]["plate"], by_id[big]["known"] = by_id[small]["plate"], by_id[small]["known"]
        sig[:] = [s for s in sig if s["track_id"] not in d]
    S = {(i, j): score_pair(a, b, calib, c) for i, a in enumerate(A) for j, b in enumerate(B)}
    used_a, used_b, links = set(), set(), []
    plate_pairs = sorted(((S[i, j][1].get("plate", 0), S[i, j][0], i, j) for (i, j) in S
                          if S[i, j][3] == "plate + appearance" and S[i, j][1].get("plate", 0) >= c["plate_confirm"]), reverse=True)
    for _, sc, i, j in plate_pairs:
        if i in used_a or j in used_b:
            continue
        used_a.add(i); used_b.add(j)
        links.append((i, j, "confirmed (plate)", sc))
    ra_i = [i for i in range(len(A)) if i not in used_a]
    rb_j = [j for j in range(len(B)) if j not in used_b]
    if ra_i and rb_j:
        M = np.array([[S[i, j][0] if S[i, j][3] != "veto" else -1e6 for j in rb_j] for i in ra_i])
        for r, k in zip(*linear_sum_assignment(-M)):
            i, j = ra_i[r], rb_j[k]
            ts = type_sim(A[i]["type"], B[j]["type"])
            if S[i, j][3] != "veto" and M[r, k] >= c["pair_min_score"] and (ts is None or ts >= 0.5):
                links.append((i, j, "probable (same-scene pair: appearance / type / colour, by elimination)", S[i, j][0]))
    # last resort, only because the owner declared the clips show the SAME vehicles: if exactly one compatible
    # vehicle is left on each side and whatever plate characters both read agree, they are linked by elimination
    la = [i for i in range(len(A)) if i not in {l[0] for l in links}]
    lb = [j for j in range(len(B)) if j not in {l[1] for l in links}]
    comp = lambda i, j: (type_sim(A[i]["type"], B[j]["type"]) or 0) >= 0.5 and S[i, j][3] != "veto"
    for i in la:
        cj = [j for j in lb if comp(i, j)]
        if len(cj) == 1 and len([k for k in la if comp(k, cj[0])]) == 1:
            j = cj[0]
            sim, joint = plate_similarity(A[i]["plate"], B[j]["plate"], c["lookalike_cost"]) if A[i]["plate"] and B[j]["plate"] else (1.0, 0)
            if joint == 0 or sim >= c["plate_confirm"]:
                links.append((i, j, "probable (elimination: the only remaining compatible vehicle on each side"
                              + (f"; partial plates agree on {joint} characters" if joint else "") + ")", S[i, j][0]))
    registry = load_registry()
    out = []
    for i, j, kind, sc in sorted(links, key=lambda x: (x[2] != "confirmed (plate)", -x[3])):
        va, reads_a = _reads_of(run_a, A[i]["track_id"])
        vb, reads_b = _reads_of(run_b, B[j]["track_id"])
        for side, run, tid, reads in (("a", run_a, A[i]["track_id"], reads_a), ("b", run_b, B[j]["track_id"], reads_b)):
            for small, big in dups[side].items():       # reads of folded duplicates belong to the same vehicle
                if big == tid:
                    reads += _reads_of(run, small)[1]
        pooled = _pool(va, vb, reads_a + reads_b, registry, full_cfg)
        if not kind.startswith("confirmed") and pooled["decision"] == "match":
            pooled["decision"] = "candidate_via_probable_link"
            pooled["reason"] = "plate evidence comes through a probable (not plate-confirmed) cross-camera link: candidate only, " + pooled["reason"]
        out.append({"a": {"clip_id": ra["clip_id"], "track_id": A[i]["track_id"], "plate": A[i]["plate"] or None},
                    "b": {"clip_id": rb["clip_id"], "track_id": B[j]["track_id"], "plate": B[j]["plate"] or None},
                    "link": kind, "link_score": round(sc, 1), "evidence": S[i, j][2], "final": pooled})
    linked_a = {o["a"]["track_id"] for o in out}; linked_b = {o["b"]["track_id"] for o in out}
    return {"clip_a": ra["clip_id"], "clip_b": rb["clip_id"], "mode": "declared same-scene pair",
            "links": out, "duplicates_folded": {"a": dups["a"], "b": dups["b"]},
            "unlinked_a": [a["track_id"] for a in A if a["track_id"] not in linked_a],
            "unlinked_b": [b["track_id"] for b in B if b["track_id"] not in linked_b],
            "note": "Pair declared by the owner (same vehicles, two angles). Only plate-confirmed links give a confident identity."}


def evaluate_links(pairs):
    """Score runs/crosscam/<a>__<b>.json against evaluation/cross_camera_ground_truth.csv.
    Each labelled vehicle is associated with a system track by BOX POSITION ONLY (tracevision.evaluate.associate,
    as in P6), never by plate. Per ground-truth group: correct link / missed (no link) / wrong link / not tracked.
    Every system link is also checked: wrong = it joins two tracks that belong to different labelled vehicles."""
    from .evaluate import assign_clip
    labels = {r["target_vehicle_id"]: r for r in csv.DictReader(open(ROOT / "TRACEVISION_DATA/evaluation/test_clip_labels.csv", encoding="utf-8"))}
    gt = list(csv.DictReader(open(ROOT / "TRACEVISION_DATA/evaluation/cross_camera_ground_truth.csv", encoding="utf-8")))
    groups = {}
    for g in gt:
        groups.setdefault(g["group_id"], {})[g["clip_id"]] = g["target_vehicle_id"]
    rows, wrong_links, total_links = [], 0, 0
    for ca, cb in pairs:
        res = json.loads((RUNS / "crosscam" / f"{ca}__{cb}.json").read_text(encoding="utf-8"))
        va = json.loads((RUNS / ca / "result.json").read_text(encoding="utf-8"))["vehicles"]
        vb = json.loads((RUNS / cb / "result.json").read_text(encoding="utf-8"))["vehicles"]
        track_of = {}                                       # target_vehicle_id -> system track id (one-to-one, E14)
        for cid, vs in ((ca, va), (cb, vb)):
            for tid, (v, _) in assign_clip([l for l in labels.values() if l["clip_id"] == cid], vs).items():
                track_of[tid] = v["track_id"]
        label_of = {(labels[t]["clip_id"], k): t for t, k in track_of.items()}
        group_of = {t: g for g, m in groups.items() for t in m.values()}
        if "pair_linking" in res:      # declared same-scene pair: score the joint links (M16)
            # the system folded nested duplicate tracks into one vehicle: a label on a folded track means the kept one
            fold = res["pair_linking"].get("duplicates_folded", {})
            for tid in list(track_of):
                side = "a" if labels[tid]["clip_id"] == ca else "b"
                track_of[tid] = int(fold.get(side, {}).get(str(track_of[tid]), track_of[tid]))
            label_of = {(labels[t]["clip_id"], k): t for t, k in track_of.items()}
            pl = res["pair_linking"]["links"]
            link_of = {l["a"]["track_id"]: l["b"]["track_id"] for l in pl}
            kind_of = {l["a"]["track_id"]: l["link"] for l in pl}
        else:
            link_of = {l["track_id"]: (l["linked_to"]["track_id"] if l["linked_to"] else None) for l in res["links"]}
            kind_of = {}
        for ta_id, tb_id in link_of.items():
            if tb_id is not None:
                total_links += 1
                ta, tb = label_of.get((ca, ta_id)), label_of.get((cb, tb_id))
                if ta and tb and group_of.get(ta) != group_of.get(tb):
                    wrong_links += 1
        for g, members in groups.items():
            if ca not in members or cb not in members:
                continue
            a, b = members[ca], members[cb]
            if a not in track_of or b not in track_of:
                outcome = "not tracked at the labelled frame"
            elif link_of.get(track_of[a]) == track_of[b]:
                outcome = "correct link" + (f" [{kind_of[track_of[a]].split(' (')[0]}]" if track_of[a] in kind_of else "")
            elif link_of.get(track_of[a]) is None:
                outcome = "no link (missed)"
            else:
                outcome = "WRONG link"
            rows.append({"group": g, "clip_a": ca, "clip_b": cb, "a": a, "b": b, "outcome": outcome,
                         "plate_a": labels[a]["plate_text_truth"], "plate_b": labels[b]["plate_text_truth"]})
    summary = {"groups": len(rows), "correct_links": sum(r["outcome"].startswith("correct link") for r in rows),
               "missed": sum(r["outcome"].startswith("no link") for r in rows),
               "wrong_links_on_groups": sum(r["outcome"] == "WRONG link" for r in rows),
               "not_tracked": sum(r["outcome"].startswith("not tracked") for r in rows),
               "system_links_total": total_links, "system_links_joining_different_labelled_vehicles": wrong_links}
    out = {"summary": summary, "groups": rows,
           "note": "Labels linked to tracks by box position only (never by plate)."}
    (ROOT / "TRACEVISION_DATA/reports/crosscam_evaluation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def _pairs_from_clips_csv():
    groups = {}
    for r in csv.DictReader(open(CLIPS_CSV, encoding="utf-8")):
        cam = r.get("camera_id", "")
        if cam.startswith("cam_parking_pair"):
            groups.setdefault(cam.rsplit("_", 1)[0], []).append(r["clip_id"])
    return [tuple(sorted(v)) for v in groups.values() if len(v) == 2]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clips", nargs="*", help="two clip ids (runs/<clip>)")
    ap.add_argument("--pairs", action="store_true", help="link every camera pair listed in clips.csv")
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--evaluate", action="store_true", help="score the --pairs links against cross_camera_ground_truth.csv")
    a = ap.parse_args()
    if a.calibrate:
        print(json.dumps(calibrate(), indent=2)); return
    if a.evaluate:
        ev = evaluate_links(_pairs_from_clips_csv())
        for r in ev["groups"]:
            print(f"  {r['group']} {r['a']} <-> {r['b']}: {r['outcome']}")
        print(json.dumps(ev["summary"], indent=2)); return
    pairs = _pairs_from_clips_csv() if a.pairs else [tuple(a.clips)]
    out_dir = RUNS / "crosscam"; out_dir.mkdir(parents=True, exist_ok=True)
    for ca, cb in pairs:
        res = link(RUNS / ca, RUNS / cb)
        if a.pairs:   # clips.csv pairs are owner-declared same-scene pairs -> joint linking + pooled evidence (M16)
            res["pair_linking"] = link_pair(RUNS / ca, RUNS / cb)
        (out_dir / f"{ca}__{cb}.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
        if "pair_linking" in res:
            print(f"== {ca} <-> {cb} (declared same-scene pair)")
            for l in res["pair_linking"]["links"]:
                f = l["final"]
                print(f"  #{l['a']['track_id']} <-> #{l['b']['track_id']}  {l['link']:<14.14} score {l['link_score']:<5}  final: plate {f['plate'] or '-':<11} "
                      f"{f['type']:<18} {f['colour']:<7} {f['decision']} {f['registry_top1'] or ''}")
            print("  unlinked:", res["pair_linking"]["unlinked_a"], "|", res["pair_linking"]["unlinked_b"])
            continue
        print(f"== {ca} -> {cb}")
        for l in res["links"]:
            tgt = l["linked_to"]
            print(f"  #{l['track_id']:<3} {l['type']:<19} {l['colour']:<7} {l['plate'] or '-':<12} {l['decision']:<9} "
                  + (f"-> {cb} #{tgt['track_id']} score {tgt['link_score']} [{tgt['evidence']}]" if tgt else l["decision_reason"]))


if __name__ == "__main__":
    main()
