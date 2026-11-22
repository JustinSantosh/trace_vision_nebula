# Test-clip labelling guide (Phase 0D)

**Only humans write these labels. Never guess a character: write `?`.** These labels are the answer key the whole system is graded against.

## Step by step (about 5–10 minutes per clip)

**0. Get the files.** `git pull`, then `git lfs pull`. The clips are in `TRACEVISION_DATA/raw/test_videos/` (clip01–09). clip10 and clip11 are Pexels stock and not in git: download them from the links in `clips.csv`, choosing the original 4K quality, and save them as `clip10.mp4` and `clip11.mp4`.

**About `test_clip_labels_AI_DRAFT.csv`:** it holds 36 machine-drafted rows (notes say "AI DRAFT - verify"), with review images in `label_review/`. **It is not ground truth.** You may start from it, but you must **check every field of every row against the clip**: plate characters (use `?` wherever *you* can't read one), frames, box, colour, type and in_registry. Fix what's wrong and delete rows for vehicles you can't verify. **Remove the "AI DRAFT" note only after checking the row.** Save the result as `test_clip_labels.csv`. Note that the draft marks 27 of 36 vehicles as `in_registry = no`, so decide registry membership yourselves (at least 2 `no`, the rest as you choose).

**1. Split the clips between labellers,** so two people never edit the same rows. For example: A takes clip01–04, B takes clip05–08, C takes clip09–11.
**Easiest way to work together:** import `test_clip_labels_TEMPLATE.csv` into one shared Google Sheet. Everyone fills only their own clips' rows. When finished, use File → Download → CSV, save it as `TRACEVISION_DATA/evaluation/test_clip_labels.csv` and commit it.

**2. Pick 3–5 target vehicles per clip.** Open `processed/test_video_frames/clipNN/contact_sheet_fps2.jpg`. Every thumbnail shows its **frame number** and time. Good targets:
- stay visible for at least 2–3 s
- show their plate at some point, even partly (partly readable plates are valuable)
- vary the type: car, two-wheeler, auto, truck or bus
On clip02 and clip06 (high, far views), plates are mostly unreadable. Label them `none`; the vehicle's type and colour still count.

**3. For each target, fill one row.** Add rows if you need more than 3 for a clip, giving them new ids such as `clip04_v04`.
- **first_frame / last_frame:** the frame numbers from the contact sheet where the vehicle first and last appears usefully.
- **timestamp_first:** the time shown on the thumbnail, in seconds.
- **vehicle_bbox_first_frame:** run `extract_test_video_frames.py` once to get full-size frames, or open the clip in a player at that time. Then open the frame in **Paint**: when you hover the mouse, the bottom bar shows pixel coordinates. Write the box as `x1,y1,x2,y2`, meaning top-left x, top-left y, bottom-right x, bottom-right y.
- **plate_text_truth:** zoom in (Ctrl + scroll). Write it **uppercase with no spaces**. **Write `?` for any character you cannot read.** For two-row plates, write the top row then the bottom row as one string.
- **unreadable_positions:** the positions of the `?` characters, counting from 1, e.g. `5;9`.
- **plate_readability:** `full` (no `?`), `partial` (some `?`) or `none` (nothing readable; leave the plate blank).
- **colour / vehicle_type:** use only the allowed words (table below).
- **in_registry:** `yes` or `no`. **Across all clips, mark at least 2 vehicles `no`** (the no-match test).
- **source / licence / country / camera_id:** already filled in. Leave them.

**4. Check.** Run `python TRACEVISION_DATA/scripts/validate_test_labels.py`. It lists every problem in plain English, for example "`?` positions don't match", "box outside the frame" or "colour not allowed", and **never changes your file**. Fix the rows and run it again until it reports 0 errors.

**Example row** (in a spreadsheet):
`clipXX | … | clipXX_v01 | 120 | 330 | 4.0 | 410,620,700,1010 | 470,880,600,930 | CG04AB12?4 | 9 | partial | white | SUV | | | yes | | plate partly hidden by a bike |`
The plate and numbers are invented for illustration and match no clip. Label what you actually see.

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

## Coverage to aim for across the labelled vehicles
Clear daylight plate · blurry plate · partly occluded plate · motorcycle/scooter · auto-rickshaw · truck/bus · night (clip11) · several vehicles in one frame · similar-looking vehicles (clip04) · two-row plate (clip08, clip10) · **same vehicle in two clips (≥ 1; the car pair to be filmed later)** · **vehicle not in registry (≥ 2)** · partly visible plate with unreadable characters.

Privacy: plates of vehicles in our clips only ever go into the registry as `evaluation_seed` rows. No owner names, phone numbers or addresses anywhere.
