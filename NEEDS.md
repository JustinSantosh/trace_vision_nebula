# NEEDS: what only the owner / team can do

**Updated:** 2026-11-23 (overnight run). Everything that could be built without you is built, tested and on GitHub. This is the full list of what's left **for you**, in priority order. Each item says what to do, why it matters, and what happens after it.

## 🔴 Must do before submission

### 1. Film the cross-camera car pair (about 15 min)
- **What:** film **one car you own** passing by, from **2 clearly different spots** (e.g. a footbridge and the roadside), as **2 clips of 8–15 s**, landscape, 1080p, held steady. Include some other traffic. **Send the original files** (USB / Google Drive / WhatsApp *"send as document"*), not normal WhatsApp video.
- **Then:** put them in `TRACEVISION_DATA/raw/test_videos/` and tell Claude. It will check, rename (clip12, clip13), extract frames and make contact sheets. **Label them** with the same `cross_camera_group_id` (e.g. `X1`), `in_registry = yes`, and the car's real plate in `registry_plate_full`.
- **Why:** the spec requires at least one cross-camera pair (scenario 10, bonus feature). It's the **only error left** in the label validator (PROBLEMS A6).
- **After it, Claude runs:** label validation → registry re-seed → pipeline + reports for the new clips → evaluation → final Phase 0 report.

### 2. Decide the repo's visibility (1 min)
- The GitHub repo is **public** and contains real number plates (your clips, the Quobotic and zenitsu09 photos) and the team's own vehicles' plates in the registry (`evaluation_seed` rows).
- **Options:** make it **private** (Settings → Danger Zone → Change visibility), or keep it public on purpose. If private, add the judges as collaborators when submitting.
- **Why:** privacy (PROBLEMS E6, DECISIONS D10). Claude won't change account settings for you.

### 3. Check the demo, then record the demo video and make slides
- **Run the app:** `python -m tracevision.api` → open http://127.0.0.1:8000 → upload a clip → open the report.
- **Suggested demo flow (3–4 min):**
  1. Upload **clip03**: a registered car is matched (`DL3CCY1025`, score 100) with reasons. Show the per-frame characters and the fused plate.
  2. Show **clip04**: a match from a **partial plate** (`UP1?FT?44?` → `UP16FT9444`). That's the `?` rule plus wildcard matching.
  3. Show **clip02 or clip06** (CCTV-style): plates too small → **"no confident match"**, never guessed. Type and colour are still reported.
  4. Show an unregistered car with a fully read plate → "no confident match" (no false identification).
  5. Show the results table from the README.
- **Slides:** problem → pipeline diagram (README) → the two algorithms → results table (README) → limitations (README) → future work.
- Claude can't record video or present. It can draft slides if you ask (e.g. a slide deck).

## 🟠 Should do (makes the results stronger)

### 4. More "in registry" vehicles (optional, about 20 min)
- Only **9 of 51** labelled vehicles are `in_registry = yes`, so the headline "8/9 matched" rests on 9 cases. Changing a few vehicles **with clearly readable plates** from `no` to `yes` in `evaluation/test_clip_labels.csv` (your call, it's your answer key) makes it more convincing. Keep at least 2 `no`. Tell Claude afterwards, so it can re-seed the registry and re-evaluate.

### 5. Review the degraded-variant sample (about 10 min)
- `TRACEVISION_DATA/evaluation/difficult_cases.csv`: for rows with `review_sample = yes`, fill `readable_after_degradation` (yes / partial / no) by looking at the plate in `TRACEVISION_DATA/processed/degraded_clips/<variant>.mp4`. This is a human check the spec asks for. The files are local (not in git), so regenerate them with `python TRACEVISION_DATA/scripts/degrade_clips.py` if needed.

### 6. Originals instead of WhatsApp copies (if you still have them)
- clip01–09 are WhatsApp copies (about 1.5 Mbit/s), which costs plate detail. Copying the phone originals over the same file names (same content, same length) would improve plate reading. Tell Claude, so it can re-run frames, pipeline, reports and evaluation. The labels stay valid as long as the clips are the same footage.

## ⚪ Optional
7. **Pexels credit:** open the clip10/11 links in `evaluation/clips.csv`, check they're the right videos, and note the creator names for the README credits.
8. **`~/Downloads/DS.mp4` and `original-5adf….mp4`** were never checked (PROBLEMS A11). Tell Claude if they're relevant.
9. **witvix** truck-plate dataset (Hugging Face access form) for a harder OCR test (PROBLEMS A2).
10. Fill in the **Owner** names in `TEAM_TASKS.md`.

## Already done (no action needed)
Data prep, models (vehicle detector, plate detector trained, OCR), the judged fusion and matching algorithms with tests, the end-to-end pipeline, the app, **reports for all 11 clips** (`TRACEVISION_DATA/evaluation/reports/`), the evaluation against your labels, the robustness test on degraded clips, and the README. Details: [completions.md](completions.md).
