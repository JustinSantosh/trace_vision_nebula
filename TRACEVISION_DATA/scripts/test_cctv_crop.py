import csv
from pathlib import Path
import cv2

csv_path = Path("TRACEVISION_DATA/evaluation/test_clip_labels.csv")
video_dir = Path("TRACEVISION_DATA/raw/test_videos")

with open(csv_path, mode="r", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

# Test first 3 available rows
for r in rows[:3]:
    clip_id = r["clip_id"]
    vid_file = video_dir / f"{clip_id}.mp4"
    frame_idx = int(r["first_frame"])
    bbox_str = r["vehicle_bbox_first_frame"]
    x1, y1, x2, y2 = [int(float(v)) for v in bbox_str.split(",")]
    
    cap = cv2.VideoCapture(str(vid_file))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    cap.release()
    
    if ret and frame is not None:
        h, w = frame.shape[:2]
        crop = frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
        print(f"Vehicle: {r['target_vehicle_id']} in {clip_id} (frame {frame_idx}): bbox=({x1},{y1},{x2},{y2}), frame shape={frame.shape}, crop shape={crop.shape}, ground_truth={r['colour']}")
    else:
        print(f"Failed to read frame {frame_idx} in {vid_file}")

