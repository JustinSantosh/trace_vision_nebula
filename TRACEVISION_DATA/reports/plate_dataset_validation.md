# Plate-Detection Dataset: Validation and Preparation (Phase 0B)

**Date:** 2026-11-22 · **Dataset:** Roboflow Quobotic "Indian number plate" v3 (CC BY 4.0), `raw/plate_detection/`
**Scripts:** `scripts/validate_plate_dataset.py` (read-only), `scripts/prepare_plate_detection.py` (raw → processed)
**Full numbers:** `plate_dataset_validation.json`. **Output:** `processed/plate_detection/` (ready to train).

## Verdict

**Ready for training**, from `processed/plate_detection/data.yaml`. The official splits are kept. Leakage across splits is real and is **reported, not fixed**. Use the leakage-free lists (below) for an honest second score.

## Integrity

| | train | valid | test |
|---|---|---|---|
| Images | 2,069 | 336 | 169 |
| Labels present | 2,069 | 336 | 169 |
| Boxes | 2,084 | 339 | 171 |
| Images with 2 plates | 15 | 4 | 2 |
| Background images (empty label) | 0 | 1 (`BR9_jpg…`, empty in the zip too) | 0 |
| Unreadable images / malformed lines / coords out of [0,1] / degenerate | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| Orphan labels | 0 | 0 | 0 |
| Polygon label lines (converted to boxes in `processed/`) | 226 | 30 | 19 |
| Paths over 260 chars (A18) | **10** | 0 | 0 |
| Image size | all 640×640 (stretched) | same | same |
| Classes | 1 (`IndianNumberPlate`) | | |

**Plate size** (on the 640×640 images): the median box covers 2.8% of the image area, with a median plate of about 185×68 px (p5 height about 32 px). Only 1 box is under 16 px tall. **These are much larger plates than CCTV gives,** so expect detector recall to fall on our clips (A13). Train on the clips' scale, using a larger `imgsz` or tiling, if needed.

## Leakage across the official splits (reported, not fixed)

1. **Every source video appears in all three splits.** There are frames from 10 videos (`video2`…`video12`), sampled every 10 frames. **62 of 169 test images (37%)** and 125 of 336 valid images come from videos that also have frames in train. Neighbouring frames are near-identical (for example `video6_930` (test) against `video6_940` (train)).
2. **dHash near-duplicates** (64-bit difference hash, also compared against the horizontally flipped image, Hamming ≤ 6): **13 valid** and **5 test** images. **All 15 pairs that were checked by eye are true duplicates.** They are the same photo uploaded under another name (for example `car-wbs-KL01CA2555` against `car-wbs-KA01CA2555`), a mirrored copy, or frames 10 apart. A threshold of ≤ 6 is strict, so this is a **lower bound**.
3. The same Roboflow source name never appears in two splits. Roboflow's own augmentations stayed inside train.

**Effect:** test mAP on the official split will be **inflated**.

**What we did:**
- Kept the official split as primary, as the spec requires.
- Wrote **`processed/plate_detection/leakage_free_test.txt`** (106 of 169) and **`leakage_free_valid.txt`** (205 of 336). These drop every image from a train video and every dHash near-duplicate.
- Report the detector on **both** sets. The headline remains our own clips (A13).

```powershell
yolo detect val model=best.pt data=E:/hack_a_sol/TRACEVISION_DATA/processed/plate_detection/data.yaml split=test        # official
# leakage-free: copy data.yaml, set  test: leakage_free_test.txt  and run the same command
```

## Other observations
- **Train contains mirrored copies** (Roboflow 50% horizontal flip), so some plates read backwards. That is fine for a detector, but **never crop train plates for OCR training or evaluation**.
- All images are stretched to 640×640, which distorts the plate aspect ratio. At inference, use Ultralytics' default letterbox on CCTV frames (A15).

## Processed copy: `processed/plate_detection/`

| File | What |
|---|---|
| `train|valid|test/images/<split>_<sha1(name)[:12]>.jpg` | **Byte-identical** copies (SHA-1 checked for every file, 2,574/2,574). Short names fix A18. |
| `train|valid|test/labels/*.txt` | Boxes only. 275 polygons → enclosing box. 0 needed clipping. Box counts match the source exactly. |
| `name_map.csv` | new name ↔ original name, image SHA-1, box count, polygons converted, source video |
| `data.yaml` | Relative paths, `nc: 1`, `names: ["IndianNumberPlate"]`. Pass its **absolute** path to Ultralytics. |
| `leakage_free_{valid,test}.txt` | Second, leakage-free evaluation lists (see above) |
| `prepare_log.json` | Run log |

The converted polygon boxes were checked visually on 6 images: they fit the plates. `raw/` is untouched. Git stores identical image bytes only once, so the processed copy adds almost nothing to the repository size.

**Not verified:** training itself. Ultralytics isn't installed yet (C2), so nobody has opened `data.yaml` with `yolo` yet. That is the first step in Phase 1.

## Reproduce
```powershell
python TRACEVISION_DATA/scripts/validate_plate_dataset.py --data TRACEVISION_DATA/raw/plate_detection --out TRACEVISION_DATA/reports
python TRACEVISION_DATA/scripts/prepare_plate_detection.py --src TRACEVISION_DATA/raw/plate_detection --dst TRACEVISION_DATA/processed/plate_detection --validation TRACEVISION_DATA/reports/plate_dataset_validation.json --overwrite
```
