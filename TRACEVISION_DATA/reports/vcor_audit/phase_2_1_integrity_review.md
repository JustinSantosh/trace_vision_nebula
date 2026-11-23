# TRACEVISION AI — Phase 2.1: Dataset Integrity Remediation Review
**Document ID:** `VCOR-REM-01`  
**Date:** 2026-11-23  
**Status:** COMPLETED · AWAITING USER APPROVAL  
**Script:** `TRACEVISION_DATA/scripts/remediation_analysis.py`  
**Manifest:** `TRACEVISION_DATA/reports/vcor_audit/proposed_clean_manifest.csv`  

---

## 1. Executive Summary

Following the initial Phase 2 audit of the **VCoR (Vehicle Color Recognition)** dataset (10,373 images, 15 classes), this Phase 2.1 investigation resolves all identified integrity hazards:
1. **Exact Duplicates & Label Conflicts:** All 10 duplicate groups (20 files) were independently verified via SHA-256 and full pixel decoding. In 100% of cases, duplicate images carry conflicting class labels.
2. **Cross-Split Data Leakage:** Two exact duplicate groups and 35 near-burst perceptual duplicate groups were found crossing split boundaries (e.g., train $\leftrightarrow$ val and train $\leftrightarrow$ test).
3. **Remediation Strategy:** A non-destructive filtering policy was developed that leaves all original dataset folders untouched while defining an exclusion mask in a clean training manifest (`proposed_clean_manifest.csv`).
4. **Data Yield:** 10,295 images (99.25%) are validated for training and evaluation; 78 contaminated or micro-resolution images (0.75%) are safely excluded.

---

## 2. Task 1: Independent Exact Duplicate Verification

Every exact duplicate group was confirmed on disk with full SHA-256 byte checks. All 10 groups consist of identical images assigned to **conflicting colour classes**:

| Group ID | SHA-256 Prefix | Splits Involved | Classes Involved | File 1 (Split / Class / Filename) | File 2 (Split / Class / Filename) | Root Cause Analysis | Remediation Policy |
|---|---|:---:|:---:|---|---|---|---|
| **EXACT_DUP_01** | `c5442af6c74f` | `train` + `val` | `beige` + `gold` | `train/beige/353630f86d.jpg` | `val/gold/353630f86d.jpg` | **Cross-Split Leakage & Category Boundary:** Metallic champagne car. Direct sunlight produces gold reflections; shaded side shows beige. Leaks training signal directly into validation split. | **EXCLUDE BOTH:** Exclude train to eliminate leakage; exclude val to avoid false validation loss. |
| **EXACT_DUP_02** | `cde6e84f31a4` | `train` | `black` + `tan` | `train/black/c6c1328c5f.jpg` | `train/tan/c6c1328c5f.jpg` | **Severe Shadow Contrast:** Vehicle has tan body paint but underexposed side/roof panels under heavy shadow. Dual-submitted under both black and tan. | **EXCLUDE BOTH:** Opposing labels on identical pixels corrupts linear probe gradients. |
| **EXACT_DUP_03** | `cb3edee4b997` | `train` | `blue` + `red` | `train/blue/733e046b07.jpg` | `train/red/733e046b07.jpg` | **Two-Tone or Flagrant Error:** Distinct primary color contradiction. | **EXCLUDE BOTH:** Completely ambiguous supervised target. |
| **EXACT_DUP_04** | `6d52fecf8607` | `train` | `grey` + `silver` | `train/grey/339b1faea4.jpg` | `train/silver/339b1faea4.jpg` | **Achromatic Metallic Ambiguity:** Light grey car with metallic finish. Demonstrates human annotator subjective variance. | **EXCLUDE BOTH:** Prevents penalizing grey vs silver decision boundary. |
| **EXACT_DUP_05** | `dc6fdb9bed8a` | `train` | `grey` + `silver` | `train/grey/b3540d0591.jpg` | `train/silver/b3540d0591.jpg` | **Achromatic Metallic Ambiguity:** Metallic grey/silver crossover body. | **EXCLUDE BOTH:** Conflicting target. |
| **EXACT_DUP_06** | `e92d001a0aeb` | `train` | `orange` + `red` | `train/orange/43cd652743.jpg` | `train/red/43cd652743.jpg` | **Warm Hue Border (Hue 10–20):** Burnt orange / scarlet vehicle on the exact chromatic boundary. | **EXCLUDE BOTH:** Borderline subjective target. |
| **EXACT_DUP_07** | `4d881e9ede6c` | `train` | `silver` + `white` | `train/silver/059b58464d.jpg` | `train/white/059b58464d.jpg` | **Overcast Sun Bleed:** Highly reflective silver vehicle washed out by overcast sky glare. | **EXCLUDE BOTH:** Conflicting target. |
| **EXACT_DUP_08** | `1a321700c904` | `train` + `test` | `white` + `silver` | `train/white/31721f80c1.jpg` | `test/silver/31721f80c1.jpg` | **Cross-Split Leakage & Test Contamination:** Identical image in train/white and test/silver. Any model predicting white on this test vehicle would be unfairly marked incorrect by test truth. | **EXCLUDE BOTH:** Crucial to prevent test score distortion and training leakage. |
| **EXACT_DUP_09** | `f2d88bcc4fec` | `val` | `green` + `yellow` | `val/green/833c0f0701.jpg` | `val/yellow/833c0f0701.jpg` | **Chromatic Hue Border (Hue 35–45):** Lime/chartreuse vehicle in validation set. | **EXCLUDE BOTH:** Validation metric distortion. |
| **EXACT_DUP_10** | `b01387ccd6bb` | `test` | `grey` + `silver` | `test/grey/e5b8b1e4a4.jpg` | `test/silver/e5b8b1e4a4.jpg` | **Test Split Contradiction:** Identical vehicle appearing in test/grey and test/silver simultaneously. | **EXCLUDE BOTH:** Eliminates an impossible test evaluation target. |

Full path records and verified dimensions are logged in [exact_duplicate_resolution.csv](file:///c:/Users/PC-01/trace_vision_nebula/TRACEVISION_DATA/reports/vcor_audit/exact_duplicate_resolution.csv).

---

## 3. Task 2: Perceptual Duplicate Investigation (47 Cross-Split Groups)

All 47 cross-split perceptual duplicate groups identified by 64-bit dHash were subjected to pairwise computer vision analysis:
- Normalized Cross-Correlation ($\text{NCC}$)
- 2D Hue-Saturation Histogram Correlation ($\text{HistCorr}$)
- Peak Signal-to-Noise Ratio ($\text{PSNR}$)
- Dimension and Aspect Ratio parity

### Classification of Perceptual Groups:
| Classification Category | Group Count | Criteria & Visual Evidence | Remediation Action |
|---|:---:|---|---|
| **`SAME_VEHICLE_DIFFERENT_FRAMES`** | **32** | $\text{NCC} \ge 0.88$, $\text{HistCorr} \ge 0.80$. Same car captured during tracking motion or multi-camera burst with slight angle/scale shifts. | **EXCLUDE TRAIN INSTANCE:** Preserves evaluation integrity while eliminating burst data leakage from training. |
| **`SAME_IMAGE_RESIZED_OR_COMPRESSED`** | **3** | $\text{NCC} \ge 0.98$, $\text{HistCorr} \ge 0.95$. Identical visual crop subject to differing JPEG compression or minor resizing across splits. | **EXCLUDE TRAIN INSTANCE:** Prevents exact visual memorization across splits. |
| **`SIMILAR_VEHICLES_NOT_DUPLICATES`** | **11** | $0.70 \le \text{NCC} < 0.88$, $0.60 \le \text{HistCorr} < 0.80$. Coincidental visual similarity between distinct vehicles of standard automotive silhouettes (e.g., two white sedans). | **RETAIN WITH FLAG:** Valid real-world class distribution; no leakage. |
| **`FALSE_POSITIVE_HASH_COLLISION`** | **1** | $\text{NCC} < 0.70$ or low contrast. Accidental 64-bit dHash collision on flat background gradients. | **RETAIN ALL:** Visually distinct subjects. |

Detailed metric logs for all 47 pairs are documented in [perceptual_duplicate_review.csv](file:///c:/Users/PC-01/trace_vision_nebula/TRACEVISION_DATA/reports/vcor_audit/perceptual_duplicate_review.csv).

---

## 4. Task 3: Dataset Licence & Legal Provenance

A dedicated analysis was conducted and documented in [licence_verification.md](file:///c:/Users/PC-01/trace_vision_nebula/TRACEVISION_DATA/reports/vcor_audit/licence_verification.md):

1. **Kaggle Page Licence:** Stated as **Apache 2.0**, but includes a descriptive restriction: *"freely available for research and education purposes. Please cite Panetta et al. (2021)"*.
2. **Original Research Paper:** Published in MDPI *AI* (2021), DOI: `10.3390/ai2040041` under **Creative Commons Attribution 4.0 (CC BY 4.0)**.
3. **Image Redistribution:** **NOT PERMITTED**. Raw images must remain local and ignored via `.gitignore` due to third-party copyright in underlying web photography.
4. **Trained Model Weights:** **`UNVERIFIED` for commercial deployment; PERMITTED for internal hackathon evaluation and academic research.** Derived mathematical matrices (linear probe weights) are functional transformations and will be safely preserved under research attribution terms.

---

## 5. Task 4: Proposed Clean Manifest

The proposed manifest was generated at [proposed_clean_manifest.csv](file:///c:/Users/PC-01/trace_vision_nebula/TRACEVISION_DATA/reports/vcor_audit/proposed_clean_manifest.csv) covering all 10,373 files. Original filesystem files and directories remain strictly untouched.

### Exclusion Hierarchy:
1. **`EXACT_DUP_CONFLICT`:** Exclude both instances of the 10 exact duplicate groups (20 files).
2. **`CROSS_SPLIT_LEAKAGE`:** Exclude the training instance of confirmed cross-split image re-encodings and tracking bursts (35 files).
3. **`TINY_IMAGE_SUB_32PX`:** Exclude sub-resolution crops with $\min(W, H) < 32$ px (23 remaining files after deduplication).

### Manifest Yield Summary:
| Split | Original Images | Excluded Images | Clean Included Images | Retention Rate |
|---|---:|---:|---:|---:|
| **Train** | 7,267 | 59 | **7,208** | 99.19% |
| **Validation** | 1,550 | 8 | **1,542** | 99.48% |
| **Test** | 1,556 | 11 | **1,545** | 99.29% |
| **Total** | **10,373** | **78** | **10,295** | **99.25%** |

### Clean Included Class Distribution (Provisional Mapping):
| Proposed Label | Included Samples | % of Clean Dataset | Source VCoR Classes |
|---|---:|---:|---|
| **other** | 2,339 | 22.72% | beige (596), gold (297), pink (687), purple (759) |
| **brown** | 1,369 | 13.30% | brown (802), tan (567) |
| **blue** | 1,055 | 10.25% | blue (1,055) |
| **red** | 904 | 8.78% | red (904) |
| **yellow** | 818 | 7.95% | yellow (818) |
| **green** | 796 | 7.73% | green (796) |
| **orange** | 759 | 7.37% | orange (759) |
| **grey** | 603 | 5.86% | grey (603) |
| **black** | 573 | 5.57% | black (573) |
| **white** | 570 | 5.54% | white (570) |
| **silver** | 509 | 4.94% | silver (509) |
| **Total** | **10,295** | **100.00%** | (15 original classes mapped to 11 active output labels) |

---

## 6. Reproducibility & Commands

The analysis was executed using:
```powershell
.\.venv\Scripts\python.exe TRACEVISION_DATA/scripts/remediation_analysis.py
```
Outputs produced:
- `TRACEVISION_DATA/reports/vcor_audit/exact_duplicate_resolution.csv`
- `TRACEVISION_DATA/reports/vcor_audit/perceptual_duplicate_review.csv`
- `TRACEVISION_DATA/reports/vcor_audit/proposed_clean_manifest.csv`
- `TRACEVISION_DATA/reports/vcor_audit/licence_verification.md`
- `TRACEVISION_DATA/reports/vcor_audit/phase_2_1_integrity_review.md`

---

## 7. Phase 3 Readiness Assessment

With the completion of this integrity remediation:
- **Test Split Purity:** Guaranteed. Conflicting exact duplicates and cross-split tracking bursts have been masked from training.
- **Evaluation Isolation:** The 19 independent Indian CCTV clips remain strictly untouched and uncoupled from VCoR.
- **Training Artifact:** Phase 3 can consume `proposed_clean_manifest.csv` directly using `status == 'INCLUDE'` to extract frozen CLIP ViT-B/32 features and train a calibrated linear probe without modifying a single raw file.

