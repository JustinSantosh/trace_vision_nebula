# D1 / D2 Replacement Candidates

> **Correction, 2026-11-22 (after download):** I first recommended Roboflow **b8iqo**, but it is **not usable**. When downloaded (v3, 1750/372/372), **2,439 of its 2,442 boxes cover more than 80% of the image**. Visual inspection shows **synthetic, computer-rendered plate images** (flat fonts, artificial noise) with no vehicles or road scenes. A detector trained on it would learn that the whole image is a plate. It has been moved to `raw/_rejected/b8iqo_synthetic/`. The cause: I judged it from page metadata and did not view sample images.
>
> **New D1 choice: Roboflow Quobotic v3.** I checked its sample images in the browser, and they are real Indian vehicle photos with plate boxes. 2,574 images: train 2,069 (with ×3 augmentation, horizontal flip, in train only), valid 336, test 169. Stretched to 640×640. CC BY 4.0.
> - **Shared source:** Quobotic's filenames (`video10_990.jpg`, `car-wbs-…`, `UP24.jpg`, UUID names) match the four zenitsu09 sub-sources, so **zenitsu09 crops were most likely cut from Quobotic images.** This is fine for evaluating Awiros, which we never train, but the two sets must not be treated as independent.
> - **Near-duplicates:** `video*_NNNN` are consecutive frames, so near-duplicate frames may sit across the train/valid/test splits. `validate_plate_dataset.py` must report this (it must not silently fix it).

**Date:** 2026-11-22. **Nothing has been downloaded.** Contents were checked through the HF Hub API (file trees), the HF dataset-viewer API (schema, statistics and sample rows), and the dataset cards. Licences are **as stated by the source and not legally verified**.

## Hugging Face, every candidate checked

| Repo | Real files? | Contents | Indian? | Licence | Verdict |
|---|---|---|---|---|---|
| `witvix/indian-truck-license-plates-sample` | Yes, 122.9 MB | 470 full images with 589 plate boxes. **Each box has its plate text.** YOLO `data.yaml` and labels, COCO JSON, `plates.csv`, plate crops. 43% night, 69% two-row plates, 29 state codes, 21% of plates under 50 px tall. Captured Aug–Sep 2026. | Yes (trucks, buses and vans at logistics gates) | **CC-BY-NC-4.0**, gated by a form | **Best single source for both the detection test and the OCR test.** Mostly commercial vehicles, so it skews away from cars and two-wheelers. Phone photos, not CCTV. |
| `zenitsu09/indian-number-plate` (identical copy: `Gamester03/indian-number-plate`) | Yes, 5.9 MB parquet | 1,709 **plate crops** with `plate_text` and the original bbox, merged from 4 sub-sources, with 965 unique plate texts. Sub-source `plates3`: 600 crops, 598 unique, 35 states, small low-resolution crops (about 60–85×14–35 px). `plates1`: 654 crops, 137 unique, **consecutive video frames** (e.g. `video3_1760…1800`). `plates2`: 417 crops, 230 unique. `plates`: 38 rows that are **Roboflow augmented duplicates** of 13 base images. | Yes (MH, DL, KA, CG and others) | **Not stated** | **Best D2 replacement for the OCR benchmark** if we use `plates3` + `plates2`, deduplicated by plate text. `plates1` is useful for multi-frame testing. There is a licence risk: use it for internal evaluation only and do not redistribute. Labels need checks: there are entries such as `BLUR`, `MH14TC206AN` and `MH4705851`. |
| `adityaver/Indian-Military_and_Civilian-Plates` | Yes, 76.8 MB | 994 images, YOLO `images/` + `labels/` + `data.yaml` | Yes, per the title | Card is gated (manual approval) | Possible detection source. Approval time is unknown. Contents unverified until access is granted. |
| `Dataclusterlabspvtltd/indian-number-plates-dataset` | Yes, 155.6 MB | 47 images with VOC XML | Yes | CC-BY-NC-ND-4.0 | Too small. The ND clause blocks derived crops. Reject. |
| `atul10/numberplate_ocr_v2` | Yes, 63.9 MB | 2,503 small images (~200×100) with YOLO box strings and **no text** | Unverified (no card) | Not stated | Reject: no card, no licence, no text labels. |
| `Hirwa/Automatic_Number_Plate_Recognition` | Yes, 680 MB | 1,852 images at 1920×1080. Classes are plate strings such as `RAG320P`. | **No (Rwandan)** | CDLA-Sharing-1.0 | Reject: foreign plates. |
| `prithivMLmods/Number-Plate-Recognition` | Yes, 41 MB | 228 images with colour and plate JSON | **No** (e.g. `77-ZFK-8`) | Apache-2.0 | Reject: foreign plates. |
| `DamarJati/IND-number-plate` | Yes, 44 MB | Folders named by plate, e.g. `A1033HZ` | **No (Indonesian format)** | Not stated | Reject. |
| `sonup/indian_vehicle`, `ybli/yolo-license-plate-number-recognition`, all 10 `thundarstrom/*` repos | **No** (card only) | n/a | n/a | n/a | Reject: empty. |

## Roboflow Universe (pages read in a browser without signing in; download needs a free account and API key)

| Project | Images / splits | Labels | Licence | Notes |
|---|---|---|---|---|
| `indian-number-plate-dataset/indian-number-plate-recognition-b8iqo` | 2,494; split 1750 / 372 / 372 | Boxes, 1 class (`NumberPlate`) | CC BY 4.0 | **REJECTED after download: synthetic, full-frame plates.** Its published model reports mAP50 95.8%. India is shown by the name only. Generated Aug 2025. |
| `quobotic/indian-number-plate` | v3: 2,574 (2069 / 336 / 169; ×3 augmentation in train only) | Boxes, 1 class | CC BY 4.0 | **Selected for D1.** Real vehicle photos (checked visually). Same upstream source as zenitsu09. |
| `payals-workspace-gz1ub/indian-number-plate-detection-g7voe` | 1,650; split 1156 / 330 / 164 | Boxes **with the plate string as the class name** (983 classes, plus `blur`) | CC BY 4.0 | Usable for OCR: crop each box and use the class name as the text. **It shares plates with zenitsu09 `plates3`** (e.g. `BR01AW1250`), so they probably come from the same upstream source. Do not count them as independent. |
| `bharani-ejlrn/indian-number-plate-detection` | 1,438 | Boxes | CC BY 4.0 | Reject: its model reports mAP50 8.9%, which suggests bad labels. |
| `carlpr/indian_car_license_plate_ocr` | 1,002 | Boxes only (no text, despite the name) | CC BY 4.0 | Low value. |

## Kaggle (read from the public metadata API; download needs a Kaggle account)

| Dataset | Size | Labels | Licence | Notes |
|---|---|---|---|---|
| `sunrajbishnolia/license-plate-detection` | 15,338 images, 918 MB | YOLO boxes | "Other", but none is actually stated | Reject: a Roboflow export with about 3 augmented copies per image, **including in test**, so the splits leak. Source unknown. |
| `kedarsai/indian-license-plates-with-labels` | ~2,181 images, 68 MB | YOLO boxes | CC0 | Only 181 are hand-labelled. About 2,000 are **auto-labelled by YOLOv5**. Weak as training data. |
| `dataclusterlabs/indian-number-plates-dataset` | 156 MB (free sample) | Boxes plus `number_plate_text` | CC0 (per Kaggle) | The free part is a sample of a paid set. The HF copy says CC-BY-NC-ND, so **the two licences conflict**. Avoid. |
| `umar1103/final-licence` | ~30k images | Text as filename, no boxes | CC BY 4.0 | Reject: synthetic and real images mixed, with non-Indian strings. |
| `deepakat002/…-yolo-annotation`, `ronakgohil/license-plate-dataset` | 97 MB / 1,695 images | YOLO boxes | CC0 | Possibly synthetic, or Indian only by tag. Extras only. |

## Recommendation

**D1 replacement (plate-detector fine-tune on Colab):**
- ~~Primary: Roboflow b8iqo~~ **Rejected: synthetic full-frame plates (see the correction above).**
- **Primary: Roboflow Quobotic v3** (export as YOLOv8 and keep its splits).
- **Out-of-domain detection test:** **witvix** (470 images: night, two-row plates, small plates). Never train on it.

**D2 replacement (Awiros OCR benchmark; OCR is never trained, so these are evaluation-only):**
- **Primary:** the **witvix** plate texts (589 plates). This is the hardest and most realistic set: 43% night and 69% two-row. Licence CC-BY-NC-4.0, which is fine for a hackathon. Gated by a form the team must fill in, which asks for name, institution, email and intended use.
- **Secondary:** **Payals** test split (164 images). CC BY 4.0, with crops cut from the boxes and the class names used as text. Drop `blur` and flag strings that fail the regex.
- **Backup with no account or form:** **zenitsu09** `plates3` + `plates2` (about 830 unique plates, crops ready). No licence is stated, so use it for internal evaluation only and do not redistribute. Exclude any plate that also appears in the Payals set to avoid double-counting.
- **Multi-frame bonus:** zenitsu09 `plates1` contains consecutive video frames of the same plate. It is a ready-made supplementary sequence set with Indian plates, and a better fit than UFPR-ALPR.

**Actions for the team (I cannot do these: they need your accounts or personal details):**
1. ~~b8iqo~~ Export **Quobotic v3** as YOLOv8 into `raw/plate_detection/`.
2. Fill in the witvix access form on HF, then download it into `raw/ocr_corpus/witvix/`.
3. Approve installing `huggingface_hub`, which zenitsu09 and witvix need, or download them manually.

**Estimated download size:** b8iqo ≈ 0.3–0.6 GB (unverified estimate), witvix 123 MB, zenitsu09 6 MB, Payals ≈ 0.2–0.4 GB (unverified estimate).

**Also noted, not verified:** the IIT "Indian Licence Plate Dataset in the wild" (arXiv 2111.06054, about 16k images, character labels) may be a stronger OCR benchmark. Its licence and access are unknown.
