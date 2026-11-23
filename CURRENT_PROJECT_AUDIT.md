# TRACEVISION AI — Current Project Audit

**Date:** 2026-11-23 · **Audited commit:** `3e0a883` (main, in sync with `origin/main`) · **Machine:** Windows 11 laptop, GeForce MX130 (2 GB)
**Method:** every result below was produced by a command run during this audit, unless it is marked NOT TESTED, BLOCKED or "claim only". Nothing in the repository was modified, reset, committed or pushed. Real plate strings are left out of this document on purpose (see §12).

Status labels: **VERIFIED WORKING** · **PARTIALLY WORKING** · **FAILED** · **NOT TESTED** · **BLOCKED**

---

## 1. Executive summary

- **The code is complete and internally consistent. It could not be run end to end on this machine.** The audit laptop has no CUDA-enabled PyTorch, no PaddlePaddle, no UVH-26 weights, an empty PaddleOCR submodule and a 2 GB Maxwell GPU. The pipeline also hard-codes CUDA. Video processing, detection, OCR and new report generation from video are therefore **BLOCKED** here, not failed.
- **What was verified:** the two judged algorithms (26/26 unit tests pass, run without pytest), the evaluation (it reproduces the README numbers exactly from the stored results), the robustness numbers (reproduced exactly from the stored degraded results), the integrity of all 11 stored `result.json` files (no invented characters, no forced matches, 0 rule violations), the registry privacy rules, the HTML/PDF report generator, and the web server with its stored-clip pages.
- **Real bugs found:** (1) if model start-up fails, the app reports only `Model start-up failed: Empty()` after about 5 minutes, hiding the real cause; (2) after that, uploaded jobs stay "queued" forever; (3) the stored-clip video viewer has no plate or vehicle images in a fresh clone; (4) the pipeline cannot run on CPU.
- **Cross-camera re-identification is not implemented in code.** NEEDS.md suggests only the filming is missing. In fact the linking code is missing too.
- **The fresh clone is broken on Windows:** 96 dataset files have paths longer than 260 characters, so checkout aborted and `.git/index` was never written. As a result git shows all 12,253 files as "deleted". **No work is lost:** the working tree matches HEAD except for those 96 files.
- **Privacy:** the GitHub repo is **PUBLIC** (checked) and contains real number plates, including 9 registry rows with the team's own vehicles' plates.

## 2. Repository and Git status

| Item | Finding | Status |
|---|---|---|
| Branch | `main` @ `3e0a883`, tracks `origin/main`, nothing ahead or behind | VERIFIED |
| `git status` | Shows **12,253 files staged as deleted** plus everything untracked | **FAILED (index missing)** |
| Root cause | `.git/index` **does not exist**. The clone ran at 10:25 today and checkout aborted on Windows `Filename too long` | VERIFIED |
| Actual working tree vs HEAD | Compared with a throwaway index in a temp folder (the real index was not touched): **0 modified files, 96 missing**, all in `TRACEVISION_DATA/raw/plate_detection/{train,valid,test}/{images,labels}` (48 image/label pairs with very long Roboflow names) | VERIFIED |
| Uncommitted changes | None, apart from the missing index | VERIFIED |
| Stashes | None | VERIFIED |
| Git LFS | git-lfs 3.7.0. 11 LFS files, all **real binaries, not pointer files** (Awiros `model.safetensors` 149 MB with a valid safetensors header, plate detector 6.5 MB, `clip01–09.mp4`) | VERIFIED |
| Submodule `third_party/PaddleOCR` | **Empty directory (0 files)**. It is needed at runtime by the OCR worker (`ppocr` imports) | **BLOCKED** |
| `core.longpaths` | Not set | cause of the aborted checkout |
| Files absent by design (git-ignored) | UVH-26 weights, COCO `yolov8n.pt`, clip10/clip11 (Pexels, not re-hosted), `runs/**/vehicles/` crops, `processed/degraded_clips/` | VERIFIED |

**Actual structure** (the paths `evaluation/` and `reports/` from the audit brief are under `TRACEVISION_DATA/`):
```
README.md NEEDS.md PROBLEMS.md DECISIONS.md PIPELINE.md TEAM_TASKS.md completions.md whatnext.md TRACEVISION_Team_Handoff.pdf
tracevision/   api.py pipeline.py fuse.py match.py ocr_worker.py plates.py colour.py report.py evaluate.py robustness.py calibrate.py config.yaml static/viewer.html   (1,950 lines)
tests/         test_fuse.py (13) test_match.py (13)
runs/clip01–11/            result.json report.html report.pdf   (no vehicles/ crops: git-ignored)
runs_degraded/<clip>__<variant>/result.json   (35 = 5 clips × 7 variants)
TRACEVISION_DATA/evaluation/   test_clip_labels.csv (51 vehicles), clips.csv, cross_camera_ground_truth.csv (header only), reports/clipNN_report.pdf (11), label_review/ (11)
TRACEVISION_DATA/registry/synthetic_vehicle_registry.csv   (313 rows)
TRACEVISION_DATA/models/       awiros/ (LFS), weights/plate_yolov8n_quobotic.pt (LFS), class_mapping.json
TRACEVISION_DATA/raw/          test_videos/clip01–09.mp4, plate_detection/ (5,152 files, 96 not checked out), ocr_corpus/
TRACEVISION_DATA/processed/    plate_detection/, ocr_evaluation/, test_video_frames/
TRACEVISION_DATA/reports/      phase reports p1–p6, health check, licences, dataset audits
TRACEVISION_DATA/scripts/      10 data scripts + 4 smoke scripts
```
There is **no root `requirements.txt`** and no `pyproject.toml`. The only dependency list is the `pip install` line in the README.

## 3. Environment and hardware status

| Item | Finding |
|---|---|
| GPU | **NVIDIA GeForce MX130, 2 GB VRAM, Maxwell** (compute capability 5.0), driver 573.71, CUDA 12.8 driver API. **This is not the RTX 3050 the docs were measured on.** |
| `python` on PATH | **Not found.** Only the `py` launcher works |
| Python 3.14.3 (default `py`) | Almost nothing installed (numpy, pandas, PIL only) |
| Python 3.13.5 | cv2, jinja2, pandas, numpy, PIL only |
| **Python 3.10.0** (used for this audit) | torch **2.11.0+cpu** (`cuda.is_available() = False`), torchvision 0.26+cpu, ultralytics 8.4.30, opencv 4.13, fastapi 0.135, uvicorn 0.42, python-multipart, jinja2, reportlab 4.4.4, pyyaml, pandas, pyarrow, tqdm, httpx |
| Missing on every interpreter | **pytest, paddlepaddle(-gpu), lap, rapidfuzz, safetensors, open_clip_torch, lmdb, shapely, pyclipper, scikit-image** |
| Environment variables | No project-specific variables are read by the code (`grep environ/getenv` finds none in `tracevision/`). Two unrelated tool tokens exist in the shell environment. Their values were not read. |

**Hardware viability (unverified, needs a test):** current PyTorch CUDA wheels and PaddlePaddle-GPU 3.x may not support compute capability 5.0, and 2 GB VRAM is tight for UVH-26, YOLOv8n, CLIP and Paddle together. **Treat this laptop as CPU-only.** The pipeline cannot run on CPU without a code change (see §11, B4).

## 4. Missing dependencies and model weights

| Resource | Needed by | Present? | Status |
|---|---|---|---|
| UVH-26 `UVH-26-MV-YOLOv11-S.pt` | vehicle detection and type | **No** (git-ignored, manual download) | BLOCKED |
| Plate detector `plate_yolov8n_quobotic.pt` | plate detection | Yes, real LFS file (6.5 MB) | present, not executed |
| COCO `yolov8n.pt` | phantom-box cross-check (C11) | **No.** The code comment says "ships with the repo", which is **false** (it is git-ignored) | BLOCKED (ultralytics *may* auto-download it; not verified) |
| Awiros `model.safetensors` + `en_dict.txt` + `test.py` | OCR | Yes, real LFS file (149 MB) | present, not executed |
| PaddleOCR source (`third_party/PaddleOCR`) | OCR model build | **Empty submodule** | BLOCKED |
| CLIP ViT-B/32 (open_clip "openai") | colour | **No** (about 580 MB, downloads on first run) | BLOCKED. The code silently falls back to the old hue heuristic |
| ByteTrack (`lap`) | tracking | `lap` not installed. The tracker config is built into ultralytics | BLOCKED |

**Commands for the owner to run (not run by me):**
```powershell
git config --global core.longpaths true
cd C:\Users\PC-01\trace_vision_nebula
git reset                                # MIXED reset: rebuilds the missing index from HEAD and does NOT touch files
git -c core.longpaths=true checkout -- TRACEVISION_DATA/raw/plate_detection   # restores the 96 long-path files
git submodule update --init --recursive  # fills third_party/PaddleOCR (about 100 MB+)

# Python 3.10 (already has most of the app stack):
py -3.10 -m pip install pytest rapidfuzz safetensors lap shapely pyclipper scikit-image lmdb open_clip_torch
# OCR on CPU (this GPU is very likely unsupported):
py -3.10 -m pip install paddlepaddle==3.3.1
# UVH-26: download weights/YOLOv11-S/UVH-26-MV-YOLOv11-S.pt from huggingface.co/iisc-aim/UVH-26 into TRACEVISION_DATA/models/weights/
# COCO yolov8n.pt: put it in TRACEVISION_DATA/models/weights/yolov8n.pt
```
Even after these steps, the pipeline still needs a CUDA GPU (B4), so the full run should be done **on the team's RTX 3050 machine**.

## 5. Test results

| Test | Command | Result | Status |
|---|---|---|---|
| Unit tests (as requested) | `python -m pytest tests -v` | `python: command not found`. With `py -3.10/-3.13/-3.14 -m pytest`: **`No module named pytest`** on all three | **FAILED (environment)** |
| Unit tests (substitute) | Plain-Python runner that imports `tests/test_*.py` and calls each `test_*` function. The tests use only bare `assert`, with no fixtures or parametrize. | **26 collected, 26 passed, 0 failed, 0 skipped** (fuse 13/13, match 13/13) | **VERIFIED WORKING** |
| Label validator | `validate_test_labels.py` (outputs redirected to a temp folder) | 51 vehicles, 11 clips, **1 error, 0 warnings**. The error: *no cross-camera group spanning 2 clips*. Derived files were not written, by design. | PARTIALLY WORKING (expected error) |
| Plate dataset validator | `validate_plate_dataset.py --sample 50` | train/valid/test: 0 missing labels, 0 malformed, 0 out of range, 1 empty label (valid). 0 source images leaked across splits. 8 source *videos* appear in more than one split (already documented). 1/50 near-duplicates test↔train. | VERIFIED WORKING (sample only. The 96 un-checked-out files were not in the sample.) |
| Evaluation | `py -3.10 -m tracevision.evaluate --tag audit` (tag changed only so that the committed `p6_evaluation_baseline.json` is not overwritten) | Ran in 1.5 s. **Output identical to the committed baseline JSON** (only the tag field differs) | **VERIFIED WORKING** |
| Robustness | `python -m tracevision.robustness` | Needs the full Engine and the degraded clips (absent) | **BLOCKED** |
| Robustness (re-score only) | Ran the same `evaluate` + `summarise` calls as `robustness.py` on the stored `runs_degraded/` results | **All 7 variants identical to the committed `p6_robustness.json`** | VERIFIED (stored results only) |

**The evaluation did use the expected labelled data:** `TRACEVISION_DATA/evaluation/test_clip_labels.csv`, 51 rows, all with `target_vehicle_id`, 11 clips. **Caveat:** `evaluate` scores the **stored** `runs/*/result.json` files (produced 2026-11-23 09:43–09:45 on the team machine). It does not re-run the models. The headline numbers are reproducible from stored outputs. They were **not** re-derived from video in this audit.

## 6. Application startup result

`py -3.10 -m tracevision.api` → **the server starts** (`Uvicorn running on http://127.0.0.1:8000`). `GET /` returns 200.

| Check | Result | Status |
|---|---|---|
| Server starts, home page loads | 200, upload form and 11 stored clips listed | **VERIFIED WORKING** (HTTP only, not in a browser) |
| Model start-up | Background thread prints `missing dependency: No module named 'rapidfuzz'`. The page keeps showing **"Loading models… (about 20 s)" for about 5 min**, then **"Model start-up failed: Empty()"** | **FAILED** (environment) and a **bug** in how the error is reported (B1) |
| Upload validation | `.md` file → 400 with the list of allowed types | VERIFIED WORKING |
| Upload of clip02.mp4 | 200, `job_id` returned, file stored in `runs/jobs/<id>/` | VERIFIED WORKING |
| Job processing | Status stays `{"status":"queued","position":1}` **indefinitely**, even after start-up has failed | **FAILED** (bug B2) |
| Path-traversal guards | `..%2F` variants on `/runs`, `/data/.../vehicles`, `/viewer` → all 404 | VERIFIED WORKING |

## 7. End-to-end workflow verification

| # | Step | Status | Evidence |
|---|---|---|---|
| 1 | Upload an existing test video | **VERIFIED WORKING** | §6 |
| 2 | Process the video | **BLOCKED** | missing deps and weights, and CUDA hard-coded (B4) |
| 3 | Detect and track vehicles | **BLOCKED** (stored outputs exist) | stored runs: 396 raw tracks → 201 kept → 174 vehicles over 11 clips |
| 4 | Detect number plates | **BLOCKED** (stored outputs exist) | 238 plate detections in stored runs |
| 5 | Read plates across frames | **BLOCKED** (fusion logic VERIFIED by tests) | 24 plates read in stored runs |
| 6 | Keep unreadable characters as `?` | **VERIFIED** (unit tests and stored outputs) | 0 rule violations in 11 results (§9). 13 partial plates kept their `?` |
| 7 | Vehicle type and colour | **BLOCKED** (stored outputs exist) | colour here would silently use the heuristic, not CLIP |
| 8 | Search the fictional registry | **VERIFIED** (unit tests), stored outputs consistent | |
| 9 | Ranked top-5 candidates | **VERIFIED** in stored outputs | never more than 5. Every candidate has reasons |
| 10 | "No confident match" when unsupported | **VERIFIED** in stored outputs | 166 of 174 vehicles got no confident match. 0/42 false matches on unregistered vehicles |
| 11 | Annotated video viewer | **PARTIALLY WORKING** (HTTP only) | the viewer page, result JSON and video (clip01–09) are served. **`/files` is `[]` for every stored clip** (no crops in a fresh clone, B3). **clip10/11 video → 404** (not in the repo). Not checked in a browser |
| 12 | PDF and HTML reports | **PARTIALLY WORKING** | stored reports are valid and served. Rebuilding from `result.json` works but **drops all images** when `vehicles/` is absent (B3) |

**Limitation:** no browser was available to this audit, so the viewer's JavaScript and live-playback mode were **NOT TESTED**.

## 8. Evaluation results (reproduced from stored results, 51 labelled vehicles)

| Metric | All | Moving / dashcam (37) | CCTV-style (14) | Matches README? |
|---|---|---|---|---|
| Detected and tracked | 44/51 (86%) | 30/37 | 14/14 | ✅ |
| Registered vehicles matched correctly | 8/9 (89%) | 8/9 | n/a | ✅ |
| Unregistered with a false confident match | **0/42** | 0/28 | 0/14 | ✅ |
| Plate characters correct / `?` / **wrong** | 112 / 20 / **0** of 132 | same | n/a (plates < 16 px) | ✅ |
| Exact plate (fully readable) | 7/10 | 7/10 | n/a | ✅ |
| Type exact / compatible | 68% / 93% | 60% / 93% | 86% / 93% | ✅ |
| Colour exact / near | 64% / 75% | 67% / 77% | 57% / 71% | ✅ |
| Human-unreadable plates where the system read characters | 2/28 (7%) | 2/14 | 0/14 | not in README (NEEDS item 7) |

**Robustness (stored degraded results):** 0 false identifications in all 7 variants ✅. Registered matched: 1/8 under blur, 480p, 360p, JPEG and night, and 5/8 under noise. Wrong characters up to 17% at 360p ✅ (matches the README).

**Caveats the numbers rest on:**
- The 9 registered vehicles are `evaluation_seed` rows created from the same labels. All 8 stored matches hit those seed rows, and none hit fictional rows.
- Thresholds and several pipeline rules were tuned on these clips (the README says so).
- 9 positive cases is a small sample.

**Discrepancy:** the README says processing takes "4–19 s per clip". The stored timings are **3.8–34.4 s** (clip10 34.4 s, clip11 17.1 s). Total for 11 clips: 119.5 s (team GPU, not measured here).

## 9. Report-generation verification

Checked by a script over all 11 `runs/*/result.json` files against `config.yaml`:

| Check | Result |
|---|---|
| Stored results correspond to the input clips | frame count, width and height match the real `clip01–09.mp4` exactly. clip10/11 can't be checked (videos absent) |
| No character emitted below vote share 0.6 or confidence 0.8 | **0 violations** |
| No emitted character missing from every per-frame read | **0 violations** |
| Fused plate = joined positions | 0 mismatches |
| `match` only when ≥ 5 known characters, top score ≥ 67.5 and margin ≥ 4 | **0 violations** (8 matches) |
| ≤ 5 candidates, each with reasons, no "probability" field | 0 violations |
| Confidences kept separate | `type.detector_conf_mean` (detector), `char_probs` / `positions[].confidence` (OCR), `match_score` (registry) are separate fields. The report says "match score is a heuristic ranking score, not a probability" |
| HTML reports | self-contained (images embedded as data URIs). They contain camera/video info, per-frame per-character OCR confidence, fused plate with confidence and vote share, type with vote share, colour with confidence, ranked candidates with match scores and reasons, and the decision with its reason |
| PDF reports | 11 valid PDFs (`%PDF-` header and `%%EOF`, about 1–6 pages). Byte-identical to the delivered `TRACEVISION_DATA/evaluation/reports/clipNN_report.pdf`. **Pages not rendered visually** (no PDF renderer on this machine) |
| Report generator on this machine | `report.build()` works on Python 3.10 (HTML + PDF), but with **0 images** when crops are absent (18 in the committed clip04 report) |
| Partial-plate matching | the clip04 partial plate (4 of 10 positions `?`) → seed record, score 81.1 vs 65.5 for the runner-up, as documented |

**Verdict: in every stored output, the system does not invent plate characters and does not force a registry match.**

## 10. Cross-camera readiness

| Question | Answer |
|---|---|
| Implemented? | **No.** There is no cross-camera code in `tracevision/` (`grep` for cross-camera / re-id / re-identification finds nothing). The design exists only as PIPELINE.md step 11 ("link tracks whose fused plates agree … and colour and type agree"), marked "new" |
| Tested? | **No** |
| Annotation columns | **Yes:** `camera_id` and `cross_camera_group_id` are in the labels and the template. `cross_camera_ground_truth.csv` has only a header |
| Labelled pairs | **None.** 0 rows have a `cross_camera_group_id`. The label validator reports this as its only error |
| Can a vehicle be linked across two clips today? | **No.** There is no paired footage and no linking code. The within-clip plate re-link (`plate_link_min_known`) is a reusable building block |
| Missing steps | (1) film the pair and label it; (2) write the linker (for example `tracevision/crosscam.py`: compare fused plates from 2 `result.json` files with the wildcard-aware `match` plate similarity, then require colour and type agreement); (3) add a cross-camera metric to `evaluate`; (4) show linked vehicles in the report and viewer |
| Status | **NOT IMPLEMENTED / BLOCKED** (the docs understate the remaining work) |

## 11. Bugs and blockers

| ID | Severity | Finding | Where |
|---|---|---|---|
| **B0** | Blocker (this machine) | Clone checkout aborted (paths over 260 characters) → no `.git/index`, 96 dataset files missing, git shows 12,253 deletions. The README's `core.longpaths` step had not been done before cloning | git |
| **B1** | High | `_serve` imports `awiros_feasibility_check` **outside** its `try`. That script calls `sys.exit()` on a missing import, so the child process dies silently. The parent waits the full 300 s timeout and the UI shows `Model start-up failed: Empty()`, hiding the real cause (`rapidfuzz` missing) | `tracevision/ocr_worker.py:21` |
| **B2** | High | When `Engine()` fails, `_worker` returns. Jobs uploaded afterwards are queued forever with no error. Uploads should be refused or marked as errors | `tracevision/api.py:39-45` |
| **B3** | Medium | The stored-clip viewer and rebuilt reports have no plate or vehicle images in a fresh clone, because `runs/**/vehicles/` is git-ignored. The demo flow in NEEDS.md ("open its stored viewer") will show no crops unless clips are re-run first | `.gitignore:51`, `api.py` `/files` |
| **B4** | Medium | CUDA is hard-coded (`device=0` in 3 YOLO calls, `OCRWorker(device="gpu")`), so there is no CPU fallback | `pipeline.py:67,112,194,419` |
| B5 | Low | If `open_clip` or the CLIP weights are missing, colour silently falls back to the older heuristic (27%/57%), which would quietly change results | `colour.py:114` |
| B6 | Low | The code comment says COCO `yolov8n.pt` "ships with the repo". It doesn't (git-ignored). The README setup also doesn't mention it | `pipeline.py:423` |
| B7 | Low | No `requirements.txt`. `pytest` is not in the README install line | repo root |
| B8 | Low | The UI says "Loading models… (about 20 s)". NEEDS.md says 3–4 min | `api.py:79` |
| B9 | Low | `@app.on_event("startup")` is deprecated in the installed FastAPI (warning only) | `api.py:59` |
| B10 | Info | clip10/11 videos are not in the repo, so their viewer video returns 404 on any fresh clone (licensing decision, documented) | — |

## 12. Security and privacy concerns

- **The GitHub repo is PUBLIC** (checked with `gh repo view`: `"visibility":"PUBLIC"`). It contains real number plates: the team's clips, the Quobotic and zenitsu09 photos, and **9 `evaluation_seed` registry rows holding the team's own vehicles' real plates**, including one taken from a Pexels clip. The owner still has to decide on visibility (NEEDS item 2).
- **Registry:** 313 rows (304 `fictional` + 9 `evaluation_seed`). Columns: id, registration number, state, type, colour, make, model, year, source, synthetic. **No owner, name, phone, address or email columns**, and 0 phone-like or email-like values. ✅
- The app binds to `127.0.0.1` only. Upload type and size are checked. Path parameters are pattern-checked, and traversal probes returned 404. ✅ There is no authentication (acceptable for a local demo only).
- zenitsu09 OCR data has no stated licence (internal evaluation only, documented).
- No secrets were found in the project code. The code reads no environment variables.

## 13. Next steps (by priority)

1. **Fix the clone** on this machine (commands in §4). Use the team's RTX 3050 machine for any demo or full run, because this laptop can't run the pipeline.
2. **Re-run the full pipeline on the GPU machine** (`python -m tracevision.pipeline --report`), then `python -m tracevision.evaluate` and `python -m pytest tests -v`, to re-confirm the stored results from video. This also regenerates the `vehicles/` crops the viewer needs (B3).
3. **Fix B1 and B2** (small, low-risk): move the import inside the `try` in `ocr_worker._serve` (or catch `SystemExit`), and make the API refuse or mark as errors any jobs created when the engine failed to start.
4. **Cross-camera:** film and label the pair (NEEDS item 1) **and** write the linker plus its metric (§10). This is the largest remaining gap for the bonus.
5. **Decide repo visibility** before submission (privacy).
6. Add `requirements.txt` (including pytest). Optionally add a CPU fallback (B4) and a warning when the CLIP colour model isn't used (B5).
7. Correct the docs: the processing-time range (3.8–34.4 s), "yolov8n ships with the repo", and the NEEDS.md wording that cross-camera only needs filming.
8. Demo rehearsal in a real browser (viewer and live playback were not tested here).

---

### Files this audit left in the repository
- `CURRENT_PROJECT_AUDIT.md` (this file)
- `TRACEVISION_DATA/reports/p6_evaluation_audit.json` (evaluation output, identical to the baseline apart from the tag; safe to delete)
- `runs/jobs/fbbd327c3360/` (test upload of clip02, git-ignored; safe to delete)
- `__pycache__/` folders (git-ignored)

All other audit outputs (validator reports, re-built report, check scripts) are in the session's temp folder, not in the repo.
