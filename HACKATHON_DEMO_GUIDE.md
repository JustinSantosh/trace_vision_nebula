# TRACEVISION AI — Hackathon Demo Guide (4 minutes + 1 optional)

**Updated 2026-11-23** for the redesigned app (tabs **Cases · Cross-camera · Performance · Enforcement**; there is no Overview page, sidebar or Ctrl+K palette any more) and for the enforcement add-on ([ENFORCEMENT.md](ENFORCEMENT.md)).

Every step uses **stored results** produced earlier by the full pipeline (`runs/clip*/result.json`). Each observation below was checked against those files on 2026-11-23. Nothing is analysed live during this demo. If you have the GPU machine and want to show a live upload, do that **after** this script (see "Optional: live upload").

## Before you start (5 minutes before)

```powershell
cd C:\Users\PC-01\trace_vision_nebula
$env:TRACEVISION_UI_ONLY = "1"            # stored results only; no model is loaded
.\.venv\Scripts\python.exe -m tracevision.api
```
Open **http://127.0.0.1:8000** in a maximised browser window. Check that:
- the **Performance** tab shows **14/15**, **0/46**, **0/252** (from `p6_evaluation_baseline.json`)
- the drop area on **Cases** says live analysis is off. That's expected in UI-only mode; say so if asked.
- for the optional enforcement step: open **clip03 → T1 → Vehicle record → Look up** once. If it says "Not Found", the server is older than the add-on: restart it.
- to show the **wrong-side clip** (step 8b), `ws01.mp4` must have been uploaded once **on this machine** with the full stack (uploaded results are not in git). Otherwise skip 8b.

On the RTX 3050 machine with the full stack you can run `python -m tracevision.api` without the variable. Uploads then work.

## The sequence

| # | Time | Open | What the judges should see |
|---|---|---|---|
| 1 | 0:00–0:30 | **Cases**, then **Performance** | Cases: the totals and the table of 19 stored clips with their registry outcomes. Performance: 14/15 registered vehicles matched, **0/46 false matches**, **0/252 wrong plate characters**. |
| 2 | 0:30–1:15 | **clip03**, vehicle **T1** | Registered car read in full, `DL3CCY1025`. All four decision steps pass; match score **100.0**, +13.3 over #2. Eight per-frame OCR reads with per-character confidence; the timeline ticks mark the frames used. |
| 3 | 1:15–1:45 | **clip03**, vehicle **T13** | Plate read in full, `DL5CX2452`. **Not in the registry** (the label says so), so the decision is **no confident match**: step 1 fails with "no registry vehicle is close". No false identification. |
| 4 | 1:45–2:30 | **clip04**, vehicle **T2** | Partial plate **`UP1?FT?44?`**: three characters unreadable, kept as `?`. Step 2: **7 of 10** readable (needs 5). Top candidate `UP16FT9444`, score **81.1**, **+15.6** over #2. The comparison row shows the `?` cells as dashed wildcards; they are never filled in. |
| 5 | 2:30–3:00 | **clip02** (or clip06) | Raised CCTV-style footage: 33 vehicles tracked (74 in clip06), **0 plates read**, every decision "no confident match". Plates there are under 16 px, so the system declines to read them. It still reports type and colour. |
| 6 | 3:00–3:50 | **Cross-camera → clip12 ↔ clip13**, then **clip16 ↔ clip17** | clip12↔13: the same white car seen from two angles, **CONFIRMED · PLATE**, pooled identity → registry MATCH 100.0. clip16↔17: clip17 alone read only `??0??K1578`; the joint link pools both cameras into `CG04DK1578` → MATCH. The second link is tagged **Probable** (appearance only, not an identity). |
| 7 | 3:50–4:00 | **clip03 → Report / PDF** (top right of the case) | The stored HTML report and its PDF. |
| 8a | 4:00–4:30 *(optional)* | **clip03 → T1 → Vehicle record → Look up** | The synthetic record for `DL3CCY1025`: owner, make/model, RTO, registration/insurance/PUC validity, e-challan history with pending amount. Issue a challan (violation → fine fills in), then **Cancel** it. Then open **clip03 → T13** (plate read, not in the registry): it has **no** Vehicle record finding. |
| 8b | 4:30–5:00 *(optional, needs ws01 uploaded)* | **Enforcement → Wrong-side driving · ws01.mp4 T5** | The queue item, plate `HR11P2233`, the evidence: front seen 0:00–0:09 while it grew about 10×, rear seen 0:14–0:18, road declared one-way. **Confirm** it: it leaves the queue; no challan, because the plate isn't in the registry. Then show the **audit log** at the bottom. |

### How to open each item
- **A clip:** **Cases** → click its row. Or type `http://127.0.0.1:8000/#case/runs/clip03` in the address bar.
- **A vehicle:** click it in the **Vehicles** list on the left, or click its box on the video. Its **findings** (Plate, Registry, Type, Colour, Seen, Direction, Vehicle record) are under the video; click one to see its evidence on the right.
- **Cross-camera:** **Cross-camera** tab → choose the pair in the drop-down → click a link. The right panel shows why they're linked, the pooled registry result, and (for a confident pooled match) the vehicle record.
- **Enforcement:** **Enforcement** tab: the review queue, simulated challans raised, the audit log, and a typed registration lookup.

## What to say (suggested narration)

1. "TRACEVISION follows one rule: **never guess**. A plate character we can't read stays `?`. If the evidence doesn't support a registry match, we say *no confident match*."
2. (clip03 T1) "Eight frames were read and fused character by character. Each cell shows the OCR confidence for that character. The match score ranks registry records; **it is not a probability**. The detector, OCR and match scores are three different numbers, shown separately."
3. (Decision panel) "This is the actual decision rule, with the thresholds stored alongside this result: at least 5 readable characters, a score of at least 67.5, and a lead of at least 4 over the runner-up. You can see which step decided."
4. (clip03 T13) "A perfectly read plate that isn't in the registry. A weaker system would return its closest record. Ours returns nothing."
5. (clip04) "Three characters were unreadable. We keep them as wildcards. The remaining seven are enough to single out one record by a clear margin, but the `?` stay `?`."
6. (clip02) "On real CCTV height, plates are a few pixels tall. We say so instead of inventing a plate, and still give type and colour."
7. (Cross-camera) "Two cameras on the same parking spot. A plate-confirmed link pools evidence from both cameras. That's how a partial read in one camera becomes a full identity. Links based only on appearance are marked *probable* and never treated as an identity."
8. (Enforcement, optional) "Once a plate is a *confident* match, we can show the registered record and challan history. This is synthetic demo data, not VAHAN. A vehicle without a confident match gets no record, so a challan can never land on a guessed vehicle. Wrong-side driving is flagged for a person to confirm; nothing is enforced automatically, and every lookup is logged."

## Expected judge questions (with honest answers)

| Question | Answer |
|---|---|
| *Is the match score a probability?* | No. It's a 0–100 ranking score: 100 × (0.70·plate + 0.15·colour + 0.15·type), with unknown attributes left out of the weighting (`tracevision/match.py`). Thresholds 67.5 / 4.0 were calibrated on held-out synthetic cases. |
| *How big is the test set?* | 19 clips, 67 owner-verified vehicles, 15 registered. Small, and several pipeline rules were tuned on these clips, so the numbers may be optimistic. |
| *Is this CCTV?* | Two clips (clip02, clip06) are raised CCTV-style views. Most of the rest are ground-level or dashcam footage, and clip12–19 are parking-camera pairs. On real CCTV, plates are often too small, and the system abstains. |
| *Does cross-camera work city-wide?* | No. It's scoped to **owner-declared same-scene pairs**: two cameras at the same spot with overlapping views. 5 of 5 checkable reference groups were linked correctly with 0 wrong links. 2 of 7 groups weren't tracked at the labelled frame. |
| *How robust is it to bad video?* | On degraded copies (blur, 360p, JPEG, night, noise) there were 0 false identifications, but identification dropped (1/8 under strong blur/360p/night) and up to 17% wrong characters at 360p. That sweep predates the latest pipeline changes and wasn't re-run. |
| *Why only 14 of 15?* | The miss never shows a plate taller than 13 px, below the 16 px reading threshold, so it was correctly not read. |
| *Is the registry real?* | No. It's synthetic: fictional records, plus the team's own test vehicles as `evaluation_seed` rows. The matching registry has no owner fields; the enforcement demo's owner names and challans are **generated** in separate files (`synthetic_owner_records.csv`, `synthetic_echallans.csv`) and every screen says "synthetic demo data". No phone numbers or addresses. |
| *Is this connected to VAHAN / e-Challan?* | No. Those need government authorisation. We show the workflow on synthetic data; a real deployment would swap `intel.py`'s CSV lookup for the authorised service. |
| *How accurate is wrong-side detection?* | We can't give a rate. Fixed cameras: 54 vehicles, 0 false flags, and no real event was filmed (the rule is tested by replaying real tracks backwards). Moving cameras: one downloaded clip, where the wrong-way SUV is flagged and nothing else; 0 false flags over 214 cars in 31 clips. Every flag needs a human to confirm it. |
| *Who can see owner data?* | In this prototype, anyone using the app; there is no login. Every lookup is written to an audit log. A real system would add authenticated roles. |
| *Why are there no plate crops in the viewer?* | Crop images are git-ignored and are recreated when the pipeline runs. The stored HTML/PDF reports contain the crops. |

## If something fails

| Problem | Recovery |
|---|---|
| Page won't load | Check the server window for `Uvicorn running on http://127.0.0.1:8000`. If port 8000 is busy, run `Get-NetTCPConnection -LocalPort 8000 -State Listen \| % { Stop-Process -Id $_.OwningProcess }`, then start again. |
| Video won't play | The evidence index, decision panel and candidates still work without video. Use the **HTML report** button on the results page instead. clip10/clip11 videos aren't in the repo (Pexels licence). |
| Browser shows old styles | Hard refresh (Ctrl+F5). |
| "Not Found" when pressing Look up | The server is older than the enforcement add-on. Stop it (Ctrl+C) and start it again, then reload. |
| The wrong-side clip isn't in the Enforcement queue | It has to be uploaded once on this machine with the full stack, **named `ws01.mp4`** (ENFORCEMENT.md §3). On the laptop, skip step 8b. |
| Laptop fails completely | Open `runs/clip03/report.pdf` and `runs/clip04/report.pdf` directly. They're self-contained. |
| Asked to analyse a new clip | Only on the GPU machine with the full stack (`python -m tracevision.api` without the UI-only variable). On the laptop, say live analysis needs the GPU stack and show the stored result instead. |

## Optional: live upload (GPU machine only)
Requires CUDA PyTorch, PaddlePaddle, the UVH-26 / COCO YOLOv8n weights and the PaddleOCR submodule (see `CURRENT_PROJECT_AUDIT.md` §4). Start without `TRACEVISION_UI_ONLY`, wait for "Engine ready", drop a clip on the **Cases** drop area, and open the result when the job reaches "Complete". The wrong-side check runs automatically after the analysis; for `TRACEVISION_DATA/raw/wrongside/ws01.mp4`, keep the file name `ws01.mp4`. The progress tracker shows real job status only (queued → analysis → report → complete), not simulated per-stage progress.
