# P4: End-to-end pipeline

**Date:** 2026-11-23 · **Approved by the owner:** "Approve P4" and "approve all phases remaining" · Code: `tracevision/pipeline.py`, `ocr_worker.py`, `colour.py` · Outputs: `runs/<clip>/result.json` (+ evidence images in `runs/<clip>/vehicles/`, git-ignored)

```powershell
python -m tracevision.pipeline                      # all clips
python -m tracevision.pipeline --clips clip03       # one clip
```

## What it does per clip
1. **Detect and track** every 2nd frame (UVH-26, 640 px, ByteTrack, **class-agnostic NMS**). Keep tracks with ≥ 5 detections that are at least 0.4% of the frame at some point.
2. **Re-link by position:** a fragment that starts within 30 frames of another's end, close to it, with a compatible type, is joined to it.
3. **Best frames:** up to 8 largest non-edge detections per track, ≥ 4 frames apart. A second pass reads only those frames.
4. **Plate:** YOLOv8n on the vehicle crop upscaled to 640 px, confidence ≥ 0.5. **Plates under 16 px are not read** (M8). Quality = size + sharpness + confidence.
5. **OCR:** Awiros in its **own process** (M7), the best 5 plate crops per track, at about 15 ms each.
6. **Re-link by plate:** tracks whose fused plates agree on ≥ 6 readable characters are one vehicle. **Exception:** if the two tracks exist in the same frames with boxes that are *not* the same object (IoU ≤ 0.5), they are different vehicles. The plate stays with the track it was read best on, and the other says "no own plate: belongs to the overlapping vehicle".
7. **Fuse** (P3), **type** (vote over non-edge detections), **colour** (body band, k-means, `unknown` when dark), **match** (P3; with a readable plate only).
8. `result.json`: every vehicle with frames, type, colour, plate status, the fused plate with per-position confidence, per-frame reads, decision, reason, and the top-5 with match scores and reasons.

## Problems found while building it, and the fixes
| Found on | Problem | Fix |
|---|---|---|
| clip03 | The same car came out as up to 4 "vehicles" (the moving camera keeps losing it) | Plate-based re-link (step 6) |
| clip11, clip03, clip01 | **One vehicle detected twice as different classes** (SUV box + truck box) because suppression was per class. Their shared plate then merged separate vehicles. | `agnostic_nms=True`, plus the IoU rule in step 6 |
| clip11 | A scooter rider's box contained the car's plate | Simultaneous, non-overlapping tracks never merge; the plate goes to its best-read owner |
| clip10 | Tracks with 1–4 readable characters were labelled "ambiguous" | Too little plate evidence now gives **no confident match** ("can't tell"), not "ambiguous". Tests and calibration unchanged (26/26, holdout 41/41). |
| clip03 | Colour read windscreen glass and bumper as body paint | Body band 30–65% of height; bright, washed-out colours count as white |

## First results (all 11 clips, RTX 3050)
| Clip | Camera | Vehicles | Plates read | Matches | Time |
|---|---|---|---|---|---|
| clip01 | moving | 12 | 4 | 2 | 9.2 s |
| clip02 | **fixed** | 31 | 0 | 0 | 3.5 s |
| clip03 | moving | 13 | 4 | 2 | 7.5 s |
| clip04 | moving | 9 | 3 | 2 | 4.1 s |
| clip05 | moving | 18 | 2 | 0 | 5.6 s |
| clip06 | **fixed** | 65 | 0 | 0 | 9.5 s |
| clip07 | moving | 6 | 0 | 0 | 5.3 s |
| clip08 | moving | 10 | 3 | 1 | 5.5 s |
| clip09 | moving | 14 | 3 | 0 | 9.9 s |
| clip10 | moving, 4K | 9 | 5 | 0 | 18.3 s |
| clip11 | night, 4K | 2 | 1 | 1 | 9.8 s |

**Quick look against the labels** (the formal numbers come in P6):
- **8 of the 9 `in_registry = yes` vehicles are matched to the right registry entry**, one of them from a partial plate (`UP1?FT?44?` → `UP16FT9444`).
- **No vehicle labelled `no` got a confident match.**
- The miss is clip07 `DL8CAH1004`: its plate was never readable (all crops under 16 px).
- CCTV-style clips (02, 06): every plate is under 16 px, so every vehicle is "no confident match". That's correct behaviour, not a failure (C7, E7).
- **Weak spots:** colour (whites in haze come out grey or blue) and car-versus-SUV type. Both are measured in P6.
