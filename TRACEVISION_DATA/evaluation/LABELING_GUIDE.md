# Test-clip labelling guide (Phase 0D)

1. Put clips in `TRACEVISION_DATA/raw/test_videos/`. Re-run `create_test_clip_template.py`, then fill in **clips.csv** (source, url, licence, country, camera_id, time_of_day, scenarios_covered).
2. Copy `test_clip_labels_TEMPLATE.csv` to **`test_clip_labels.csv`**. Add or delete rows so there is **one row per target vehicle**.
3. Run `python TRACEVISION_DATA/scripts/validate_test_labels.py` and fix whatever it reports. The script never edits your labels.

## Columns
| Column | Rule |
|---|---|
| target_vehicle_id | Unique, e.g. `clip01_v01` |
| first_frame / last_frame | **Original** frame indices (`frames_index.csv` from `extract_test_video_frames.py`, or a video player's frame counter) |
| timestamp_first | Seconds, e.g. `12.4` |
| vehicle_bbox_first_frame | `x1,y1,x2,y2` in pixels on first_frame (required) |
| plate_bbox_first_frame | Same format, optional |
| plate_text_truth | **UPPERCASE, no spaces. Write `?` for every character a human cannot read in the clip. Never guess.** Example `CG04?B12?4` |
| unreadable_positions | 1-based positions of the `?` characters, `;`-separated, e.g. `5;9`. Blank if none. |
| plate_readability | `full` (no `?`), `partial` (some `?`), `none` (no character readable: leave plate_text_truth blank) |
| colour | one of: white, black, silver, grey, red, blue, green, yellow, brown, orange, other, unknown |
| vehicle_type | one of: car, SUV, motorcycle, scooter, auto_rickshaw, bus, truck, van, bicycle, other, unknown |
| make / model | Only if **verified** (badge visible, or it is our own car). Otherwise blank. |
| in_registry | `yes` / `no`. **At least 2 vehicles must be `no`** (no-match test). |
| cross_camera_group_id | Same id on the rows for the same physical vehicle in **different** clips, e.g. `X1`. Only if you **know** it is the same vehicle (you filmed it). Looking similar is not enough. |
| registry_plate_full | Optional. The full plate if you know it from **outside** the clip (e.g. your own vehicle), needed to put a partly-readable vehicle into the registry. Never inferred from the video. |
| notes | Anything odd: occlusion, night, glare, two-row plate … |

## Coverage to aim for (5–8 clips)
Clear daylight plate · blurry plate · partly occluded plate · motorcycle/scooter · auto-rickshaw · truck/bus · night · several vehicles in one frame · similar-looking vehicles · **same vehicle in two clips (≥ 1)** · **vehicle not in registry (≥ 2)** · partly visible plate with unreadable characters.

Privacy: plates of vehicles in our clips only ever go into the registry as `evaluation_seed` rows. No owner names, phone numbers or addresses anywhere.
