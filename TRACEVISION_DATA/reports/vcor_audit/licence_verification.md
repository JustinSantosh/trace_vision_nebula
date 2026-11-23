# TRACEVISION AI — VCoR Dataset Licence & Intellectual Property Review
**Document ID:** `VCOR-LIC-01-REV2`  
**Date:** 2026-11-23  
**Status:** REVISED AUDIT FINDING · PRE-TRAINING GATE  
**Target Dataset:** `TRACEVISION_DATA/datasets/vcor/`  

---

## 1. Executive Summary

This document establishes the licensing provenance, copyright boundaries, and intellectual property terms governing the **VCoR (Vehicle Color Recognition)** dataset used for fine-grained vehicle colour classification in TRACEVISION AI.

> [!IMPORTANT]
> **Legal Disclaimer:** This document is an engineering compliance assessment based on documented public metadata, open-access academic publications, and repository manifests. It does not constitute formal legal counsel or a binding legal opinion.

### Evidence Separation & Status Summary Table

| Asset / Component | Source Evidence | Stated Licence / Terms | Training Permission | Git Redistribution | Commercial Redistribution | Status |
|---|---|---|:---:|:---:|:---:|:---:|
| **Kaggle Metadata Badge** | Kaggle Dataset Card UI | Apache License 2.0 | Metadata Only | N/A | `UNVERIFIED` | Metadata badge only; contradicted by description |
| **Kaggle Description Text** | Dataset Card Body | *"Freely available for research and education purposes"* | Permitted (Research/Edu) | **NO** | `UNVERIFIED` | Restricts use to research/education |
| **Research Paper** | MDPI *AI* (2021), 2(4), 684–704 | Creative Commons Attribution 4.0 (CC BY 4.0) | Permitted (Paper citation) | **YES** (Citations & text) | Open Access (Paper text only) | Paper licence does **NOT** transfer to scraped images |
| **Underlying Source Images** | Web automotive portals & CCTV crops | Third-party copyright / Unspecified | Permitted (Local Research) | **STRICTLY PROHIBITED** | `UNVERIFIED` | Third-party web photographs |
| **Derived Model Weights** | Statistical tensors from frozen CLIP probe | Functional transformation | Permitted (Local Research / Demo) | Permitted (Weight tensors only) | `UNVERIFIED` | Commercial terms unverified by dataset licensors |

---

## 2. Component-by-Component Licence Analysis

### 2.1 Kaggle Dataset Metadata Badge vs. Description Text
- **Dataset Title:** VCoR (Vehicle Color Recognition) Dataset
- **Publisher / Curator:** Landry Kezebou (with Karen Panetta, Sos Agaian, Tufts University)
- **Kaggle URL:** `https://www.kaggle.com/datasets/landrykezebou/vcor-vehicle-color-recognition-dataset`
- **Metadata Badge Licence:** **Apache 2.0**
  - *Evidence Type:* Platform UI metadata dropdown selection upon upload.
- **Explicit Description Clause:**
  > *"The dataset is freely available for research and education purposes. If you use this dataset, please cite the following paper:*  
  > *Panetta, Karen, Landry Kezebou, Victor Oludare, James Intriligator, and Sos Agaian. 2021. 'Artificial Intelligence for Text-Based Vehicle Search, Recognition, and Continuous Localization in Traffic Videos' AI 2, no. 4: 684-704."*
- **Legal Conflict & Rigorous Assessment:**
  - An Apache 2.0 badge normally grants broad commercial and sublicensing rights.
  - However, the dataset author's explicit descriptive text limits intended usage to *"research and education purposes"*.
  - In copyright and open-source compliance standards, platform metadata badges cannot be assumed to override explicit textual restrictions authored by the curator.
  - Therefore, commercial rights cannot be derived from the Kaggle metadata badge alone.

### 2.2 Research Paper Open Access Status
- **Title:** *Artificial Intelligence for Text-Based Vehicle Search, Recognition, and Continuous Localization in Traffic Videos*
- **Authors:** Karen Panetta, Landry Kezebou, Victor Oludare, James Intriligator, Sos Agaian
- **Journal:** *AI* (MDPI), Volume 2, Issue 4, Pages 684–704 (2021)
- **DOI:** `10.3390/ai2040041`
- **Licence:** **Creative Commons Attribution 4.0 International (CC BY 4.0)**
- **Critical Boundary Distinction:**
  - The CC BY 4.0 licence applies **strictly to the text, figures, and publication layout of the MDPI journal article**.
  - **The CC BY 4.0 licence does NOT automatically cover the underlying image assets or dataset contents.**
  - The paper's "Data Availability Statement" points readers to the Kaggle link, which is governed by the separate Kaggle terms analyzed above.

### 2.3 Underlying Image Assets
- The VCoR dataset consists of bounding-box vehicle crops scraped from online automotive listings and public highway cameras.
- The underlying photographers, dealerships, or camera operators have not executed copyright assignments or public domain dedications (CC0).
- **Redistribution of Raw Images:** **STRICTLY PROHIBITED**. Raw image files must never be checked into source control or hosted on public servers.
- Local processing for research and non-commercial model training falls within recognized fair-use / computational analysis doctrines, provided images remain on local non-public storage.

### 2.4 Derived Model Weights (Phase 3 Linear Probe)
- Training a linear probe or fine-tuned classifier over frozen OpenCLIP embeddings generates a mathematical transformation ($\mathbf{W} \in \mathbb{R}^{d \times c}$) of feature space.
- Weights are functional model parameters and do not contain reconstructible copies of the original image pixels.
- **Commercial Status:** **`UNVERIFIED`**.
  - While academic research, hackathon evaluation, and prototyping are fully covered under the author's research grant and fair use, commercial SaaS deployment or commercial distribution of the derived weights lacks explicit clearance.
  - Direct supporting terms from Tufts University or the dataset authors would be required for commercial productization.

---

## 3. Mandatory Compliance & Attribution Directives

To preserve full compliance across TRACEVISION AI:

1. **Air-Gapped Source Repository:**
   - Raw dataset files in `TRACEVISION_DATA/datasets/vcor/` are strictly ignored by Git via `.gitignore`.
   - Never commit `.jpg` or raw dataset archives to Git.
2. **Prominent Citation Requirement:**
   - All reports, presentations, and technical documentation using VCoR must cite:
     ```bibtex
     @article{panetta2021artificial,
       title={Artificial Intelligence for Text-Based Vehicle Search, Recognition, and Continuous Localization in Traffic Videos},
       author={Panetta, Karen and Kezebou, Landry and Oludare, Victor and Intriligator, James and Agaian, Sos},
       journal={AI},
       volume={2},
       number={4},
       pages={684--704},
       year={2021},
       publisher={MDPI},
       doi={10.3390/ai2040041}
     }
     ```
3. **Usage Scope:**
   - Phase 3 training and evaluation are conducted under the authorized "research and education" remit.
   - Any future commercial licensing or enterprise SaaS rollout will require author clarification regarding commercial use of derived weights.
