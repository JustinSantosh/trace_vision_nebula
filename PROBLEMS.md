# TRACEVISION AI — Phase 0 Problem Log

**Last updated:** 2026-11-22 (Quobotic re-verified, Awiros reproduces card samples, completions/whatnext added)
**Severity:** 🔴 Blocker (stops a phase) · 🟠 High (risks the demo or the results) · 🟡 Medium (workaround exists) · ⚪ Low / note

Evidence for every item is in `TRACEVISION_DATA/reports/`. Done work is summarised in [completions.md](completions.md) and the plan is in [whatnext.md](whatnext.md).

## Progress so far

| Step | State |
|---|---|
| 0A Audit, coverage matrix, licence report | ✅ Done |
| Replace the empty D1/D2 repos | ✅ D1 → Roboflow **Quobotic v3** (b8iqo rejected as synthetic). D2 → **zenitsu09** now, witvix pending. |
| Quobotic v3 downloaded and extracted | ✅ All 5,151 files match the zip CRC (0 missing, 0 corrupt, 0 extra). Real scenes. Re-checked on 2026-11-22 after a failed Explorer copy: 0 missing, 0 size mismatches. |
| zenitsu09 OCR evaluation set | ✅ 1,709 crops → 965 unique plates, `ground_truth.csv` built (local only) |
| 0B Plate-detection validation + Colab `data.yaml` | ⏳ Next (`validate_plate_dataset.py`, `prepare_plate_detection.py`) |
| 0C Awiros feasibility check | 🟡 Part done: PaddlePaddle runs on Windows CPU and **9/9 card samples are reproduced** (`models/awiros/samples_ours.json`). Still open: per-character probabilities (B1), the 965-plate benchmark, latency. |
| witvix (harder OCR test) | ⏳ Waiting for the team (access form) |
| 0D Test clips | ⏳ Waiting for the team (no clips yet) |

| Phase 1–4 (models, own matching algorithm, app, report, evaluation) | ⏳ Planned, see [whatnext.md](whatnext.md) |

**Open blockers right now:** A5 (no test clips; this is now the critical path, because the demo and the per-clip analysis reports both need clips) and A6 (no cross-camera pair, which only affects the bonus). Everything else has a workaround in hand.

---

## A. Datasets

| # | Severity | Problem | Impact | Proposed fix | Owner / status |
|---|---|---|---|---|---|
| A1 | 🔴 | **The D1 plate-detection repo (`thundarstrom/indian-license-plate-detection`) contains no data.** The HF API tree lists only `.gitattributes`, `README.md` and `data.yaml`, about 2.4 kB in total. The card claims 3,742 images, but there are no images or labels. | Phase 0B and the YOLOv8n plate-detector fine-tune in Phase 1 are blocked. | ~~b8iqo~~ was rejected after download (see A14). **Now: Roboflow Quobotic v3** (real photos, CC BY 4.0, 2069/336/169), with witvix as the out-of-domain test. See `reports/d1_d2_alternatives.md`. | ✅ Downloaded and verified 2026-11-22: 2069/336/169, CRC OK, real scenes (median plate 2.8% of the image). |
| A2 | 🔴 | **The D2 OCR-corpus repo (`thundarstrom/indian-anpr-ocr-corpus`) contains no data.** It lists only `.gitattributes` and `README.md`, about 2.3 kB. There is no `parseq_dataset/`, `gt.txt` or LMDB. | We cannot measure Awiros CER or exact-plate accuracy on a proper test split. | **Proposed:** witvix truck plates (589 texts, CC-BY-NC-4.0, gated by a form) plus the Payals Roboflow test split (CC BY 4.0). Backup: zenitsu09 crops (no licence stated, internal use only). See `reports/d1_d2_alternatives.md`. | Alternative found. The team must fill in the witvix form. |
| A3 | 🟠 | The maintainer's other 8 dataset repos, including `indian-anpr-ocr-benchmark`, `augmented-indian-plate-detection` and `traffic-pipeline-sample-videos`, are also card-only. | There is no fallback from the same source. | Look elsewhere. | Confirmed |
| A4 | 🟡 | The D1 `data.yaml` points to the uploader's local path `c:/projects/traffic-analytics-system/...` and uses the split folder name `valid/`. | It would break on Colab if used unchanged. | `prepare_plate_detection.py` must rewrite the paths. Applies only if the data ever appears. | Note |
| A5 | 🔴 | **There are no test clips in the working folder** (V1, V2 and V3 are all absent). | Phases 0D, 0E and 0F are blocked, along with every clip-based evaluation: detection, type, colour, multi-frame recovery, cross-camera and no-match. The deliverables also require **an analysis report per test clip**. | **Fastest:** film 5–10 short phone clips from a high, distant, CCTV-like angle, including blurred or partly hidden plates and **at least 2 vehicles that will not be in the registry** (for no-match). Alternatively, download 5–8 Indian traffic clips from Pexels or Pixabay. Record the source and licence for each in `raw/test_videos/clips.csv`. | Open: team action, top priority |
| A6 | 🟠 | **No clip with the same vehicle in two clips has been found.** Scenario 10 is required. | Cross-camera re-identification cannot be evaluated. Stock footage rarely shows one vehicle from two angles. | The team films the same vehicle from two phone positions, or cuts two non-overlapping segments from one long clip (weaker, and must be disclosed). | Open |
| A7 | 🟡 | The V1 Kaggle page (`nimishshandilya/car-number-plate-video`) could not be read automatically because it is rendered with JavaScript. Its licence, contents and country mix are unverified. | It could be unusable or contain non-Indian plates. | Check the licence on Kaggle when downloading and tag the country of each clip. | Open |
| A8 | 🟠 | DenseWorld-115k (V2) ships only a manifest. The clips must be rebuilt from YouTube with `yt-dlp` at 480p. The videos stay the creators' copyright and are for research use only. | Plates are often unreadable at 480p. Videos can disappear from YouTube. The clips cannot be redistributed or used in a public demo. | Use only a few clips for evaluation, and none in the public repo or demo video. Prefer V3. | Note |
| A9 | 🟡 | UFPR-ALPR (O1) is gated behind an email request from a university account, with 1–5 business days' turnaround, under an academic, non-commercial licence. Its plates are Brazilian. | It is unlikely to arrive in time for the hackathon. | Skip it unless someone requests access now. It must never be used as Indian OCR ground truth. | Optional |
| A10 | ⚪ | The IEEE DataPort dashcam set (O2) needs a login, is 4.43 GB, has no annotations, and uses a dashcam rather than a CCTV angle. | It adds little value for its cost. | Skip. | Not recommended |
| A12 | 🟡 | Several replacement sources overlap or have licence problems. Payals and zenitsu09 `plates3` share plates. The DataCluster set is listed as CC0 on Kaggle but CC-BY-NC-ND on HF. zenitsu09 states no licence. The Kaggle `sunrajbishnolia` set has augmented copies leaking into test. | There is a risk of inflated scores or licence breaches. | Dedupe across sources by plate text and image hash before evaluation. Use unlicensed sets internally only. Reject the leaking set. | Open |
| A13 | 🟡 | No replacement source is CCTV footage: witvix is phone photos, and Roboflow and Kaggle are mostly close-up stills. | Detection and OCR scores will overstate CCTV performance. | Report the scores on our own test clips separately, as the headline number. | Note |
| A14 | 🔴 | **The Roboflow b8iqo set (my first D1 pick) is synthetic.** Its images are rendered plates filling the whole frame: 2,439 of 2,442 boxes cover more than 80% of the image. | It cannot train a scene plate detector. Time was lost on the download. | Moved to `raw/_rejected/b8iqo_synthetic/` (not deleted). Replaced by Quobotic v3 after checking its sample images. **Rule from now on: view sample images before recommending any dataset.** | Resolved: replaced |
| A15 | 🟡 | Quobotic v3 contains consecutive video frames (`video*_NNNN.jpg`) that may sit across splits. Images are also stretched to 640×640, which distorts the plate's aspect ratio. Its train split is flip-augmented, so it contains mirrored plates. | Test mAP may be inflated by near-duplicates. The stretch differs from CCTV frames. | `validate_plate_dataset.py` reports near-duplicates across splits (it does not fix them). Use the ultralytics default letterboxing at inference. | Open |
| A16 | 🟡 | zenitsu09 crops come from the same images as Quobotic. | They are not independent of the detector data. | Never use zenitsu09 for end-to-end detector+OCR evaluation. Use it only for the standalone Awiros OCR benchmark. | Note |
| A17 | 🟡 | Reading the zenitsu09 parquet file needs `pyarrow`, which is not installed. | The OCR ground truth cannot be built yet. | Installed pyarrow 26.0.1 (approved). | Resolved |
| A18 | 🟠 | **Quobotic filenames are up to ~233 characters**, so full paths reach 280 characters. Windows has `LongPathsEnabled = 0`, so File Explorer extraction fails ("Path too long") and normal Python `open()` cannot read 10 train files (5 photos × 2 augmented copies). | Explorer could not extract the zip. The audit reported those 10 files as missing or corrupt, which is false: they read fine through the `\\?\` long-path prefix. Ultralytics on Windows would silently miss them. **Do not use File Explorer for this zip; click Cancel on its "Path too long" dialog** (Skip would drop the file). Extracted with Python using the long-path prefix, then **re-extracted and checked file by file against the zip: 5,151/5,151 CRC match, 0 missing, 0 extra.** `prepare_plate_detection.py` will build a processed copy with **short hashed filenames plus a name map** (originals untouched). The alternative is for the user to enable long paths in Windows (a system setting I won't change). Not an issue on Colab/Linux. | Extraction resolved. Short-name copy: open, fix in 0B |
| A19 | 🟡 | Quobotic labels mix boxes (2,319 lines) with **polygon** lines (275 lines with 11–29 fields). | Ultralytics detect converts polygons to boxes, but the mix should be reported. | `validate_plate_dataset.py` reports the counts and converts to boxes only in the processed copy. | Open |
| A20 | 🟡 | zenitsu09 OCR labels: **112 of 1,709 (82 of 965 unique plates) fail both plate regexes**. Examples: `TERRANO` (a car-model badge, not a plate), `MH4705851` (likely a missing letter), `KL01KLKL01`, `MHD1CV9311` (D vs 0). 364 of the 965 primary crops are under 20 px tall. | Ground-truth errors would count against Awiros unfairly. Tiny crops lower the scores. | Flagged as `nonstandard_review` (not rejected). Report CER both with and without flagged rows, and by crop height. Optional manual review of the 82. | Open |
| A11 | ⚪ | Two `.mp4` files sit in `~/Downloads` (`DS.mp4` and `original-5adf…mp4`). They are outside the working folder and were not inspected. | They may be intended test clips. | If so, move them into `raw/test_videos/` and record their source and licence. | Team to confirm |

## B. Models

| # | Severity | Problem | Impact | Proposed fix | Status |
|---|---|---|---|---|---|
| B1 | 🟠 | **The Awiros card does not document per-character probabilities.** | Multi-frame plate recovery was designed around per-character confidence. | Check the CTC head output in `test.py` and PaddleOCR during Phase 0C. Fallback: use per-position agreement across frames as the confidence signal. | To verify in 0C. Awiros now runs locally, so this can be checked directly. |
| B2 | 🟡 | Awiros needs PaddlePaddle plus a clone of the PaddleOCR repo with `test.py` and `en_dict.txt` copied in. Its input is 3×48×320. | There is a risk of installation trouble on Windows with Python 3.12. CPU latency is unknown. | Run the approved feasibility check. If the Windows install fails, run it on Colab. | ✅ Install resolved: PaddlePaddle runs on Windows CPU and the PaddleOCR clone is in `third_party/` (git-ignored). 9/9 card samples reproduced. CPU latency still to be measured. |
| B3 | 🟡 | The UVH-26 card says "14 classes" but lists 13: Hatchback, Sedan, SUV, MUV, Bus, Truck, Three-wheeler, Two-wheeler, LCV, Mini-bus, Tempo-traveller, Bicycle, Van. | `class_mapping.json` must be built from the actual model class names. | Read the names from the loaded `.pt` file and do not trust the card. | Open |
| B4 | 🟡 | UVH-26 uses a single Two-wheeler class and cannot separate motorcycle from scooter. It also has no auto-rickshaw class name (Three-wheeler is the nearest). | Our type vocabulary splits these classes. | Map Two-wheeler to `motorcycle/scooter` (ambiguous) and Three-wheeler to `auto_rickshaw`, recording that this is a judgement call. Do not invent the split. | Open |
| B5 | 🟡 | The UVH-26 card states no input resolution or CPU speed for any variant. | We cannot yet say whether YOLOv11-S runs acceptably on CPU. | Benchmark on the first clip. There is a local RTX 3050 with 6 GB as a fallback. | Open |
| B6 | 🟠 | **Licences:** YOLOv8 and the Ultralytics-based UVH-26 YOLOv11 variants are **AGPL-3.0**, even though the UVH-26 card says Apache-2.0. | AGPL obligations apply if the app is distributed or offered as a network service. | This is acceptable for a hackathon demo. State it in the README. The non-Ultralytics UVH-26 variants (RT-DETRv2, DAMO-YOLO) avoid it. | Note |

## C. Tooling and environment

| # | Severity | Problem | Impact | Proposed fix | Status |
|---|---|---|---|---|---|
| C1 | 🟡 | **FFprobe and FFmpeg are not installed.** | Codec and duration come from OpenCV headers, which are less reliable. FFmpeg-based degradation is unavailable. | `winget install Gyan.FFmpeg` (needs approval). OpenCV covers frame extraction for now. | Open |
| C2 | 🟡 | `ultralytics`, `torch`, `imagehash` and the app stack (`fastapi`, `uvicorn`, `jinja2`, an HTML→PDF tool) are not installed. (`pyarrow` 26.0.1 and `paddlepaddle` are installed. Awiros uses the PaddleOCR repo clone, not the `paddleocr` pip package.) | Model download, inference and the near-duplicate check cannot run yet. | Install when each phase starts (each install needs approval, except the Awiros dependencies, which are already approved). | Open |
| C3 | ⚪ | Running the audit with `python -I` drops the user site-packages (Pillow, OpenCV, PyYAML). In the first version this made every image look corrupt. | Images were wrongly reported as corrupt. | **Fixed:** the script now stops with an error when a dependency is missing. Run it without `-I`, or install the packages system-wide. | Fixed |
| C4 | ⚪ | The OpenCV video fallback cannot report codec names reliably (it gives a FourCC such as `FMP4`). | The codec column in the audit is approximate. | Install FFprobe. | Linked to C1 |

## D. Coverage gaps (from the coverage matrix)

| Requirement | Status | Blocking item |
|---|---|---|
| Vehicle detection | Partial | A5 |
| Vehicle type | Partial | A5, B3, B4 |
| Indian plate detection | Partial: Quobotic v3 in hand, validation pending (0B) | A15, A18, A19 |
| Indian OCR benchmark | Partial: zenitsu09 ground truth built (965 plates); Awiros not yet run | B1, B2, A20 |
| Multi-frame recovery | Missing | A5, B1 |
| Vehicle colour | Missing | A5 |
| Registry ranking | Missing | A5, then Phase 0F |
| No-match handling | Missing | A5 (needs at least 2 vehicles not in the registry) |
| Cross-camera tracking | Missing | A5, A6 |
| Make/model (bonus) | Missing | No verified labels; make no claims |

## E. Process risks

| # | Severity | Risk | Mitigation |
|---|---|---|---|
| E1 | 🟠 | The 4-hour Phase 0 budget was hit by the empty D1/D2 repos and the rejected b8iqo download. | D1/D2 are now replaced. Do not hunt for more data; move to 0B/0C. |
| E2 | 🟠 | Hand-labelling time for the clips is not yet allocated. | Limit it to 5–8 clips at first, with bounding boxes on the first frame only. |
| E3 | 🟡 | Real plates appear in the test clips, which is a privacy concern. | Keep raw clips and crops out of this repo (see `.gitignore`). The registry stays synthetic, with evaluation-seed entries clearly marked. |
| E4 | 🟠 | The judged deliverable "matching and ranking algorithm developed by the team" is not started, and neither are the UI and report. Data prep could eat the remaining time. | Cap 0B/0C. Start the registry and scorer (Phase 2) in parallel with model work, since they don't need clips. See [whatnext.md](whatnext.md). |
| E5 | 🟡 | The PaddleOCR clone (`third_party/`) and the Awiros sample images were untracked and could be committed by accident. | Added to `.gitignore` on 2026-11-22. |
