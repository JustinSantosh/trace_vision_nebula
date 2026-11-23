# TRACEVISION AI — VCoR Dataset Licence & Intellectual Property Review
**Document ID:** `VCOR-LIC-01`  
**Date:** 2026-11-23  
**Status:** COMPLETED · AUDIT FINDING  
**Target Dataset:** `TRACEVISION_DATA/datasets/vcor/`  

---

## 1. Executive Summary

This document establishes the licensing provenance, copyright restrictions, and redistribution terms governing the **VCoR (Vehicle Color Recognition)** dataset used for fine-grained vehicle colour classification in TRACEVISION AI.

> [!IMPORTANT]
> **Legal Notice:** This review is an engineering compliance assessment based on documented public metadata and open-access scientific publications. It does not constitute formal legal counsel or a binding legal opinion.

### Summary Status Table
| Component | Applicable Licence / Status | Permitted for Training? | Permitted for Git Redistribution? | Commercial Status |
|---|:---:|:---:|:---:|:---:|
| **Kaggle Dataset Metadata** | **Apache License 2.0** (with attribution clause) | **YES** (Internal Research) | **NO** (Raw images stay local) | `UNVERIFIED` |
| **Research Paper** | **Creative Commons Attribution 4.0 (CC BY 4.0)** | **YES** | **YES** (Paper text & citations) | Open Access |
| **Third-Party Notebooks / Repos** | Apache 2.0 / MIT / Unspecified | **YES** | n/a | Non-binding |
| **Derived Trained Weights (Linear Probe)** | Derivative Functional Artifact | **YES** (Demo / Hackathon) | **YES** (Weight tensors only) | `UNVERIFIED` |

---

## 2. Component-by-Component Licence Analysis

### 2.1 Original Kaggle Dataset Page
- **Dataset Title:** VCoR (Vehicle Color Recognition) Dataset
- **Publisher / Curator:** Landry Kezebou (with Karen Panetta, Sos Agaian, Tufts University)
- **URL:** `https://www.kaggle.com/datasets/landrykezebou/vcor-vehicle-color-recognition-dataset`
- **Metadata Badge Licence:** **Apache 2.0**
- **Explicit Description Clause:**
  > *"The dataset is freely available for research and education purposes. If you use this dataset, please cite the following paper:*  
  > *Panetta, Karen, Landry Kezebou, Victor Oludare, James Intriligator, and Sos Agaian. 2021. 'Artificial Intelligence for Text-Based Vehicle Search, Recognition, and Continuous Localization in Traffic Videos' AI 2, no. 4: 684-704."*
- **Assessment:** While Apache 2.0 is an OSI-approved permissive open-source license that normally grants commercial redistribution rights with attribution, the curator's descriptive clause specifically limits intended use to *"research and education purposes"*. In legal precedence, custom qualifying text on dataset cards creates ambiguity regarding commercial deployment.

### 2.2 Original Research Paper
- **Title:** *Artificial Intelligence for Text-Based Vehicle Search, Recognition, and Continuous Localization in Traffic Videos*
- **Authors:** Karen Panetta, Landry Kezebou, Victor Oludare, James Intriligator, Sos Agaian
- **Journal:** *AI* (MDPI), Volume 2, Issue 4, Pages 684–704 (2021)
- **DOI:** `10.3390/ai2040041`
- **Licence:** **Creative Commons Attribution (CC BY 4.0)**
- **Data Availability Statement:** Explicitly directs researchers to the author's public Kaggle repository for download.
- **Assessment:** The paper itself is fully open access. Proper academic citation satisfies the author's publication requirements.

### 2.3 Third-Party Notebooks and Repositories
- Multiple community benchmarking notebooks on Kaggle, GitHub, and ResearchGate consume VCoR under default platform terms (MIT or Apache 2.0).
- **Rule of Evidence:** Third-party repository licenses govern only the code in those repositories; they do not grant or expand rights over the underlying VCoR dataset images.

---

## 3. Redistribution Rights

### 3.1 Redistribution of Original Source Images
- **Finding:** **NOT PERMITTED / STRICTLY RESTRICTED**.
- **Justification:**
  1. The VCoR dataset consists of bounding-box vehicle crops extracted from web automotive listings and public traffic cameras.
  2. The underlying copyright of the original photographs belongs to their respective original photographers/dealerships and was not explicitly waived into the public domain.
  3. Including 10,373 scraped raw JPEG images directly in TRACEVISION's public Git repository violates copyright redistribution safe harbors.
- **Action Taken:** `TRACEVISION_DATA/datasets/` has been permanently added to `.gitignore`. No dataset files will be committed or pushed to GitHub.

### 3.2 Redistribution of Derived Trained Model Weights
- **Finding:** **`UNVERIFIED` for commercial production; PERMITTED for academic research, hackathon evaluation, and internal demos.**
- **Justification:**
  1. Under prevailing international copyright law, statistical model weights (e.g., float32 matrices of linear probes or feature heads) are mathematical functional representations, not verbatim reproductions of the underlying training images.
  2. Training a frozen CLIP linear probe transforms image pixels into abstract high-dimensional feature distributions.
  3. However, because the dataset card stipulates *"freely available for research and education purposes"*, deploying derived weights into a commercial SaaS product without express written clarification from Tufts University / the authors remains legally `UNVERIFIED`.
- **Evidence Still Needed for Full Commercial Clearance:**
  - Written confirmation from the dataset authors clarifying whether the Apache 2.0 badge supersedes the "research and education" descriptive text.
  - Confirmation of commercial licensing terms for derived model checkpoints.

---

## 4. Compliance Guidelines for TRACEVISION AI

To maintain complete compliance during Phase 2 and Phase 3:
1. **Local Storage Only:** All VCoR source images remain strictly local in `TRACEVISION_DATA/datasets/vcor/` and excluded from Git tracking via `.gitignore`.
2. **Proper Attribution:** Any report, presentation, or documentation referencing vehicle colour improvements must prominently cite:
   ```bibtex
   @article{panetta2021artificial,
     title={Artificial Intelligence for Text-Based Vehicle Search, Recognition, and Continuous Localization in Traffic Videos},
     author={Panetta, Karen and Kezebou, Landry and Oludare, Victor and Intriligator, James and Agaian, Sos},
     journal={AI},
     volume={2},
     number={4},
     pages={684--704},
     year={2021},
     publisher={MDPI}
   }
   ```
3. **Derived Artifacts Scope:** Model weights produced during subsequent training phases may be shared internally for demo, evaluation, and hackathon presentation purposes under academic fair use.

