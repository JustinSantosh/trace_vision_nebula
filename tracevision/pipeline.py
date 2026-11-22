"""End-to-end pipeline (P4): clip -> vehicles with fused plate, type, colour and registry candidates -> result.json

    python -m tracevision.pipeline                       # all clips in TRACEVISION_DATA/raw/test_videos
    python -m tracevision.pipeline --clips clip02 clip03 --out runs

Stages (PIPELINE.md): 1 ingest - 2 vehicle detect + type (UVH-26) - 3 track (ByteTrack) + re-link - 4 best frames -
5 plate detect (YOLOv8n, on the upscaled vehicle crop) - 6 OCR (Awiros, separate process) - 7 fuse - 8 colour - 9 match.
Plates shorter than `min_plate_height_px` are reported unreadable and never OCR'd (M8). Nothing is guessed.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

from . import ROOT, load_config
from .colour import estimate_colour
from .fuse import fuse
from .match import decide, load_registry, rank

CMAP = json.loads((ROOT / "TRACEVISION_DATA/models/class_mapping.json").read_text(encoding="utf-8"))
VIDEOS = ROOT / "TRACEVISION_DATA/raw/test_videos"
CLIPS_CSV = ROOT / "TRACEVISION_DATA/evaluation/clips.csv"


def vtype_of(cls):
    return CMAP["mapping"][str(int(cls))]["type"]


def compatible(a, b):
    if a == b:
        return True
    sa, sb = set(a.split("/")), set(b.split("/"))
    return bool(sa & sb) or any(sa & set(g) and sb & set(g) for g in CMAP["compatible_types"])


def camera_type(clip_id):
    import csv
    if CLIPS_CSV.exists():
        for r in csv.DictReader(open(CLIPS_CSV, encoding="utf-8")):
            if r["clip_id"] == clip_id:
                return "fixed_cctv_style" if "fixed" in r.get("camera_id", "") else "moving_camera"
    return "unknown"


# ---------------------------------------------------------------- stage 1-3: detect, track, re-link
def track_clip(video, model, pc):
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    model.predictor = None                       # fresh tracker state for every clip
    tracks, idx = defaultdict(list), -1
    while True:
        ok, f = cap.read()
        if not ok:
            break
        idx += 1
        if idx % pc["detect_every"]:
            continue
        # agnostic_nms: one vehicle must not survive as two boxes of different classes (P4: SUV + truck on one car)
        r = model.track(f, persist=True, tracker="bytetrack.yaml", imgsz=pc["imgsz"], conf=pc["vehicle_conf"],
                        agnostic_nms=True, device=0, verbose=False)[0]
        if r.boxes.id is None:
            continue
        for b, tid, c, s in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.id.int().cpu().numpy(),
                                r.boxes.cls.int().cpu().numpy(), r.boxes.conf.cpu().numpy()):
            x1, y1, x2, y2 = [float(v) for v in b]
            edge = x1 <= 2 or y1 <= 2 or x2 >= W - 2 or y2 >= H - 2
            tracks[int(tid)].append({"frame": idx, "type": vtype_of(c), "conf": float(s), "box": [x1, y1, x2, y2],
                                     "edge": edge, "area": (x2 - x1) * (y2 - y1)})
    cap.release()
    return tracks, {"fps": fps, "width": W, "height": H, "frames": idx + 1}


def track_type(dets):
    use = [d for d in dets if not d["edge"]] or dets          # edge-cut boxes don't vote (C6)
    votes = Counter()
    for d in use:
        votes[d["type"]] += d["conf"]
    t, v = votes.most_common(1)[0]
    return t, round(v / sum(votes.values()), 3)


def relink(tracks, pc):
    """Join fragments of one vehicle: B starts soon after A ends, near A's last box, with a compatible type."""
    items = sorted(tracks.items(), key=lambda kv: kv[1][0]["frame"])
    merged, parent = {}, {}
    for tid, dets in items:
        best = None
        for aid, adets in merged.items():
            last = adets[-1]
            gap = dets[0]["frame"] - last["frame"]
            if not (0 < gap <= pc["relink_gap_frames"]):
                continue
            if not compatible(track_type(adets)[0], track_type(dets)[0]):
                continue
            ax1, ay1, ax2, ay2 = last["box"]; bx1, by1, bx2, by2 = dets[0]["box"]
            diag = ((ax2 - ax1) ** 2 + (ay2 - ay1) ** 2) ** 0.5
            dist = (((ax1 + ax2) - (bx1 + bx2)) ** 2 / 4 + ((ay1 + ay2) - (by1 + by2)) ** 2 / 4) ** 0.5
            ratio = dets[0]["area"] / max(last["area"], 1)
            if dist <= pc["relink_max_center_dist"] * diag and 0.4 <= ratio <= 2.5:
                if best is None or gap < best[1]:
                    best = (aid, gap)
        if best:
            merged[best[0]] = merged[best[0]] + dets
            parent[tid] = best[0]
        else:
            merged[tid] = list(dets)
    return merged, parent


# ---------------------------------------------------------------- stage 4-5: best frames, plates
def pick_frames(dets, n, gap):
    pool = sorted([d for d in dets if not d["edge"]] or dets, key=lambda d: -d["area"])
    out = []
    for d in pool:
        if all(abs(d["frame"] - o["frame"]) >= gap for o in out):
            out.append(d)
        if len(out) == n:
            break
    return out


def crop(img, box, pad=0.04):
    H, W = img.shape[:2]
    x1, y1, x2, y2 = box
    px, py = (x2 - x1) * pad, (y2 - y1) * pad
    x1, y1 = int(max(0, x1 - px)), int(max(0, y1 - py))
    x2, y2 = int(min(W, x2 + px)), int(min(H, y2 + py))
    return img[y1:y2, x1:x2]


def find_plate(vcrop, plate_model, conf):
    s = 640 / max(vcrop.shape[:2])
    up = cv2.resize(vcrop, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC) if s > 1 else vcrop
    r = plate_model.predict(up, imgsz=640, conf=conf, device=0, verbose=False)[0]
    if not len(r.boxes):
        return None
    i = int(r.boxes.conf.argmax())
    b = (r.boxes.xyxy[i].cpu().numpy() / (s if s > 1 else 1.0))
    x1, y1, x2, y2 = [int(v) for v in b]
    pc = vcrop[max(0, y1 - 2):y2 + 2, max(0, x1 - 2):x2 + 2]
    if pc.size == 0:
        return None
    g = cv2.cvtColor(cv2.resize(pc, (max(8, int(48 * pc.shape[1] / max(pc.shape[0], 1))), 48)), cv2.COLOR_BGR2GRAY)
    sharp = float(cv2.Laplacian(g, cv2.CV_64F).var())
    h = y2 - y1
    c = float(r.boxes.conf[i])
    quality = 0.5 * min(1.0, h / 40.0) + 0.3 * min(1.0, sharp / 300.0) + 0.2 * c
    return {"crop": pc, "height_px": h, "conf": round(c, 3), "sharpness": round(sharp, 1), "quality": round(quality, 3)}


# ---------------------------------------------------------------- one clip
def run_clip(video, out_dir, models, ocr, registry, cfg):
    pc, mcfg = cfg["pipeline"], cfg
    veh_model, plate_model = models
    clip_id = Path(video).stem
    t0 = time.perf_counter(); timing = {}
    raw, meta = track_clip(video, veh_model, pc)
    timing["detect_track_s"] = round(time.perf_counter() - t0, 1)
    min_area = pc["min_vehicle_area_frac"] * meta["width"] * meta["height"]
    kept = {k: v for k, v in raw.items() if len(v) >= pc["min_track_dets"] and max(d["area"] for d in v) >= min_area}
    tracks, parent = relink(kept, pc)

    # second pass: read only the frames we need
    t1 = time.perf_counter()
    want = defaultdict(list)
    chosen = {tid: pick_frames(d, pc["candidate_frames"], pc["min_frame_gap"]) for tid, d in tracks.items()}
    for tid, ds in chosen.items():
        for d in ds:
            want[d["frame"]].append((tid, d))
    vcrops = defaultdict(list)
    cap = cv2.VideoCapture(str(video)); idx = -1
    while want:
        ok, f = cap.read()
        if not ok:
            break
        idx += 1
        if idx in want:
            for tid, d in want.pop(idx):
                vcrops[tid].append((d, crop(f, d["box"])))
    cap.release()

    plates, ocr_jobs = {}, []
    pconf, minh = cfg["plate_detector"]["conf"], cfg["plate_detector"]["min_plate_height_px"]
    for tid, items in vcrops.items():
        found = []
        for d, vc in items:
            p = find_plate(vc, plate_model, pconf)
            if p:
                p["frame"] = d["frame"]; found.append(p)
        plates[tid] = found
        readable = sorted([p for p in found if p["height_px"] >= minh], key=lambda p: -p["quality"])[:pc["ocr_top_k"]]
        for p in readable:
            ocr_jobs.append((tid, p))
    timing["plates_s"] = round(time.perf_counter() - t1, 1)
    t2 = time.perf_counter()
    reads = ocr.read([p["crop"] for _, p in ocr_jobs]) if ocr_jobs else []
    by_track = defaultdict(list)
    for (tid, p), r in zip(ocr_jobs, reads):
        by_track[tid].append({"frame": p["frame"], "quality": p["quality"], "chars": r["chars"], "text": r["text"],
                              "ms": r["ms"], "height_px": p["height_px"]})
    timing["ocr_s"] = round(time.perf_counter() - t2, 1)

    # plate-based re-link (C6): tracks whose fused plates agree are the same vehicle (the moving camera loses and
    # re-finds cars). Plate evidence beats box position, so this joins tracks the spatial re-link could not.
    prelim = {tid: fuse(rd, cfg) for tid, rd in by_track.items()}
    def same_plate(a, b):
        if len(a) != len(b):
            return False
        both = [(x, y) for x, y in zip(a, b) if x != "?" and y != "?"]
        return len(both) >= pc.get("plate_link_min_known", 6) and all(x == y for x, y in both)
    root = {tid: tid for tid in tracks}
    def find(x):
        while root[x] != x:
            x = root[x]
        return x
    frames_of = {t: {d["frame"] for d in tracks[t]} for t in tracks}
    box_at = {t: {d["frame"]: d["box"] for d in tracks[t]} for t in tracks}
    def iou(a, b):
        ix = max(0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
        inter = ix * iy; u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
        return inter / u if u > 0 else 0.0
    def coexist(ga, gb):
        """True if the groups are DIFFERENT vehicles seen at the same time (shared frames, boxes not the same object).
        Simultaneous tracks whose boxes overlap heavily (IoU > 0.5) are one vehicle detected twice -> not 'coexisting'."""
        ious = []
        for a in ga:
            for b in gb:
                for fr in frames_of[a] & frames_of[b]:
                    ious.append(iou(box_at[a][fr], box_at[b][fr]))
        return len(ious) > 2 and float(np.mean(ious)) <= 0.5
    members_of = {t: [t] for t in tracks}
    ids = sorted(prelim, key=lambda t: tracks[t][0]["frame"])
    plate_owner_dropped = {}
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if same_plate(prelim[a].text, prelim[b].text):
                ra, rb = find(a), find(b)
                if ra == rb:
                    continue
                if coexist(members_of[ra], members_of[rb]):
                    # same plate inside two simultaneous boxes: it belongs to the track where it was read best
                    qa = np.mean([x["height_px"] for x in by_track[a]]); qb = np.mean([x["height_px"] for x in by_track[b]])
                    loser = b if qa >= qb else a
                    plate_owner_dropped[loser] = b if loser == a else a
                    continue
                root[rb] = ra
                members_of[ra] = members_of[ra] + members_of.pop(rb)
    for loser, owner in plate_owner_dropped.items():
        by_track.pop(loser, None)
    groups = defaultdict(list)
    for tid in tracks:
        groups[find(tid)].append(tid)
    plate_merged = {}
    for r, members in groups.items():
        if len(members) == 1:
            continue
        tracks[r] = sorted(sum((tracks[m] for m in members), []), key=lambda d: d["frame"])
        for m in members:
            if m == r:
                continue
            vcrops[r] = vcrops.get(r, []) + vcrops.pop(m, [])
            plates[r] = plates.get(r, []) + plates.pop(m, [])
            by_track[r] = by_track.get(r, []) + by_track.pop(m, [])
            tracks.pop(m)
            parent[m] = r
            for k, v in list(parent.items()):
                if v == m:
                    parent[k] = r
        plate_merged[r] = sorted(members)
        # keep the best K reads of the merged group
        by_track[r] = sorted(by_track[r], key=lambda x: -x["quality"])[:max(pc["ocr_top_k"], 8)]

    # assemble vehicles
    t3 = time.perf_counter()
    vdir = Path(out_dir) / "vehicles"; vdir.mkdir(parents=True, exist_ok=True)
    vehicles = []
    for tid, dets in sorted(tracks.items(), key=lambda kv: kv[1][0]["frame"]):
        vtype, tconf = track_type(dets)
        items = sorted(vcrops.get(tid, []), key=lambda x: -x[0]["area"])
        col = estimate_colour([c for _, c in items[:pc["colour_frames"]]], vtype)
        found, rd = plates.get(tid, []), by_track.get(tid, [])
        if rd:
            fused = fuse(rd, cfg)
            plate_status = "read" if fused.text.strip("?") else "unreadable (low OCR confidence)"
        else:
            fused = None
            if tid in plate_owner_dropped:
                plate_status = f"no own plate: the plate seen in this box belongs to the overlapping vehicle (track {plate_owner_dropped[tid]})"
            elif not found:
                plate_status = "no plate detected"
            else:
                plate_status = f"unreadable (plate too small: max {max(p['height_px'] for p in found)} px < {minh} px)"
        if fused and fused.text.strip("?"):
            q, known, cands = rank(fused.text, col["label"], vtype, registry, cfg)
            m = decide(q, col["label"], vtype, known, cands, cfg)
            decision, reason = m.decision, m.decision_reason
            cand_out = [c.__dict__ for c in m.candidates]
        else:
            decision, reason, cand_out = "no_confident_match", f"plate {plate_status}: cannot identify from the plate", []
        # evidence images for the report
        if items:
            cv2.imwrite(str(vdir / f"t{tid}_vehicle_f{items[0][0]['frame']}.jpg"), items[0][1])
        for r in rd:
            p = next(p for p in found if p["frame"] == r["frame"])
            cv2.imwrite(str(vdir / f"t{tid}_plate_f{r['frame']}.jpg"), p["crop"])
        vehicles.append({
            "track_id": tid, "merged_track_ids": sorted([tid] + [k for k, v in parent.items() if v == tid]),
            "first_frame": dets[0]["frame"], "last_frame": dets[-1]["frame"],
            "first_time_s": round(dets[0]["frame"] / meta["fps"], 2), "n_detections": len(dets),
            "first_box": [round(v) for v in dets[0]["box"]],
            "type": {"label": vtype, "vote_share": tconf, "detector_conf_mean": round(float(np.mean([d["conf"] for d in dets])), 3)},
            "colour": col,
            "plate": {"status": plate_status,
                      "fused": fused.text if fused else None,
                      "unknown_positions": fused.unknown_positions if fused else None,
                      "positions": [p.__dict__ for p in fused.positions] if fused else [],
                      "warnings": fused.warnings if fused else [],
                      "per_frame_reads": [{"frame": r["frame"], "text": r["text"], "height_px": r["height_px"],
                                           "quality": r["quality"], "char_probs": [c["prob"] for c in r["chars"]]} for r in rd],
                      "plates_detected": len(found)},
            "decision": decision, "decision_reason": reason, "candidates": cand_out})
    timing["assemble_s"] = round(time.perf_counter() - t3, 1)
    timing["total_s"] = round(time.perf_counter() - t0, 1)
    result = {"clip_id": clip_id, "camera_type": camera_type(clip_id), "video": meta,
              "processed_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "config": {k: cfg[k] for k in ("pipeline", "plate_detector", "fusion", "match")},
              "summary": {"raw_tracks": len(raw), "kept_tracks": len(kept), "vehicles_after_relink": len(vehicles),
                          "plates_read": sum(1 for v in vehicles if v["plate"]["status"] == "read"),
                          "decisions": dict(Counter(v["decision"] for v in vehicles))},
              "timing": timing, "vehicles": vehicles,
              "note": "match_score is a heuristic ranking score, not a probability. '?' marks characters that could not be read."}
    (Path(out_dir) / "result.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clips", nargs="*", default=None, help="clip ids (default: all in raw/test_videos)")
    ap.add_argument("--out", default=str(ROOT / "runs"))
    a = ap.parse_args()
    cfg = load_config()
    clips = a.clips or sorted(p.stem for p in VIDEOS.glob("clip*.mp4"))
    from .ocr_worker import OCRWorker
    with OCRWorker(device="gpu") as ocr:                     # start Paddle first, in its own process
        from ultralytics import YOLO
        veh = YOLO(str(ROOT / "TRACEVISION_DATA/models/weights/UVH-26-MV-YOLOv11-S.pt"))
        plate = YOLO(str(ROOT / "TRACEVISION_DATA/models/weights/plate_yolov8n_quobotic.pt"))
        registry = load_registry()
        for cid in clips:
            r = run_clip(VIDEOS / f"{cid}.mp4", Path(a.out) / cid, (veh, plate), ocr, registry, cfg)
            print(cid, r["camera_type"], r["summary"], r["timing"], flush=True)


if __name__ == "__main__":
    main()
