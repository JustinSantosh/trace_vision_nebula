# Phase 0A — Dataset Audit

**Date:** 2026-11-22 · **Audit tool:** `scripts/inspect_datasets.py` (raw output: `reports/dataset_audit.json`)

## 1. Headline findings

1. **The working folder held no inputs.** `E:\hack_a_sol` was empty before this audit. Every `raw/` subfolder is empty, so there were no images, videos or labels to inspect.
2. **D1 and D2 cannot be downloaded: their Hugging Face repos have no data in them.** I listed the repo trees through the HF API on 2026-11-22:
   - `thundarstrom/indian-license-plate-detection`: `.gitattributes`, `README.md` and `data.yaml` only, 2.4 kB in total. The card claims 3,742 images, but there are no images or labels. `data.yaml` points to the uploader's local path `c:/projects/traffic-analytics-system/...` and declares `nc: 1`, `names: [license_plate]`.
   - `thundarstrom/indian-anpr-ocr-corpus`: `.gitattributes` and `README.md` only, 2.3 kB. The card claims 18,537 crops, but there is no `parseq_dataset/`, no `gt.txt` and no LMDB.
   - Both repos have a single `main` branch and no other refs. Neither is gated, so this is not an access problem. **The data was never uploaded.**
   - The maintainer's other 8 dataset repos (`indian-anpr-ocr-benchmark`, `augmented-indian-plate-detection`, `traffic-pipeline-sample-videos`, and others) are also card-only.
3. **The pretrained models are available and not gated.**
   - UVH-26: `weights/YOLOv11-S/UVH-26-MV-YOLOv11-S.pt` is 57.1 MB.
   - Awiros: `model.safetensors` is 149.4 MB. The repo also includes `test.py`, `en_dict.txt` and 10 sample plate crops.
4. **Tooling gaps on this machine:**
   - **FFprobe and FFmpeg are not installed.** The audit falls back to reading the video header with OpenCV, which gives FPS, frame count, resolution and FourCC, but the codec name is less reliable.
   - `huggingface_hub`, `ultralytics`, `paddlepaddle`, `paddleocr`, `safetensors`, `torch` and `imagehash` are not installed.
   - Python 3.12.6, OpenCV, Pillow, NumPy, pandas and PyYAML are present.
   - There is a local RTX 3050 6 GB laptop GPU. This is useful for inference later, though training stays on Colab as planned.
   - Free space on drive E: is 96 GB.
5. I noticed two `.mp4` files in `~/Downloads` (`DS.mp4` and `original-5adf…mp4`). **I did not inspect or use them** because they are outside the working folder. If they are intended test clips, move them into `raw/test_videos/` and record their source URL and licence.

## 2. Per-input audit

| ID | Input | Present locally | Source reachable | Content at source | Licence (per source page, unverified) | Suitability |
|---|---|---|---|---|---|---|
| D1 | Plate detection | No | Yes | **None** (card only) | CC-BY-4.0 | Blocked: no data |
| D2 | OCR corpus | No | Yes | **None** (card only) | CC-BY-4.0 | Blocked: no data |
| V1 | Kaggle ANPR clips | No | Not verified (Kaggle page only renders with JavaScript) | Unknown | Unknown | Pending download; licence must be checked on Kaggle |
| V2 | DenseWorld-115k | No | Yes, not gated | Manifest only (28 MB): `clips.csv` and `sources.json`. Clips are rebuilt locally from YouTube with yt-dlp at 480p. No object labels. | CC-BY-4.0 for metadata only. The videos remain YouTube creators' copyright, research use only. | Usable for a small set of evaluation clips. 480p limits plate readability. No redistribution. |
| V3 | Pexels / Pixabay | No | n/a | n/a | Pexels / Pixabay licences: free use, no attribution required, no standalone redistribution | Recommended main source of Indian CCTV-style clips |
| O1 | UFPR-ALPR | No | Gated (request by email from a university account, 1–5 business days) | 4,500 PNG images at 1920×1080, 150 vehicles | Custom academic, non-commercial, no redistribution | Optional. Request now only if wanted, since access takes days. |
| O2 | IEEE DataPort dashcam | No | Needs login or subscription | `DASHCAM DATA.zip`, 4.43 GB, .mov 1080p30 | CC-BY-4.0 | Optional. Large, no annotations, dashcam view. Not recommended. |

The image counts, dimensions, label formats, corrupt or missing samples and video metadata that this audit is supposed to report **cannot be filled in for any input, because none is present.** I have not estimated or copied any of these figures from the dataset cards and presented them as measured.

## 3. Missing inputs and proposed alternatives (nothing downloaded)

| Need | Status | Proposed action (needs your approval) |
|---|---|---|
| Plate-detection training set (replaces D1) | Missing | (a) Ask `thundarstrom` to upload the data by opening an HF discussion. (b) Use an alternative Indian plate set in YOLO format, such as a Roboflow Universe "Indian number plate" export or a Kaggle Indian licence-plate dataset. **I have not verified any candidate yet.** Each needs its licence, size and format checked. |
| OCR evaluation set (replaces D2) | Missing | (a) Ask for the upload, as above. (b) **Fallback that needs no download:** take the plate crops from our own labelled test clips as the OCR ground truth. It is small but it is real Indian plates and within our control. (c) Use Awiros's 10 sample crops only as a smoke test, never as a benchmark. |
| Test clips | Missing | Download 5–8 Indian traffic clips from Pexels or Pixabay (V3) first, then optionally V1. Record the page URL and licence for each. |
| FFprobe / FFmpeg | Missing | `winget install Gyan.FFmpeg` (needs approval). Not a blocker, because OpenCV covers frame extraction. |
| Awiros dependencies | Missing | Already approved for Phase 0C. Note that the model expects input of 3×48×320. Per-character probabilities are not documented and will need checking in the code. |

## 4. Feasibility impact

- **Phase 0B (plate-detection set) is blocked** until a replacement for D1 is chosen and downloaded. The validator script can still be written and tested on a fixture.
- **Phase 0C (Awiros check):** the installation and latency test can go ahead now using Awiros's own sample crops. The CER and exact-match benchmark is blocked until an OCR test set exists.
- **Phase 0D and later** depend on the team adding clips.

See `dataset_coverage_matrix.md` and `license_report.md`.
