# TRACEVISION AI — Hackathon Demo Guide (4 minutes)

Every step uses **stored results** produced earlier by the full pipeline (`runs/clip*/result.json`). Each observation below was checked against those files on 2026-11-23. Nothing is analysed live during this demo. If you have the GPU machine and want to show a live upload, do that **after** this script (see "Optional: live upload").

## Before you start (5 minutes before)

```powershell
cd C:\Users\PC-01\trace_vision_nebula
$env:TRACEVISION_UI_ONLY = "1"            # stored results only; no model is loaded
.\.venv\Scripts\python.exe -m tracevision.api
```
Open **http://127.0.0.1:8000** in a maximised browser window. Check that:
- the Overview shows **14/15**, **0/46**, **0/252** (from `p6_evaluation_baseline.json`)
- the upload card says **"Live analysis is off on this machine"**. That's expected in UI-only mode; say so if asked.

On the RTX 3050 machine with the full stack you can run `python -m tracevision.api` without the variable. Uploads then work.

## The sequence

| # | Time | Open | What the judges should see |
|---|---|---|---|
| 1 | 0:00–0:30 | **Overview** | "Case file at a glance": 19 clips, 219 tracked vehicles, 14 registry matches, 205 "no confident match", 6 cross-camera links. Below it, the evaluation: 14/15 registered vehicles matched, **0/46 false matches**, **0/252 wrong plate characters**. |
| 2 | 0:30–1:15 | **clip03**, vehicle **T1** | Registered car read in full, `DL3CCY1025`. All four decision steps pass; match score **100.0**, +13.3 over #2. Eight per-frame OCR reads with per-character confidence; the timeline ticks mark the frames used. |
| 3 | 1:15–1:45 | **clip03**, vehicle **T13** | Plate read in full, `DL5CX2452`. **Not in the registry** (the label says so), so the decision is **no confident match**: step 1 fails with "no registry vehicle is close". No false identification. |
| 4 | 1:45–2:30 | **clip04**, vehicle **T2** | Partial plate **`UP1?FT?44?`**: three characters unreadable, kept as `?`. Step 2: **7 of 10** readable (needs 5). Top candidate `UP16FT9444`, score **81.1**, **+15.6** over #2. The comparison row shows the `?` cells as dashed wildcards; they are never filled in. |
| 5 | 2:30–3:00 | **clip02** (or clip06) | Raised CCTV-style footage: 33 vehicles tracked (74 in clip06), **0 plates read**, every decision "no confident match". Plates there are under 16 px, so the system declines to read them. It still reports type and colour. |
| 6 | 3:00–3:50 | **Cross-camera → clip12 ↔ clip13**, then **clip16 ↔ clip17** | clip12↔13: the same white car seen from two angles, **CONFIRMED · PLATE**, pooled identity → registry MATCH 100.0. clip16↔17: clip17 alone read only `??0??K1578`; the joint link pools both cameras into `CG04DK1578` → MATCH. The second link is labelled **PROBABLE · NOT AN IDENTITY** (appearance only). |
| 7 | 3:50–4:00 | **Reports → clip03** | The stored HTML report preview, plus HTML/PDF downloads. |

### How to open each item
- **Results:** Overview → "Explore a sample result" → the clip's card → **Open stored result**. Or type `http://127.0.0.1:8000/#results/runs/clip03` in the address bar.
- **Vehicle:** click its row in the **Evidence index** (right side), or click its box on the video.
- **Cross-camera:** sidebar → Cross-camera → choose the pair in **CLIP PAIR**. The **"Joint links for this camera pair"** section is the evaluated output; "Directional link evidence" below it shows each direction scored alone.
- **Ctrl+K** opens the command palette. `?` opens About & limitations.

## What to say (suggested narration)

1. "TRACEVISION follows one rule: **never guess**. A plate character we can't read stays `?`. If the evidence doesn't support a registry match, we say *no confident match*."
2. (clip03 T1) "Eight frames were read and fused character by character. Each cell shows the OCR confidence for that character. The match score ranks registry records; **it is not a probability**. The detector, OCR and match scores are three different numbers, shown separately."
3. (Decision panel) "This is the actual decision rule, with the thresholds stored alongside this result: at least 5 readable characters, a score of at least 67.5, and a lead of at least 4 over the runner-up. You can see which step decided."
4. (clip03 T13) "A perfectly read plate that isn't in the registry. A weaker system would return its closest record. Ours returns nothing."
5. (clip04) "Three characters were unreadable. We keep them as wildcards. The remaining seven are enough to single out one record by a clear margin, but the `?` stay `?`."
6. (clip02) "On real CCTV height, plates are a few pixels tall. We say so instead of inventing a plate, and still give type and colour."
7. (Cross-camera) "Two cameras on the same parking spot. A plate-confirmed link pools evidence from both cameras. That's how a partial read in one camera becomes a full identity. Links based only on appearance are marked *probable* and never treated as an identity."

## Expected judge questions (with honest answers)

| Question | Answer |
|---|---|
| *Is the match score a probability?* | No. It's a 0–100 ranking score: 100 × (0.70·plate + 0.15·colour + 0.15·type), with unknown attributes left out of the weighting (`tracevision/match.py`). Thresholds 67.5 / 4.0 were calibrated on held-out synthetic cases. |
| *How big is the test set?* | 19 clips, 67 owner-verified vehicles, 15 registered. Small, and several pipeline rules were tuned on these clips, so the numbers may be optimistic. |
| *Is this CCTV?* | Two clips (clip02, clip06) are raised CCTV-style views. Most of the rest are ground-level or dashcam footage, and clip12–19 are parking-camera pairs. On real CCTV, plates are often too small, and the system abstains. |
| *Does cross-camera work city-wide?* | No. It's scoped to **owner-declared same-scene pairs**: two cameras at the same spot with overlapping views. 5 of 5 checkable reference groups were linked correctly with 0 wrong links. 2 of 7 groups weren't tracked at the labelled frame. |
| *How robust is it to bad video?* | On degraded copies (blur, 360p, JPEG, night, noise) there were 0 false identifications, but identification dropped (1/8 under strong blur/360p/night) and up to 17% wrong characters at 360p. That sweep predates the latest pipeline changes and wasn't re-run. |
| *Why only 14 of 15?* | The miss never shows a plate taller than 13 px, below the 16 px reading threshold, so it was correctly not read. |
| *Is the registry real?* | No. It's synthetic: fictional records, plus the team's own test vehicles as `evaluation_seed` rows. There are no owner names, phone numbers or addresses. |
| *Why are there no plate crops in the viewer?* | Crop images are git-ignored and are recreated when the pipeline runs. The stored HTML/PDF reports contain the crops. |

## If something fails

| Problem | Recovery |
|---|---|
| Page won't load | Check the server window for `Uvicorn running on http://127.0.0.1:8000`. If port 8000 is busy, run `Get-NetTCPConnection -LocalPort 8000 -State Listen \| % { Stop-Process -Id $_.OwningProcess }`, then start again. |
| Video won't play | The evidence index, decision panel and candidates still work without video. Use the **HTML report** button on the results page instead. clip10/clip11 videos aren't in the repo (Pexels licence). |
| Browser shows old styles | Hard refresh (Ctrl+F5). |
| Laptop fails completely | Open `runs/clip03/report.pdf` and `runs/clip04/report.pdf` directly. They're self-contained. |
| Asked to analyse a new clip | Only on the GPU machine with the full stack (`python -m tracevision.api` without the UI-only variable). On the laptop, say live analysis needs the GPU stack and show the stored result instead. |

## Optional: live upload (GPU machine only)
Requires CUDA PyTorch, PaddlePaddle, the UVH-26 / COCO YOLOv8n weights and the PaddleOCR submodule (see `CURRENT_PROJECT_AUDIT.md` §4). Start without `TRACEVISION_UI_ONLY`, wait for "Engine ready", drop a clip on **Analyse a clip**, and open the result when the job reaches "Complete". The progress tracker shows real job status only (queued → analysis → report → complete), not simulated per-stage progress.
