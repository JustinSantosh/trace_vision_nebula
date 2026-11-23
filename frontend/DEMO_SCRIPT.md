# Three-minute judge demo click path

**Updated 2026-11-23.** The app now has four tabs, **Cases · Cross-camera · Performance · Enforcement**. The Overview page, Ctrl+K palette and "Rehearse demo mode" from the earlier UI are gone, so this script was rewritten. The full guide with narration and judge Q&A is [HACKATHON_DEMO_GUIDE.md](../HACKATHON_DEMO_GUIDE.md).

Use the local app at `http://127.0.0.1:8000`. This script uses stored results only.

## 0:00–0:25 · Set the frame

Start on **Cases**: 19 stored clips with their registry outcomes. Say that unknown plate characters stay `?` and that a weak match is reported as "no confident match". If the engine status says stored results only, say the machine is reviewing stored results; don't start an upload.

## 0:25–1:05 · One clip, one vehicle

Open **clip03**, select **T1** (`DL3CCY1025`). Click the **Plate** finding (per-frame reads, per-character confidence), then **Registry** (the decision rule checked in order, the candidates). Then select **T13**: read in full, not in the registry, so "no confident match".

## 1:05–1:45 · Compare two cameras

Open **Cross-camera**, choose **clip12 ↔ clip13**, click the link. Show the **Confirmed** tag, why they're linked, and the pooled registry result. Choose **clip16 ↔ clip17**: one camera alone read only part of the plate; pooled, it's a match. Link scores are ranking scores, not probabilities.

## 1:45–2:10 · Measured performance

Open **Performance**: 14/15 matched, 0/46 false identifications, 0/252 wrong characters. Click a metric to show its definition and source file. Point out the small test set.

## 2:10–2:45 · Enforcement (synthetic data)

Back to **clip03 → T1 → Vehicle record → Look up**: owner, compliance, e-challan history, all labelled synthetic. Issue a challan and cancel it. Then open **Enforcement**: the wrong-side review queue (with `ws01.mp4` if it was uploaded on this machine), the simulated challans, and the audit log.

## 2:45–3:00 · Close with an honest miss

Open **clip02**: raised CCTV view, plates under 16 px, so every vehicle is "no confident match", with type and colour still reported. Leave `?` characters and no-match decisions unchanged; they are part of the evidence.
