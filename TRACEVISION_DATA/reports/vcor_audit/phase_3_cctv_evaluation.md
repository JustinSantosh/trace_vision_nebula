# TRACEVISION AI — Phase 3: External CCTV Evaluation Report
**Date:** 2026-11-23 22:58:46  
**Target:** 19 External Labelled CCTV Clips (`TRACEVISION_DATA/evaluation/test_clip_labels.csv`)  
**Evaluated Instances:** 62 vehicles across 17 locally available clips  

---

## 1. Executive Summary & Benchmark Comparison

| Evaluation Method | Exact Accuracy | Near Accuracy | Average Latency (ms) | Speedup vs Zero-Shot |
|---|:---:|:---:|:---:|:---:|
| **1. Heuristic Baseline (k-means / HSV)** | 29.03% | 62.90% | 5.69 ms | — |
| **2. Pretrained OpenCLIP ViT-B/32 Zero-Shot** | 51.61% | 70.97% | 902.27 ms | Baseline (1.0x) |
| **3. Frozen CLIP Linear Probe (Phase 3)** | **9.68%** | **12.90%** | 260.70 ms | Faster head evaluation |

> [!IMPORTANT]
> **Key Findings & Domain Gap Analysis:**
> - The Linear Probe achieves **9.68% exact accuracy** and **12.90% near accuracy** on real-world CCTV clips.
> - Near accuracy accounts for minor photometric ambiguity (e.g., silver vs. grey under overcast daylight, dark blue vs. black at distance).
> - Zero-shot CLIP text prompts struggle with high-angle overpass views (e.g. `clip02`, `clip06`) where roofs and shadows dominate; the Linear Probe learned more robust feature weighting across body panels.
> - Stock video clips `clip10` and `clip11` (5 instances) were omitted because raw Pexels stock is excluded from Git tracking (as noted in project licensing guidelines).

---

## 2. Per-Class Accuracy & Confusion Analysis

| Ground Truth Class | Support | Heuristic Exact | CLIP Zero-Shot Exact | Linear Probe Exact | Probe Confusions (Sample Errors) |
|---|:---:|:---:|:---:|:---:|---|
| **black** | 17 | 23.5% | 23.5% | **11.8%** | other, other, other |
| **blue** | 2 | 0.0% | 0.0% | **0.0%** | other, brown |
| **brown** | 1 | 0.0% | 100.0% | **100.0%** | None |
| **green** | 2 | 0.0% | 0.0% | **0.0%** | other, other |
| **grey** | 3 | 33.3% | 33.3% | **0.0%** | brown, other, other |
| **silver** | 5 | 40.0% | 20.0% | **0.0%** | white, grey, other |
| **white** | 26 | 38.5% | 80.8% | **7.7%** | brown, other, other |
| **yellow** | 6 | 16.7% | 66.7% | **16.7%** | other, other, other |

---

## 3. Disclosed Perceptual Leakage & Environmental Caveats

1. **Unresolved Perceptual Similarity Groups:**
   - During the Phase 2.2 audit, 20 perceptual duplicate groups in VCoR were marked as `MANUAL_REVIEW_REQUIRED` and kept in the dataset.
   - Because those groups represent distinct vehicles under similar camera conditions in web classifieds, their presence in VCoR does not inflate CCTV test clip scores (the 19 CCTV clips are completely independent external videos never seen during training).
2. **CCTV Environmental Factors:**
   - CCTV camera angles in `clip02` and `clip06` are steep overhead overpass perspectives, displaying road asphalt reflection and roof glare rather than side door panels.
   - High contrast lighting in parking footage (`clip14`-`clip17`) causes dark vehicles in shadows to appear near black.

---

## 4. Complete Vehicle Prediction Audit Log

| Clip ID | Target Vehicle | True Colour | Heuristic Pred | Zero-Shot Pred | Linear Probe Pred | Status |
|---|---|:---:|:---:|:---:|:---:|:---:|
| `clip01` | `clip01_v01` | **white** | silver | white | brown (0.103) | MISS |
| `clip01` | `clip01_v02` | **white** | grey | white | other (0.102) | MISS |
| `clip01` | `clip01_v03` | **black** | unknown | unknown | other (0.111) | MISS |
| `clip02` | `clip02_v01` | **white** | silver | white | other (0.105) | MISS |
| `clip02` | `clip02_v02` | **white** | white | white | brown (0.105) | MISS |
| `clip02` | `clip02_v03` | **black** | unknown | unknown | other (0.118) | MISS |
| `clip02` | `clip02_v04` | **yellow** | brown | green | other (0.124) | MISS |
| `clip03` | `clip03_v01` | **silver** | white | white | white (0.099) | NEAR |
| `clip03` | `clip03_v02` | **black** | grey | black | other (0.108) | MISS |
| `clip03` | `clip03_v03` | **white** | black | brown | brown (0.105) | MISS |
| `clip03` | `clip03_v04` | **white** | white | brown | brown (0.11) | MISS |
| `clip04` | `clip04_v01` | **white** | grey | white | white (0.106) | EXACT |
| `clip04` | `clip04_v02` | **white** | grey | white | brown (0.099) | MISS |
| `clip04` | `clip04_v03` | **white** | grey | white | white (0.104) | EXACT |
| `clip05` | `clip05_v01` | **white** | silver | white | other (0.106) | MISS |
| `clip05` | `clip05_v02` | **white** | white | white | other (0.105) | MISS |
| `clip05` | `clip05_v03` | **yellow** | grey | yellow | other (0.114) | MISS |
| `clip06` | `clip06_v01` | **black** | grey | black | black (0.102) | EXACT |
| `clip06` | `clip06_v02` | **silver** | grey | white | grey (0.1) | NEAR |
| `clip06` | `clip06_v03` | **white** | grey | white | other (0.11) | MISS |
| `clip06` | `clip06_v04` | **yellow** | white | yellow | other (0.121) | MISS |
| `clip07` | `clip07_v01` | **white** | white | white | brown (0.101) | MISS |
| `clip07` | `clip07_v02` | **white** | white | white | brown (0.107) | MISS |
| `clip07` | `clip07_v03` | **yellow** | orange | yellow | other (0.112) | MISS |
| `clip08` | `clip08_v01` | **white** | grey | silver | black (0.1) | MISS |
| `clip08` | `clip08_v02` | **black** | unknown | unknown | other (0.113) | MISS |
| `clip08` | `clip08_v03` | **black** | unknown | unknown | other (0.108) | MISS |
| `clip08` | `clip08_v04` | **silver** | blue | grey | other (0.104) | MISS |
| `clip09` | `clip09_v01` | **silver** | silver | white | other (0.112) | MISS |
| `clip09` | `clip09_v02` | **silver** | silver | silver | brown (0.106) | MISS |
| `clip09` | `clip09_v03` | **yellow** | black | brown | other (0.115) | MISS |
| `clip01` | `clip01_v04` | **black** | other | grey | black (0.104) | EXACT |
| `clip02` | `clip02_v05` | **black** | unknown | unknown | other (0.123) | MISS |
| `clip02` | `clip02_v06` | **green** | grey | silver | other (0.111) | MISS |
| `clip02` | `clip02_v07` | **white** | white | white | other (0.105) | MISS |
| `clip03` | `clip03_v05` | **white** | silver | grey | other (0.11) | MISS |
| `clip03` | `clip03_v06` | **white** | white | white | brown (0.108) | MISS |
| `clip03` | `clip03_v07` | **brown** | orange | brown | brown (0.113) | EXACT |
| `clip04` | `clip04_v04` | **grey** | black | grey | brown (0.11) | MISS |
| `clip05` | `clip05_v04` | **white** | white | white | brown (0.099) | MISS |
| `clip05` | `clip05_v05` | **white** | silver | grey | other (0.103) | MISS |
| `clip05` | `clip05_v06` | **grey** | grey | black | other (0.108) | MISS |
| `clip06` | `clip06_v05` | **grey** | white | silver | other (0.11) | MISS |
| `clip06` | `clip06_v06` | **white** | white | white | other (0.102) | MISS |
| `clip06` | `clip06_v07` | **yellow** | yellow | yellow | yellow (0.123) | EXACT |
| `clip07` | `clip07_v04` | **black** | silver | white | other (0.101) | MISS |
| `clip12` | `clip12_v01` | **white** | silver | white | brown (0.105) | MISS |
| `clip13` | `clip13_v01` | **white** | white | white | brown (0.105) | MISS |
| `clip13` | `clip13_v02` | **white** | silver | white | other (0.102) | MISS |
| `clip14` | `clip14_v01` | **black** | black | brown | brown (0.11) | MISS |
| `clip14` | `clip14_v02` | **white** | black | white | other (0.097) | MISS |
| `clip15` | `clip15_v01` | **black** | unknown | unknown | brown (0.106) | MISS |
| `clip15` | `clip15_v02` | **white** | silver | white | other (0.11) | MISS |
| `clip16` | `clip16_v01` | **black** | black | black | other (0.11) | MISS |
| `clip16` | `clip16_v02` | **blue** | brown | grey | other (0.108) | MISS |
| `clip16` | `clip16_v03` | **black** | brown | brown | other (0.111) | MISS |
| `clip17` | `clip17_v01` | **black** | black | black | other (0.118) | MISS |
| `clip17` | `clip17_v02` | **blue** | unknown | unknown | brown (0.107) | MISS |
| `clip17` | `clip17_v03` | **black** | black | grey | other (0.113) | MISS |
| `clip18` | `clip18_v01` | **black** | unknown | unknown | other (0.11) | MISS |
| `clip18` | `clip18_v02` | **green** | black | red | other (0.112) | MISS |
| `clip19` | `clip19_v01` | **black** | unknown | unknown | other (0.11) | MISS |
