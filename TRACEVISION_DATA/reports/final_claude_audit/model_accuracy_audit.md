# Model accuracy audit

The four kinds of evidence are kept apart. **VCoR benchmark** = public dataset splits. **CCTV evaluation** = the
team's 19 labelled clips. **Real-world performance** = not measured (no deployment data). **Unit tests** = logic only.

## Colour: the one model change, and why
### Finding
The shipped probe v1 (`train_linear_probe.py`) minimises `mean CE + 0.5·(1/C)·‖W‖²`. Because the CE is a mean,
this penalty is N = 7,208 times stronger than the usual `0.5‖W‖² + C·ΣCE`. Diagnosis (`scripts/colour_leakage_and_cctv_transfer.py`
and a scratch diagnostic):
- every weight row has norm ≈ 1.0–1.8 on unit-length features → all logits within ≈ 0.2 of each other;
- the per-class bias then decides most outputs (`other` +0.18 → 37 of 62 CCTV crops called `other` by argmax);
- through the production path (`estimate_colour(method="linear_probe")`, confidence gate 0.25) v1 answers **`unknown` for 62/62 CCTV crops** and never reaches the gate;
- validation accuracy was still rising at the largest C tried (100).

The cached embeddings were confirmed consistent with production inference (re-embedding 24 VCoR images with
`colour._clip_model`: cosine 1.0000).

### Fix: probe v2 (`TRACEVISION_DATA/scripts/train_linear_probe_v2.py`)
Same embeddings, same splits, same classes. Train-split standardisation (folded into W, b so the file format is
unchanged), the standard penalty, L-BFGS run to convergence, C picked by **validation** macro-F1 from
0.001–10 (picked 0.1, inside the grid). Test split scored once after selection.

| VCoR split | CLIP zero-shot | Probe v1 | **Probe v2** |
|---|---|---|---|
| Validation acc / top-2 / macro-F1 | 59.9 / 68.2 / 59.9 | 63.5 / 77.5 / 61.4 | **85.0 / 96.5 / 85.0** |
| Test acc / top-2 / macro-F1 | 60.1 / 67.4 / 59.7 | 60.8 / 74.9 / 58.9 | **81.3 / 95.7 / 80.7** |

Per-class figures and the confusion matrix: `vcor_probe_v2_evaluation.md`. Zero-shot has no `other` class, which
costs it the `other` rows on VCoR; that is part of why the VCoR gap is large.

### Leakage check (VCoR)
Max cosine similarity of every val/test embedding to any train embedding: **0** val and **0** test images at ≥ 0.995
(near-identical), 7 val / 3 test at ≥ 0.98. Val vs test at ≥ 0.995: 0. This rules out exact and near-exact
duplicates across splits; it does not prove the absence of the same physical vehicle photographed twice.

### CCTV transfer (reporting only; these labels were not used to train or choose anything)
62 vehicle crops from 17 clips (clip10/11 videos are not on disk), cut from the labelled first-frame boxes, run
through the production `estimate_colour` (night rule included):

| Method | Exact | Near (white≈silver≈grey etc.) | `unknown` (night rule / gate) | CPU ms per crop |
|---|---|---|---|---|
| Heuristic | 18/62 | 39/62 | 9 | 6 |
| **CLIP zero-shot (production)** | **29/62** | **43/62** | 9 | ≈1,800 first call incl. text prompts; ≈ 500–900 after |
| Probe v1 | 0/62 | 0/62 | 62 | ≈ 520 |
| Probe v2 | 19/62 | 25/62 | 9 | ≈ 790 |

Earlier report `vcor_audit/phase_3_cctv_evaluation.md` gave zero-shot 32/62; the difference is that its script
lower-cased the vehicle type (`suv` is not in the prompt noun table, so it fell back to "vehicle"); the run above
uses the type labels the pipeline actually passes.

**Decision:** production stays `colour.method: clip`. v2 is a real fix of a broken option and much better on
clean crops, but it does not transfer to these CCTV crops (VCoR images are tight, well-lit catalogue shots). Choosing
between methods using the CCTV numbers would be selection on the test set, so a switch should wait for a separate,
held-out CCTV colour set. Colour stays supporting evidence (15% weight in matching), never identity.

## Detection, tracking, plates, OCR, matching, cross-camera, wrong-side
No change was made. Reason per stage:

| Stage | What exists | Why no change |
|---|---|---|
| Vehicle detection (UVH-26 + COCO ensemble) | 61/67 detected+tracked on the eval clips | The only labelled data are the eval clips; tuning `vehicle_conf`/NMS on them is test-set tuning. No other labelled CCTV detection set is on disk. |
| Tracking (ByteTrack + relink) | — | No MOT-style ID labels → ID switches / fragmentation cannot be measured. No claim is made. |
| Plate detection (YOLOv8n fine-tuned) | leakage-free test mAP50 0.995 (team report, Roboflow split) | That split is near-saturated; CCTV plates < 16 px are deliberately refused (M8), which is the main CCTV limit. |
| OCR + fusion | 0/252 wrong characters, 84% read, 16% `?` | The `?` rule (share ≥ 0.6, prob ≥ 0.8) is the system's key safety property; loosening it would raise "read" at the price of wrong characters. |
| Registry matching | 14/15 matched, 0/46 false | Thresholds were calibrated on held-out synthetic cases (calibrate.py), not on eval clips. Kept. |
| Cross-camera | 5/5 checkable groups | Plate-confirmed links only give identity; appearance-only links stay "probable". Kept. |
| Wrong-side | 0 flagged on 2 fixed + 17 moving-camera clips (stored) | Severity tiers added earlier are kept; flagged items still need a human review before any challan. |

## What would raise accuracy next (needs data, not code)
1. A held-out CCTV colour set (≥ 300 crops) to choose between zero-shot and probe v2, or to fine-tune the probe on CCTV crops.
2. MOT-labelled sequences for tracking metrics.
3. Higher-resolution CCTV (plates ≥ 16 px) — the single biggest limit on plate reading from raised cameras.
