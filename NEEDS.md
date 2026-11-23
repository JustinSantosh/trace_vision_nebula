# NEEDS: what only the owner / team can do

**Updated:** 2026-11-23 (evening). Everything that can be built without you is built, tested and on GitHub (19 clips, 67 verified vehicles; 14/15 registered vehicles matched, 0/46 false identifications, 0/252 wrong plate characters; cross-camera 5/5 checkable groups linked, 0 wrong). This is what's left **for you**, in priority order.

## 🔴 Must do before submission

### 1. Decide the repo's visibility (1 min)
- The GitHub repo is **public** and contains real number plates: your clips (clip01–09, clip12–19), the Quobotic and zenitsu09 photos, and your own vehicles' plates in the registry (`evaluation_seed` rows).
- **Options:** make it **private** (Settings → Danger Zone → Change visibility) and add teammates and judges as collaborators, or keep it public on purpose.
- **Why:** privacy (PROBLEMS E6, DECISIONS D10). Claude won't change account settings for you.

### 2. Record the demo video and make the slides
- **Run the app:** `python -m tracevision.api` → wait for "Models ready." (15 s – 4 min) → http://127.0.0.1:8000. Widen the window so the live feed and panels sit beside the video.
- **Suggested demo flow (4–5 min):**
  1. **clip03 or clip12** (home page → ▶ video viewer → Play): live playback shows box → plate reads → "checking registry" → **MATCH** with reasons.
  2. **clip04:** a match from a **partial plate** (`UP1?FT?44?` → `UP16FT9444`): the `?` rule plus wildcard matching.
  3. **clip02 or clip06** (CCTV-style): plates too small → **"no confident match"**, never guessed; type and colour still reported.
  4. **clip16:** the hidden-plate Activa is found but its plate stays `?`; the motorcycle `CG04DK1578` is matched.
  5. **Cross-camera:** open **clip17**, select the motorcycle → "Same vehicle in another camera": this angle alone reads `??0??K1578`, both angles pooled give `CG04DK1578` → MATCH. Click through to clip16. Say that pairing is only for **cross-angled cameras** (same spot, different angles).
  6. Upload a **random clip**: strangers' vehicles → "no confident match" (no false identification).
  7. Show the README results table.
- **Slides:** problem → pipeline diagram (README) → the two judged algorithms (multi-frame fusion, registry matching) → cross-camera fusion → results table → honest limitations → future work.
- Claude can't record video or present, but can draft the slide deck if you ask.

## 🟠 Should do (makes the results stronger)

### 3. Review the degraded-variant sample (about 10 min)
- `TRACEVISION_DATA/evaluation/difficult_cases.csv`: for rows with `review_sample = yes`, fill `readable_after_degradation` (yes / partial / no) by looking at the plate in `TRACEVISION_DATA/processed/degraded_clips/<variant>.mp4`. This human check is in the spec. The variants are local (not in git); regenerate them with `python TRACEVISION_DATA/scripts/degrade_clips.py` if needed.

### 4. Originals instead of WhatsApp copies (if you still have them)
- clip01–09 and clip12–19 are WhatsApp copies (about 1.5–2 Mbit/s), which costs plate detail. Copying the phone originals over the same file names (same footage, same length) would improve plate reading. Tell Claude, so it can re-run frames, pipeline, reports and evaluation.

### 5. Full plates for three of your vehicles (if you know them)
- The dark SUV (`CG04?S9584`: is the 5th character O or Q?), the Activa whose plate is hidden by a tag, and the plate-less scooter are marked `in_registry = yes`, but nobody has written their full registration, so they can't be in the registry. Add `registry_plate_full` in `evaluation/test_clip_labels.csv` if you know them, then tell Claude to re-seed and re-evaluate.

## ⚪ Optional
6. **Pexels credit:** open the clip10/11 links in `evaluation/clips.csv`, check they're the right videos, and note the creator names for the README credits.
7. **`~/Downloads/DS.mp4` and `original-5adf….mp4`** were never checked (PROBLEMS A11). Tell Claude if they're relevant.
8. **witvix** truck-plate dataset (Hugging Face access form) for a harder OCR test (PROBLEMS A2).
9. Fill in the **Owner** names in `TEAM_TASKS.md`.

## ✅ Done (no action needed)
- Cross-camera clips **clip12–19** filmed (4 pairs), labelled (AI draft, owner-verified) and linked (PROBLEMS A6).
- **clip08_v02 / v03** plates checked by the owner: the system's reads `UP37P1176` and `DL3SS5192` are correct; labels updated.
- Data prep, models, the judged fusion and matching algorithms with tests, the two-detector pipeline, the app with video viewer, live playback and cross-camera panel, **reports for all 19 clips** (`TRACEVISION_DATA/evaluation/reports/`), the evaluation against your labels, and the README. Details: [completions.md](completions.md).
