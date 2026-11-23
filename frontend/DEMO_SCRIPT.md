# Three-minute judge demo click path

Use the local app at `http://127.0.0.1:8000`. This script uses stored results only. The Demo mode progress is simulated and does not upload a clip, run the pipeline, or create new evidence.

## 0:00–0:25 · Set the frame

Start on Overview. Point out that the evaluation figures come from local report files and that unknown plate characters remain `?`. If the engine status is unavailable, say the machine is reviewing stored results; do not start an upload.

## 0:25–1:05 · Compare two cameras

Press **Ctrl+K**, search for **Cross-camera review**, and open it. Select **clip12 ↔ clip13**. Press **Play both** briefly, then show the recorded T1-to-T1 link, its evidence and score components, and the separate X1 reference outcome. Clarify that reference labels (`clip12_v01`) are not pipeline track IDs.

Select **clip14 ↔ clip15**. Show the linked and no-link decisions, including the partial plate characters and candidate reasons. Point out that each direction is shown as recorded; a reverse-direction decision may differ. Link scores are heuristic ranking scores, not probabilities.

## 1:05–1:35 · Show measured performance

Press **Ctrl+K**, search for **Evaluation insights**, and open it. Point to the current labelled-set metrics, the degraded-video variants, and the cross-camera reference outcomes. Read the denominators and source note; avoid presenting the small evaluation set as a general guarantee.

## 1:35–1:55 · Open the report

Use the **Reports** navigation item. Select **clip03**, scroll the in-app preview briefly, and show the existing HTML and PDF download controls.

## 1:55–2:45 · Rehearse a stored result

Press **Ctrl+K**, search for **Rehearse demo mode**, choose **clip03**, and start the walkthrough. The stage sequence is labelled simulated. When it finishes, click **Open stored result**. Show the demo banner, annotated playback, the readable fused plate, and the separated detector, OCR, and top-candidate scores.

## 2:45–3:00 · Close with an honest miss

Use the vehicle evidence index to select a vehicle with no confident match and show its recorded reason. Then dismiss the demo banner or return to Overview. Leave `?` characters and no-match decisions unchanged; they are part of the evidence.
