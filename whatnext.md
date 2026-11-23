# TRACEVISION AI — What Next

**Last updated:** 2026-11-23 (evening) · Done work: [completions.md](completions.md) · Owner actions: [NEEDS.md](NEEDS.md) · Problems: [PROBLEMS.md](PROBLEMS.md) · Decisions: [DECISIONS.md](DECISIONS.md) · Pipeline design: [PIPELINE.md](PIPELINE.md) · Team workstreams: [TEAM_TASKS.md](TEAM_TASKS.md)

**Where we are:**
- **Built, tested and evaluated end to end.** 19 clips, 67 owner-verified vehicles: **14/15 registered vehicles matched, 0/46 false identifications (+0/6 on registered vehicles with unknown plates), 0/252 wrong plate characters**, 61/67 vehicles found, type 95% compatible, colour 59% exact.
- **Cross-camera:** the four declared, cross-angled parking pairs are linked jointly with evidence pooled from both angles: **5 of 5 checkable groups correct, 0 wrong** (M16).
- **App:** upload → video viewer with live playback (box → plate reads → registry check → decision), per-vehicle details, cross-camera panel, HTML/PDF report per clip.
- **Enforcement add-on:** synthetic vehicle records and e-challans for confident matches, simulated challans, and wrong-side driving (fixed and moving cameras) with a review queue and an audit log. Team guide: [ENFORCEMENT.md](ENFORCEMENT.md).
- **What's left for submission is owner work: [NEEDS.md](NEEDS.md)** (repo visibility, demo video, slides).

## 0. Owner / team actions

| Priority | Action | Status |
|---|---|---|
| ✅ | **Test clips:** 19 clips: clip01–09 own footage, clip10–11 Pexels (linked, not re-hosted), clip12–19 four cross-angled parking pairs. 2 are fixed CCTV-style (clip02, 06). | Done |
| ✅ | **Labels:** 67 vehicles, owner-verified (clip12–19 from an AI draft accepted by the owner, E11); clip08_v02/v03 plates confirmed by the owner. Validator: 0 errors. | Done |
| ✅ | **Cross-camera pairs** (A6): filmed, labelled (groups X1–X7), linked. | Done |
| 🔴 1 | **Repo visibility:** public, with real plates (E6 / D10). | Owner decision |
| 🔴 2 | **Demo video and slides** (demo flow in NEEDS.md). Claude can draft slides. | Owner |
| 🟠 3 | Review the degraded-variant sample (`difficult_cases.csv`, human check from the spec). | Owner, 10 min |
| 🟡 4 | Phone originals instead of WhatsApp copies; full plates of the 3 `in_registry = yes` vehicles nobody can read. | Optional |
| ⚪ 5 | Pexels creator credits; the two unchecked `.mp4` in Downloads (A11); witvix (A2); owner names in TEAM_TASKS. | Optional |

## 1. Phase 0 (data): status
- [x] 0A audit · 0B plate data (validated, short-name copy, `data.yaml`) · 0C Awiros check (81.5% exact, GPU 15 ms per crop)
- [x] 0D: 19 clips, frames, contact sheets, template, guide; labels verified (67 vehicles)
- [x] All 10 spec scripts exist and pass a smoke run
- [x] 0E: degraded variants (made for clip01–11; local) and `multi_frame_sequences.json` (67 sequences)
- [x] 0F: registry re-seeded from the labels (12 `evaluation_seed` rows + fictional decoys); thresholds recalibrated (unchanged 67.5 / 4.0)
- [x] `cross_camera_ground_truth.csv`: 7 groups (X1–X7)
- [ ] **Final Phase 0 report** (`reports/phase0_final.md`): Claude can write it now; nothing blocks it.

## 2. Build steps (PIPELINE.md §10)
- [x] **P1** vision stack (UVH-26 + COCO YOLOv8n ensemble, M15; OCR in its own GPU process)
- [x] **P2** plate detector: YOLOv8n fine-tuned, leakage-free mAP50 0.995
- [x] **P3** judged algorithms: multi-frame fusion (`?` rule) + registry matching (match score, reasons, match / ambiguous / no-match), calibrated on synthetic cases
- [x] **P4** pipeline: detect + track (two detectors) → re-link → phantom-box check (C11) → best frames → plate → OCR → fuse → type → CLIP colour → match
- [x] **P5** FastAPI app, video viewer with live playback, cross-camera panel, HTML/PDF reports for all 19 clips
- [x] **P6** evaluation (one-to-one label association, E14) and robustness sweep (*robustness numbers predate the ensemble and CLIP colour*)
- [x] **Bonus:** cross-camera re-identification: plate-led open-world linking + joint linking with pooled evidence for declared cross-angled pairs (M14, M16)
- [x] **Add-on:** enforcement (vehicle records, challans, wrong-side driving with review), E17–E20

## 3. Submission
- [x] README: results, architecture diagram, how to run, models and licences, cross-camera section, honest limitations
- [x] Team hand-off PDF (`TRACEVISION_Team_Handoff.pdf`)
- [ ] Demo video and slides (owner)
- [ ] Repo visibility (owner)

## 4. Optional improvements (known weak spots)

| # | Improvement | Problem | Size |
|---|---|---|---|
| 1 | **Colour** (59% exact): a small trained colour classifier, or background removal before CLIP | C8, C12 | Medium |
| 2 | **Duplicate nested boxes** in the pipeline itself (now folded only for cross-camera linking) | C12 | Small |
| 3 | **Car vs SUV** confusion | C9 | Medium |
| 4 | **Stricter OCR confidence on low-quality plates** (blur / 360p / night can be confidently wrong) | C10 | Small |
| 5 | **Re-run the robustness sweep** with the current pipeline and include clip12–19 | — | Small |
| 6 | A dedicated **vehicle re-ID model** for cross-camera matching without plates (open world) | C12 | Large |
| 7 | A true **real-time mode** (analyse while playing); needs re-evaluation | — | Medium |
| 8 | **More wrong-side clips** (fixed camera, and a moving camera on a known two-way road) to measure the check instead of showing one example | E18, E19 | Small (filming) |
| 9 | Wrong-side check for **two-wheelers** (the front/rear prompts are for cars) | E19 | Medium |
| 10 | **Other violations** on the same tracks: triple riding (count riders on a motorcycle box), illegal parking (stationary in a no-parking zone) | — | Medium |
| 11 | **Authenticated roles** for owner data (removed from the demo at the owner's request) | E17 | Medium |

## Installs
None required: everything is in the README install line (torch 2.14.1+cu126, ultralytics, paddlepaddle-gpu 3.3.1 cu126, fastapi, reportlab, open_clip_torch, …). UVH-26 weights are downloaded by hand (README). Optional: FFmpeg (C1).
