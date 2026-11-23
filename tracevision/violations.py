"""Traffic-violation checks on stored tracks (no models needed). Currently: wrong-side driving.

    python -m tracevision.violations                 # check every clip in runs/ and print a summary

Wrong-side driving (fixed cameras only)
  A camera rule (TRACEVISION_DATA/cameras/camera_rules.json) gives zones of road with a permitted direction of
  travel. For each tracked vehicle, the bottom-centre of its box (where it touches the road) is followed while it is
  inside a zone. The vehicle is flagged only if all of these hold:
    * it is in the zone for at least MIN_POINTS detections
    * its net movement there is at least MIN_DISP of the frame height (parked / jittering boxes are ignored)
    * that movement points against the permitted direction: cosine <= MAX_COS (more than ~120 degrees off)
    * most short steps agree (share of steps moving against the flow >= MIN_AGREE), so one bad box can't flag it
  Clips from moving cameras are "not assessed": image motion there is relative to the camera, not to the road.

A flagged vehicle is a *suspected* violation. It is enforced only after an officer confirms it (review workflow in
api.py), and a simulated challan is raised only when the vehicle also has a confident registry match.
"""
from __future__ import annotations

import csv
import json
import threading
from math import hypot
from pathlib import Path

from . import ROOT

RULES = ROOT / "TRACEVISION_DATA" / "cameras" / "camera_rules.json"
CLIPS_CSV = ROOT / "TRACEVISION_DATA" / "evaluation" / "clips.csv"
REVIEWS = ROOT / "runs" / "enforcement" / "reviews.json"
MIN_POINTS, MIN_DISP, MAX_COS, MIN_AGREE, STEP = 8, 0.06, -0.5, 0.7, 4
_lock = threading.Lock()


def camera_of(clip_id: str) -> str | None:
    if not CLIPS_CSV.exists():
        return None
    for r in csv.DictReader(open(CLIPS_CSV, encoding="utf-8")):
        if r["clip_id"] == clip_id:
            return r.get("camera_id") or None
    return None


def rule_for(clip_id: str | None):
    cam = camera_of(clip_id) if clip_id else None
    try:
        rules = json.loads(RULES.read_text(encoding="utf-8")).get("cameras", {})
    except (OSError, ValueError):
        rules = {}
    return cam, rules.get(cam) if cam else None


def inside(pt, poly) -> bool:
    x, y, hit = pt[0], pt[1], False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[i - 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def _unit(v):
    n = hypot(*v)
    return (v[0] / n, v[1] / n) if n else (0.0, 0.0)


def camera_motion(result: dict, video: Path, ref_frame: int, cache: Path | None = None, every: int = 4) -> dict:
    """Map each sampled frame onto the rule's reference frame (the frame the zones were drawn on).

    "Fixed" phone footage still pans (clip06 drifts ~200 px), and then parked cars sweep across the image and look
    like traffic. Per sampled frame: ORB features on the BACKGROUND only (every tracked vehicle box is masked out,
    so traffic can't drag the estimate), matched straight to the reference frame (no frame-to-frame drift),
    similarity transform by RANSAC. Frames with too few inliers or too large a shift are marked unusable (None).
    Returns {"ref_frame", "every", "transforms": {frame: [a, b, tx, c, d, ty] | None}}."""
    import cv2
    import numpy as np
    if cache and cache.exists():
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if data.get("ref_frame") == ref_frame and data.get("every") == every:
                return data
        except ValueError:
            pass
    boxes: dict[int, list] = {}
    for v in result.get("vehicles", []):
        for p in v.get("track") or []:
            boxes.setdefault(int(p[0]), []).append(p[1:])

    def bg_mask(f, shape):
        m = np.full(shape, 255, np.uint8)
        for fr in range(f - 2, f + 3):
            for x1, y1, x2, y2 in boxes.get(fr, []):
                cv2.rectangle(m, (int(x1) - 6, int(y1) - 6), (int(x2) + 6, int(y2) + 6), 0, -1)
        return m

    cap = cv2.VideoCapture(str(video))
    grey, i = {}, -1
    while True:
        ok, f = cap.read()
        if not ok:
            break
        i += 1
        if i % every == 0 or i == ref_frame:
            grey[i] = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    cap.release()
    orb, bf = cv2.ORB_create(1500), cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    ref = grey.get(ref_frame)
    out = {"ref_frame": ref_frame, "every": every, "transforms": {}}
    if ref is None:
        return out
    kr, dr = orb.detectAndCompute(ref, bg_mask(ref_frame, ref.shape))
    W = ref.shape[1]
    for fr, g in sorted(grey.items()):
        A = None
        if fr == ref_frame:
            A = np.array([[1, 0, 0], [0, 1, 0]], float)
        elif g.std() >= 5 and dr is not None:             # skip black / blank frames
            k, d = orb.detectAndCompute(g, bg_mask(fr, g.shape))
            ms = bf.match(d, dr) if d is not None else []
            if len(ms) >= 12:
                src = np.float32([k[m.queryIdx].pt for m in ms])
                dst = np.float32([kr[m.trainIdx].pt for m in ms])
                A, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0)
                if A is None or inl is None or int(inl.sum()) < 25 or abs(A[0, 2]) > 0.45 * W:
                    A = None
        out["transforms"][str(fr)] = [round(float(x), 4) for x in A.ravel()] if A is not None else None
    if cache:
        cache.write_text(json.dumps(out), encoding="utf-8")
    return out


def _to_ref(motion, frame, x, y):
    """Point in `frame` -> reference-frame pixels using the nearest sampled transform (None if unusable)."""
    if motion is None:
        return x, y
    every = motion["every"]
    near = int(round(frame / every) * every)
    A = motion["transforms"].get(str(near))
    if A is None:
        A = motion["transforms"].get(str(frame))
    if A is None:
        return None
    return A[0] * x + A[1] * y + A[2], A[3] * x + A[4] * y + A[5]


def check_track(track, zone, width, height, motion=None):
    """track: [[frame, x1, y1, x2, y2], ...] in pixels. Returns a finding dict or None.
    With `motion`, points are first moved into the reference frame (camera pan removed); unusable frames are dropped."""
    pts = []
    for p in track:
        q = _to_ref(motion, p[0], (p[1] + p[3]) / 2, p[4])        # bottom-centre: where the vehicle meets the road
        if q is not None:
            pts.append((p[0], q[0] / width, q[1] / height))
    pts = [p for p in pts if inside(p[1:], zone["polygon"])]
    if len(pts) < MIN_POINTS:
        return None
    allowed = _unit(zone["allowed_direction"])
    # aspect-correct the motion so a normalised x step and y step are the same distance in pixels
    vec = lambda a, b: ((b[1] - a[1]) * width / height, b[2] - a[2])
    net = vec(pts[0], pts[-1])
    disp = hypot(*net)
    if disp < MIN_DISP:
        return None
    u = _unit(net)
    cos = u[0] * allowed[0] + u[1] * allowed[1]
    steps = [vec(pts[i], pts[i + STEP]) for i in range(0, len(pts) - STEP, STEP)]
    steps = [s for s in steps if hypot(*s) > 0.004]
    agree = sum(1 for s in steps if _unit(s)[0] * allowed[0] + _unit(s)[1] * allowed[1] < 0) / len(steps) if steps else 0.0
    return {"zone": zone["name"], "points": len(pts), "first_frame": pts[0][0], "last_frame": pts[-1][0],
            "displacement_frac": round(disp, 3), "cos_to_allowed": round(cos, 3), "against_flow_share": round(agree, 2),
            "allowed_direction": zone["allowed_direction"], "observed_direction": [round(u[0], 3), round(u[1], 3)],
            "wrong_side": cos <= MAX_COS and agree >= MIN_AGREE}


def load_reviews() -> dict:
    try:
        return json.loads(REVIEWS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_review(vid: str, review: dict):
    with _lock:
        data = load_reviews()
        data[vid] = review
        REVIEWS.parent.mkdir(parents=True, exist_ok=True)
        REVIEWS.write_text(json.dumps(data, indent=1), encoding="utf-8")


def detect(result: dict, run_id: str) -> dict:
    """Wrong-side check for one stored result. run_id is 'runs/clip02' or 'jobs/<id>' (used in violation ids)."""
    clip = result.get("clip_id")
    cam, rule = rule_for(clip if run_id.startswith("runs/") else None)
    out = {"camera_id": cam, "assessed": bool(rule), "checked_vehicles": 0, "violations": [], "rules": []}
    if not rule:
        out["not_assessed_reason"] = ("no traffic rule is configured for this camera" if cam and "fixed" in cam else
                                      "moving or unknown camera: image motion is not road direction, so wrong-side "
                                      "driving is not assessed")
        return out
    v = result.get("video") or {}
    W, H = v.get("width"), v.get("height")
    out["rules"] = [{"name": z["name"], "allowed_direction": z["allowed_direction"], "polygon": z["polygon"]} for z in rule["zones"]]
    out["camera_description"] = rule.get("description")
    motion = None
    ref = rule.get("reference_frame")
    video = ROOT / "TRACEVISION_DATA" / "raw" / "test_videos" / f"{clip}.mp4"
    if ref is not None:
        if not video.exists() and not (ROOT / run_id / "camera_motion.json").exists():
            out.update(assessed=False, not_assessed_reason="the video is needed to remove camera movement and is not on this machine")
            out["rules"] = []
            return out
        motion = camera_motion(result, video, int(ref), ROOT / run_id / "camera_motion.json")
        usable = [t for t in motion["transforms"].values() if t is not None]
        shifts = [abs(t[2]) for t in usable]
        out["stabilisation"] = {"reference_frame": int(ref), "frames_sampled": len(motion["transforms"]),
                                "frames_usable": len(usable), "max_pan_px": round(max(shifts), 1) if shifts else None}
    reviews = load_reviews()
    fps = v.get("fps") or 30
    out["per_vehicle"] = {}
    for veh in result.get("vehicles", []):
        track = veh.get("track") or []
        best = seen = None
        for zone in rule["zones"]:
            f = check_track(track, zone, W, H, motion)
            if f is not None:
                seen = seen or f
                if f["wrong_side"] and (best is None or f["cos_to_allowed"] < best["cos_to_allowed"]):
                    best = f
        if seen:
            out["checked_vehicles"] += 1
            out["per_vehicle"][str(veh["track_id"])] = best or seen
        if not best:
            continue
        cands = veh.get("candidates") or []
        matched = veh.get("decision") == "match" and cands
        vid = f"{run_id}:T{veh['track_id']}:wrong_side"
        mid = (best["first_frame"] + best["last_frame"]) // 2
        out["violations"].append({
            "violation_id": vid, "type": "wrong_side_driving", "label": "Wrong-side driving",
            "run": run_id, "clip_id": clip, "track_id": veh["track_id"],
            "vehicle_type": (veh.get("type") or {}).get("label"), "colour": (veh.get("colour") or {}).get("label"),
            "plate": (veh.get("plate") or {}).get("fused"), "decision": veh.get("decision"),
            "registration_number": cands[0]["registration_number"] if matched else None,
            "evidence_frames": [best["first_frame"], mid, best["last_frame"]],
            "time_s": [round(best["first_frame"] / fps, 2), round(best["last_frame"] / fps, 2)],
            "measurement": best, "review": reviews.get(vid, {"status": "pending"}),
        })
    return out


def main():
    rows = []
    for p in sorted((ROOT / "runs").glob("clip*/result.json"), key=lambda p: int(p.parent.name[4:])):
        r = json.loads(p.read_text(encoding="utf-8"))
        d = detect(r, f"runs/{p.parent.name}")
        rows.append((p.parent.name, d))
        state = f"{d['checked_vehicles']} vehicles checked, {len(d['violations'])} flagged" if d["assessed"] else "not assessed"
        print(f"{p.parent.name:7} {str(d['camera_id']):24} {state}")
        for v in d["violations"]:
            m = v["measurement"]
            print(f"        T{v['track_id']} {v['vehicle_type']} cos {m['cos_to_allowed']} against-flow {m['against_flow_share']}")
    assessed = [d for _, d in rows if d["assessed"]]
    print(f"\n{len(assessed)} fixed-camera clips assessed, {sum(d['checked_vehicles'] for d in assessed)} vehicles checked, "
          f"{sum(len(d['violations']) for d in assessed)} flagged")


if __name__ == "__main__":
    main()
