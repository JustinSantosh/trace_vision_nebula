"""P1 smoke test: UVH-26 + ByteTrack on test clips, every 2nd frame, GPU."""
import json, os, sys, time
from collections import Counter, defaultdict
import cv2, numpy as np
from ultralytics import YOLO

ROOT = r"E:\hack_a_sol"
OUT = sys.argv[1]
clips = sys.argv[2:]
cmap = json.load(open(ROOT + r"\TRACEVISION_DATA\models\class_mapping.json"))["mapping"]
model = YOLO(ROOT + r"\TRACEVISION_DATA\models\weights\UVH-26-MV-YOLOv11-S.pt")
os.makedirs(OUT, exist_ok=True)
summary = {}
for cid in clips:
    model.predictor = None  # fresh tracker per clip
    cap = cv2.VideoCapture(ROOT + rf"\TRACEVISION_DATA\raw\test_videos\{cid}.mp4")
    idx, n, t_model = -1, 0, 0.0
    tracks = defaultdict(list)
    snaps = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        idx += 1
        if idx % 2:
            continue
        t = time.perf_counter()
        r = model.track(f, persist=True, tracker="bytetrack.yaml", device=0, imgsz=640, conf=0.25, verbose=False)[0]
        t_model += time.perf_counter() - t
        n += 1
        if r.boxes.id is not None:
            for b, tid, c, s in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.id.int().cpu().numpy(), r.boxes.cls.int().cpu().numpy(), r.boxes.conf.cpu().numpy()):
                tracks[int(tid)].append((idx, int(c), float(s), (b[2] - b[0]) * (b[3] - b[1])))
        if idx in (0, 120, 240, 480):
            im = f.copy()
            if r.boxes.id is not None:
                for b, tid, c in zip(r.boxes.xyxy.cpu().numpy().astype(int), r.boxes.id.int().cpu().numpy(), r.boxes.cls.int().cpu().numpy()):
                    cv2.rectangle(im, tuple(b[:2]), tuple(b[2:]), (0, 255, 0), 2)
                    cv2.putText(im, f"{tid}:{cmap[str(c)]['type']}", (b[0], max(12, b[1] - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
            snaps.append(im)
    kept = {k: v for k, v in tracks.items() if len(v) >= 5}
    types = Counter()
    for v in kept.values():
        votes = Counter()
        for _, c, s, _ in v:
            votes[cmap[str(c)]["type"]] += s
        types[votes.most_common(1)[0][0]] += 1
    summary[cid] = {"frames_processed": n, "ms_per_frame": round(1000 * t_model / max(n, 1), 1),
                    "tracks_total": len(tracks), "tracks_ge5": len(kept), "types_of_tracks_ge5": dict(types),
                    "longest_track_detections": max((len(v) for v in kept.values()), default=0)}
    if snaps:
        h = 600
        row = np.hstack([cv2.resize(s, (int(s.shape[1] * h / s.shape[0]), h)) for s in snaps])
        cv2.imwrite(os.path.join(OUT, f"{cid}_tracks.jpg"), row, [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(cid, summary[cid], flush=True)
json.dump(summary, open(os.path.join(OUT, "p1_smoke_summary.json"), "w"), indent=2)
