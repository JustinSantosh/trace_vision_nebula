import csv
from pathlib import Path
import cv2

csv_path = Path("TRACEVISION_DATA/evaluation/test_clip_labels.csv")
video_dir = Path("TRACEVISION_DATA/raw/test_videos")

with open(csv_path, mode="r", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

print(f"Total labelled vehicles in test_clip_labels.csv: {len(rows)}")

clips = set(r["clip_id"] for r in rows)
print(f"Unique clips: {len(clips)} -> {sorted(list(clips))}")

colours = set(r["colour"] for r in rows)
print(f"Unique ground-truth colours: {len(colours)} -> {sorted(list(colours))}")

missing_videos = []
crop_count = 0
for r in rows:
    clip_id = r["clip_id"]
    vid_file = video_dir / f"{clip_id}.mp4"
    if not vid_file.exists():
        if clip_id not in missing_videos:
            missing_videos.append(clip_id)
    else:
        crop_count += 1

print(f"Available video files for {crop_count} vehicle instances.")
if missing_videos:
    print(f"Missing video files for clips: {missing_videos}")

