"""Traffic-violation checks on stored tracks. Currently: wrong-side driving, by two methods.

    python -m tracevision.violations                 # check every clip in runs/ and print a summary
    python -m tracevision.violations --orient --jobs # compute CLIP front/rear caches first (needs open_clip), incl. uploads

1. Fixed cameras: direction in a zone (no models)
  A camera rule (TRACEVISION_DATA/cameras/camera_rules.json, "cameras") gives zones of road with a permitted direction
  of travel. For each tracked vehicle, the bottom-centre of its box (where it touches the road) is followed while it is
  inside a zone, after camera pan is removed. The vehicle is flagged only if all of these hold:
    * it is in the zone for at least MIN_POINTS detections
    * its net movement there is at least MIN_DISP of the frame height (parked / jittering boxes are ignored)
    * that movement points against the permitted direction: cosine <= MAX_COS (more than ~120 degrees off)
    * most short steps agree (share of steps moving against the flow >= MIN_AGREE), so one bad box can't flag it

2. Moving cameras: head-on pass (CLIP orientation, DECISIONS E19)
  On a moving camera, image motion is not road direction, so the vehicle's ORIENTATION is used instead. CLIP zero-shot
  scores each sampled crop "front (headlights, grille)" against "rear (red tail lights, boot)". A head-on pass is:
    * its front is seen clearly (p_front >= HO_FRONT) on >= HO_K crops while the box grows at least HO_GROWTH times
      (it closes in from a distance facing the camera; an overtaking car's flank does not grow like this)
    * then its rear is seen (p_front <= HO_REAR) on >= HO_K later crops (it has gone past)
  A head-on pass is wrong-side driving where the road is one-way for the camera's direction ("layout": "one_way" in
  "moving" / "uploads" of camera_rules.json). On a declared two-way road it is ordinary oncoming traffic and is not
  flagged; with the layout undeclared it is flagged for review with that caveat. Cars only (two-wheelers' riders hide
  front / rear).

A flagged vehicle is a *suspected* violation. It is enforced only after it is confirmed (review workflow in api.py),
and a simulated challan is raised only when the vehicle also has a confident registry match.
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
HO_FRONT, HO_REAR, HO_K, HO_GROWTH, HO_MIN_SIDE, HO_SAMPLES = 0.8, 0.3, 3, 2.0, 60, 24
FRONT_PROMPTS = ["a photo of a car's headlights at the front", "front bumper and grille of a car"]
REAR_PROMPTS = ["a photo of a car's red tail lights at the back", "rear bumper and boot of a car"]
TWO_WHEEL = ("motorcycle", "scooter", "bicycle")
_lock = threading.Lock()


def camera_of(clip_id: str) -> str | None:
    if not CLIPS_CSV.exists():
        return None
    for r in csv.DictReader(open(CLIPS_CSV, encoding="utf-8")):
        if r["clip_id"] == clip_id:
            return r.get("camera_id") or None
    return None


def run_path(run_id: str) -> Path:
    """'runs/clip02' -> runs/clip02 ; 'jobs/<id>' (API id of an upload) -> runs/jobs/<id>."""
    return ROOT / "runs" / run_id if run_id.startswith("jobs/") else ROOT / run_id


def run_label(run_id: str, result: dict) -> str:
    """Name shown for a run: the clip id, or an upload's original file name."""
    if run_id.startswith("jobs/"):
        nf = run_path(run_id) / "name.txt"
        if nf.exists():
            return nf.read_text(encoding="utf-8").strip()[:80] or run_id
        return run_id
    return result.get("clip_id") or run_id


def _rules() -> dict:
    try:
        return json.loads(RULES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def rule_for(clip_id: str | None):
    cam = camera_of(clip_id) if clip_id else None
    rules = _rules().get("cameras", {})
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
    is_wrong = cos <= MAX_COS and agree >= MIN_AGREE
    
    # Severity classification: Critical, High, Needs Review, Not a Violation
    zone_type = zone.get("restricted_type", "divided_carriageway")
    if is_wrong:
        if cos <= -0.80 or disp >= 0.12 or zone_type in ("one_way", "emergency_route"):
            severity = "critical"
        else:
            severity = "high"
    else:
        if cos <= -0.30 and agree >= 0.50:
            severity = "needs_review"
        else:
            severity = "not_a_violation"

    return {"zone": zone["name"], "points": len(pts), "first_frame": pts[0][0], "last_frame": pts[-1][0],
            "displacement_frac": round(disp, 3), "cos_to_allowed": round(cos, 3), "against_flow_share": round(agree, 2),
            "allowed_direction": zone["allowed_direction"], "observed_direction": [round(u[0], 3), round(u[1], 3)],
            "wrong_side": is_wrong, "severity": severity, "zone_type": zone_type}


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


def _entry(veh, run_id, clip, first, last, fps, measurement, reviews):
    cands = veh.get("candidates") or []
    matched = veh.get("decision") == "match" and cands
    vid = f"{run_id}:T{veh['track_id']}:wrong_side"
    severity = measurement.get("severity", "high")
    return {
        "violation_id": vid, "type": "wrong_side_driving", "label": "Wrong-side driving",
        "severity": severity,
        "run": run_id, "clip_id": clip, "track_id": veh["track_id"],
        "vehicle_type": (veh.get("type") or {}).get("label"), "colour": (veh.get("colour") or {}).get("label"),
        "plate": (veh.get("plate") or {}).get("fused"), "decision": veh.get("decision"),
        "registration_number": cands[0]["registration_number"] if matched else None,
        "evidence_frames": [first, (first + last) // 2, last],
        "time_s": [round(first / fps, 2), round(last / fps, 2)],
        "measurement": measurement, "review": reviews.get(vid, {"status": "pending"}),
    }


# ---------------------------------------------------------------- moving cameras: head-on pass
_text = {}


def compute_orientation(result: dict, video: Path) -> dict:
    """CLIP front/rear score for up to HO_SAMPLES crops per 4-wheeled track: {track_id: [[frame, p_front, width_frac]]}."""
    import cv2
    import numpy as np
    from PIL import Image

    from .colour import _clip_model
    c = _clip_model()
    torch = c["torch"]
    if "T" not in _text:
        def emb(ps):
            e = c["model"].encode_text(c["tok"](ps).to(c["dev"])).float()
            e /= e.norm(dim=-1, keepdim=True)
            e = e.mean(0)
            return e / e.norm()
        with torch.no_grad():
            _text["T"] = torch.stack([emb(FRONT_PROMPTS), emb(REAR_PROMPTS)])
    v = result.get("video") or {}
    W = v.get("width")
    want = {}
    for veh in result.get("vehicles", []):
        if any(k in (veh.get("type") or {}).get("label", "") for k in TWO_WHEEL):
            continue                                   # prompts describe cars; riders hide a two-wheeler's front/rear
        pts = [p for p in veh.get("track") or []
               if min(p[3] - p[1], p[4] - p[2]) >= HO_MIN_SIDE and p[1] > 2 and p[3] < W - 2]
        if len(pts) >= 2 * HO_K:
            idx = np.linspace(0, len(pts) - 1, min(HO_SAMPLES, len(pts))).astype(int)
            want[str(veh["track_id"])] = [pts[i] for i in idx]
    frames = {p[0] for ps in want.values() for p in ps}
    cap, i, got = cv2.VideoCapture(str(video)), -1, {}
    while frames:
        ok, f = cap.read()
        if not ok:
            break
        i += 1
        if i in frames:
            got[i] = f
    cap.release()
    out = {}
    for tid, ps in want.items():
        ps = [p for p in ps if p[0] in got]
        if not ps:
            continue
        ims = [c["pre"](Image.fromarray(cv2.cvtColor(got[p[0]][int(p[2]):int(p[4]), int(p[1]):int(p[3])], cv2.COLOR_BGR2RGB)))
               for p in ps]
        with torch.no_grad():
            ie = c["model"].encode_image(torch.stack(ims).to(c["dev"])).float()
            ie /= ie.norm(dim=-1, keepdim=True)
            pf = (100 * ie @ _text["T"].T).softmax(-1)[:, 0].cpu().numpy()
        out[tid] = [[int(p[0]), round(float(q), 3), round((p[3] - p[1]) / W, 3)] for p, q in zip(ps, pf)]
    return out


def orient_run(run_dir: Path, video: Path) -> dict:
    """Compute and cache <run>/orientation.json (call where the GPU / CLIP is available: pipeline worker or CLI)."""
    result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    data = {"prompts": {"front": FRONT_PROMPTS, "rear": REAR_PROMPTS}, "tracks": compute_orientation(result, video)}
    (run_dir / "orientation.json").write_text(json.dumps(data), encoding="utf-8")
    return data


def head_on(seq):
    """seq: [[frame, p_front, width_frac], ...] in time order. Returns the measurement if it is a head-on pass."""
    front = [s for s in seq if s[1] >= HO_FRONT]
    rear = [s for s in seq if s[1] <= HO_REAR]
    if len(front) < HO_K or len(rear) < HO_K:
        return None
    ff = sorted(s[0] for s in front)
    rr = sorted(s[0] for s in rear)
    if not ff[HO_K - 1] < rr[-HO_K]:                 # the front must be seen before the rear
        return None
    before = [s for s in front if s[0] <= rr[-HO_K]]
    growth = max(s[2] for s in before) / max(1e-3, min(s[2] for s in before))
    if growth < HO_GROWTH:                           # never closed in facing the camera (e.g. an overtaking flank)
        return None
    ff = sorted(s[0] for s in before)                # report the approach only (not a later look back)
    return {"method": "head_on_pass", "front_frames": ff, "rear_frames": rr, "growth": round(growth, 2),
            "p_front_median": round(sorted(s[1] for s in front)[len(front) // 2], 2),
            "p_rear_median": round(1 - sorted(s[1] for s in rear)[len(rear) // 2], 2),
            "first_frame": ff[0], "last_frame": rr[-1]}


def _moving_rule(run_id: str, cam: str | None):
    rules = _rules()
    if run_id.startswith("jobs/"):
        nf = run_path(run_id) / "name.txt"
        name = nf.read_text(encoding="utf-8").strip() if nf.exists() else ""
        ups = rules.get("uploads", {})
        return ups.get(name) or ups.get(run_id.split("/")[1])
    return rules.get("moving", {}).get(cam) if cam else None


LAYOUT_NOTE = {"one_way": "Declared one-way for the camera's direction: a head-on pass is wrong-side driving.",
               "two_way": "Declared two-way: head-on passes are ordinary oncoming traffic, so none is flagged.",
               "undeclared": "Road layout not declared: a head-on pass is flagged for review, but on a two-way road it "
                             "may be ordinary oncoming traffic."}


def _detect_head_on(result: dict, run_id: str, cam):
    clip = run_label(run_id, result)
    rule = _moving_rule(run_id, cam) or {}
    layout = rule.get("layout", "undeclared")
    out = {"camera_id": cam, "method": "head_on_pass", "layout": layout, "layout_note": LAYOUT_NOTE.get(layout),
           "camera_description": rule.get("description"), "assessed": False, "checked_vehicles": 0,
           "violations": [], "rules": []}
    cache = run_path(run_id) / "orientation.json"
    if not cache.exists():
        out["not_assessed_reason"] = ("vehicle orientation has not been computed for this clip yet "
                                      "(python -m tracevision.violations --orient)")
        return out
    tracks = json.loads(cache.read_text(encoding="utf-8")).get("tracks", {})
    out["assessed"] = True
    fps = (result.get("video") or {}).get("fps") or 30
    reviews = load_reviews()
    out["per_vehicle"] = {}
    for veh in result.get("vehicles", []):
        seq = tracks.get(str(veh["track_id"]))
        if not seq:
            continue
        out["checked_vehicles"] += 1
        m = head_on(seq)
        wrong = bool(m) and layout != "two_way"
        severity = ("critical" if layout == "one_way" else "needs_review") if wrong else "not_a_violation"
        pv = (m or {"method": "head_on_pass"}) | {"wrong_side": wrong, "severity": severity, "layout": layout, "head_on": bool(m), "samples": len(seq)}
        out["per_vehicle"][str(veh["track_id"])] = pv
        if wrong:
            out["violations"].append(_entry(veh, run_id, clip, m["first_frame"], m["last_frame"], fps, pv, reviews))
    return out


# ---------------------------------------------------------------- fixed cameras: direction in a zone
def detect(result: dict, run_id: str) -> dict:
    """Wrong-side check for one stored result. run_id is 'runs/clip02' or 'jobs/<id>' (used in violation ids)."""
    clip = result.get("clip_id")
    cam, rule = rule_for(clip if run_id.startswith("runs/") else None)
    if not rule:
        if cam and "fixed" in cam:
            return {"camera_id": cam, "assessed": False, "checked_vehicles": 0, "violations": [], "rules": [],
                    "not_assessed_reason": "no traffic rule is configured for this fixed camera"}
        return _detect_head_on(result, run_id, cam)
    out = {"camera_id": cam, "method": "zone_direction", "assessed": True, "checked_vehicles": 0, "violations": [], "rules": []}
    v = result.get("video") or {}
    W, H = v.get("width"), v.get("height")
    out["rules"] = [{"name": z["name"], "allowed_direction": z["allowed_direction"], "polygon": z["polygon"]} for z in rule["zones"]]
    out["camera_description"] = rule.get("description")
    motion = None
    ref = rule.get("reference_frame")
    video = ROOT / "TRACEVISION_DATA" / "raw" / "test_videos" / f"{clip}.mp4"
    if ref is not None:
        if not video.exists() and not (run_path(run_id) / "camera_motion.json").exists():
            out.update(assessed=False, not_assessed_reason="the video is needed to remove camera movement and is not on this machine")
            out["rules"] = []
            return out
        motion = camera_motion(result, video, int(ref), run_path(run_id) / "camera_motion.json")
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
            out["per_vehicle"][str(veh["track_id"])] = (best or seen) | {"method": "zone_direction"}
        if best:
            out["violations"].append(_entry(veh, run_id, clip, best["first_frame"], best["last_frame"], fps,
                                            best | {"method": "zone_direction"}, reviews))
    return out


def _video_for(run_dir: Path, clip: str | None):
    ups = list(run_dir.glob("upload.*"))
    if ups:
        return ups[0]
    v = ROOT / "TRACEVISION_DATA" / "raw" / "test_videos" / f"{clip}.mp4"
    return v if v.exists() else None


def main():
    import argparse
    ap = argparse.ArgumentParser(description="wrong-side driving check over stored runs")
    ap.add_argument("--orient", action="store_true", help="compute CLIP orientation caches (needs open_clip) first")
    ap.add_argument("--jobs", action="store_true", help="also check uploaded clips in runs/jobs/")
    a = ap.parse_args()
    dirs = sorted((ROOT / "runs").glob("clip*/result.json"), key=lambda p: int(p.parent.name[4:]))
    if a.jobs:
        dirs += sorted((ROOT / "runs" / "jobs").glob("*/result.json"))
    rows = []
    for p in dirs:
        run_id = p.parent.relative_to(ROOT / "runs").as_posix()
        run_id = run_id if run_id.startswith("jobs/") else "runs/" + run_id
        r = json.loads(p.read_text(encoding="utf-8"))
        if a.orient and rule_for(r.get("clip_id") if run_id.startswith("runs/") else None)[1] is None:
            vid = _video_for(p.parent, r.get("clip_id"))
            if vid:
                orient_run(p.parent, vid)
        d = detect(r, run_id)
        rows.append((run_id, d))
        if d["assessed"]:
            state = f"{d.get('method')}: {d['checked_vehicles']} vehicles checked, {len(d['violations'])} flagged"
            if d.get("layout"):
                state += f" (layout {d['layout']})"
        else:
            state = "not assessed: " + d.get("not_assessed_reason", "")
        print(f"{run_id:22} {str(d['camera_id']):24} {state}")
        for v in d["violations"]:
            m = v["measurement"]
            if m.get("method") == "head_on_pass":
                extra = f"growth {m['growth']}x, front {m['p_front_median']}, rear {m['p_rear_median']}"
            else:
                extra = f"cos {m['cos_to_allowed']} against-flow {m['against_flow_share']}"
            print(f"        T{v['track_id']} {v['vehicle_type']} plate {v['plate']} {v['time_s'][0]}-{v['time_s'][1]} s  {extra}")
    assessed = [d for _, d in rows if d["assessed"]]
    print(f"\n{len(assessed)} clips assessed, {sum(d['checked_vehicles'] for d in assessed)} vehicles checked, "
          f"{sum(len(d['violations']) for d in assessed)} flagged")


if __name__ == "__main__":
    main()
