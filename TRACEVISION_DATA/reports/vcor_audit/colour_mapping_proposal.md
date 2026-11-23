# TRACEVISION AI — Phase 2: VCoR Colour Mapping Proposal
**Document ID:** `VCOR-PROP-01`  
**Date:** 2026-11-23  
**Status:** PROPOSAL (Awaiting User Review and Approval)  
**Target Module:** TRACEVISION Colour Recognition Subsystem (`tracevision/colour.py`)  

---

## 1. Executive Context

TRACEVISION AI performs automated vehicle identification and traceability for traffic surveillance and legal enforcement. Vehicle colour is one of three primary multimodal evidence channels used by the matching engine (`match.py`):
$$\text{Match Score} = 100 \times (0.70 \cdot \text{Plate} + 0.15 \cdot \text{Colour} + 0.15 \cdot \text{Type})$$

The system strictly enforces the distinction between two non-standard states:
- **`unknown`**: Insufficient visual evidence, extreme low-light/night conditions ($\text{mean}(V) < 55.0$), or heavy occlusion. In `match.py`, `unknown` drops the colour term from the denominator without penalising candidate ranking.
- **`other`**: Confident visual detection of a valid physical paint colour that lies outside the system's 10 canonical primary vehicle categories. In `match.py`, an observed colour that does not match or closely relate to a registered colour receives a score of $0.0$ ("colour conflict").

The newly ingested **VCoR (Vehicle Color Recognition)** dataset contains **10,373 vehicle crops across 15 fine-grained color categories**. This proposal evaluates the mapping of these 15 classes into TRACEVISION's 12 supported output labels:
$$\text{TRACEVISION Labels} = \{\text{white, black, silver, grey, red, blue, green, yellow, brown, orange, other, unknown}\}$$

---

## 2. Canonical Classes (10 Direct 1:1 Correspondences)

Ten of the 15 VCoR categories have unambiguous 1:1 semantic and visual counterparts in TRACEVISION:

| # | VCoR Source Class | TRACEVISION Label | Justification | Primary Confusion Risk |
|---|---|---|---|---|
| 1 | **black** | `black` | Direct chromatic match (low value, achromatic). | Dark shadows, unlit night frames. |
| 2 | **blue** | `blue` | Direct chromatic match ($190^\circ \le \text{Hue} \le 260^\circ$). | Dark navy blue misread as black. |
| 3 | **brown** | `brown` | Direct chromatic match (low-value warm orange/red). | Dark brown misread as black; light brown bordering tan. |
| 4 | **green** | `green` | Direct chromatic match ($70^\circ \le \text{Hue} \le 165^\circ$). | Dark forest green misread as black; olive green bordering brown. |
| 5 | **grey** | `grey` | Direct achromatic match (medium value, low saturation). | Boundary overlap with silver and white under bright sun. |
| 6 | **orange** | `orange` | Direct chromatic match ($15^\circ \le \text{Hue} \le 40^\circ$). | Red-orange vehicles bordering red; metallic bronze. |
| 7 | **red** | `red` | Direct chromatic match ($0^\circ \le \text{Hue} \le 15^\circ$ or $\ge 345^\circ$). | Maroon/burgundy misread as brown; sun glare washing out to pink. |
| 8 | **silver** | `silver` | Direct achromatic metallic match ($V \ge 0.50$, metallic specular reflection). | Distinguishing matte grey from metallic silver in CCTV resolution. |
| 9 | **white** | `white` | Direct achromatic match ($V \ge 0.75$, $S < 0.20$). | Specular highlights on silver/grey causing false white calls. |
| 10 | **yellow** | `yellow` | Direct chromatic match ($40^\circ \le \text{Hue} \le 70^\circ$). | Pale pastel yellow misread as white; gold metallic paints. |

---

## 3. Detailed Evaluation of the 5 Non-Standard Classes

The remaining 5 classes (**beige**, **gold**, **pink**, **purple**, **tan**) are not explicitly named in TRACEVISION's canonical 10-color vocabulary. Each is evaluated below across visual, semantic, and investigative risk dimensions.

### 3.1 `beige` (601 images: 421 train / 90 val / 90 test)
1. **Source Class:** `beige`
2. **Visual Characteristics:** Pale sandy neutral, very low saturation ($S \approx 0.10 - 0.25$), high lightness ($V \ge 0.70$).
3. **Proposed TRACEVISION Output Label:** **`other`** (Conservative) or **`brown`** (Registry-aligned).
4. **Visual & Semantic Justification:**
   - In vehicle registration databases (e.g., Indian VAHAN / US NCIC), beige is historically grouped under "BROWN" (Fawn/Cream/Khaki) or occasionally "WHITE / OFF-WHITE".
   - In computer vision feature space (CLIP / HSV), beige forms a distinct cluster between pure white and light tan.
5. **Potential Misclassification Risk:**
   - Forcing `beige` into `white` creates false positives against pure white cars (the most common vehicle color on Indian roads, ~40% of fleet).
   - Forcing `beige` into `brown` creates investigator confusion when reviewing reports: a light champagne/cream sedan marked as "BROWN" appears obviously wrong to a human investigator.
6. **Recommendation:** Map to **`other`** in strict mode, or treat as a compatible near-color under `brown` with an explicit human-readable note: `"beige (subsumed to brown)"`.

---

### 3.2 `gold` (300 images: 210 train / 45 val / 45 test)
1. **Source Class:** `gold`
2. **Visual Characteristics:** Metallic yellow/bronze luster with warm undertones. Highly specular under outdoor sunlight.
3. **Proposed TRACEVISION Output Label:** **`yellow`** (Registry-aligned) or **`other`** (Conservative).
4. **Visual & Semantic Justification:**
   - In vehicle regulatory codes, metallic gold is classified under "YELLOW / GOLD" (e.g., NCIC code `YEL/GLD`).
   - TRACEVISION's `NEAR_COLOURS` matrix in `match.py` already groups `{"brown", "orange", "yellow"}` together, awarding a partial match score of 0.5.
5. **Potential Misclassification Risk:**
   - Calling a champagne-gold executive sedan "yellow" risks conflating it with bright commercial taxis or sports cars.
   - In low light or evening CCTV footage, gold metallic flakes do not reflect, causing it to appear brown or grey.
6. **Recommendation:** Under Strategy 1 (Registry Alignment), map `gold` $\rightarrow$ **`yellow`**. Under Strategy 2 (Evidentiary Rigor), map `gold` $\rightarrow$ **`other`**.

---

### 3.3 `pink` (689 images: 483 train / 103 val / 103 test)
1. **Source Class:** `pink`
2. **Visual Characteristics:** High value, low-to-medium saturation red/magenta ($V \ge 0.70$, $S \approx 0.30 - 0.60$). Rare in production vehicles; mostly aftermarket wraps or specialty promotional vehicles.
3. **Proposed TRACEVISION Output Label:** **`other`** (Unambiguous).
4. **Visual & Semantic Justification:**
   - Chromatically, pink is a desaturated tint of red. However, human witnesses and traffic investigators will never describe a hot-pink or pastel-pink vehicle as "red".
   - The label `other` was explicitly architected into TRACEVISION for rare, valid vehicle colors that do not fit the 10 canonical categories.
5. **Potential Misclassification Risk:**
   - Mapping `pink` $\rightarrow$ `red` would contaminate the `red` classifier embeddings and create investigator distrust ("The witness reported a pink car, but the system claims it is red").
6. **Recommendation:** **Map unconditionally to `other`.** Do not subsume into `red`.

---

### 3.4 `purple` (765 images: 536 train / 114 val / 115 test)
1. **Source Class:** `purple`
2. **Visual Characteristics:** Violet/magenta hue ($270^\circ \le \text{Hue} \le 330^\circ$). Typically seen on luxury finishes, custom wraps, or specific manufacturer lines (e.g., dark plum, violet).
3. **Proposed TRACEVISION Output Label:** **`other`** (Unambiguous).
4. **Visual & Semantic Justification:**
   - Purple is entirely outside TRACEVISION's 10 standard primary colors.
   - Mapping purple to `blue` or `red` distorts the decision boundary for two major primary colors.
5. **Potential Misclassification Risk:**
   - Dark metallic purple in low-light CCTV footage can visually mimic black or navy blue. A trained model forced to pick `blue` will produce false confidences.
6. **Recommendation:** **Map unconditionally to `other`.**

---

### 3.5 `tan` (571 images: 400 train / 85 val / 86 test)
1. **Source Class:** `tan`
2. **Visual Characteristics:** Medium-light brown with warm yellowish-brown undertones ($V \approx 0.40 - 0.65$, moderate saturation). Distinctly darker and browner than beige.
3. **Proposed TRACEVISION Output Label:** **`brown`** (Registry and Semantic Consensus).
4. **Visual & Semantic Justification:**
   - Tan is universally defined in color science and vehicle documentation as a shade of light brown.
   - DMV, police, and automotive catalogs treat tan as a standard sub-type of brown.
5. **Potential Misclassification Risk:**
   - Very light tan crops may visually border beige.
   - Extremely dark tan may visually border brown.
   - However, classifying tan as `brown` produces zero surprise to a human investigator (a "tan car" and a "light brown car" are linguistically interchangeable in witness testimonies).
6. **Recommendation:** Map `tan` $\rightarrow$ **`brown`**.

---

## 4. Comparison of Candidate Mapping Strategies

| VCoR Class | Strategy 1: Registry-Aligned (Recommended) | Strategy 2: Conservative Evidentiary | Strategy 3: Strict 10 + Other |
|---|:---:|:---:|:---:|
| **black** | `black` | `black` | `black` |
| **blue** | `blue` | `blue` | `blue` |
| **brown** | `brown` | `brown` | `brown` |
| **green** | `green` | `green` | `green` |
| **grey** | `grey` | `grey` | `grey` |
| **orange** | `orange` | `orange` | `orange` |
| **red** | `red` | `red` | `red` |
| **silver** | `silver` | `silver` | `silver` |
| **white** | `white` | `white` | `white` |
| **yellow** | `yellow` | `yellow` | `yellow` |
| **beige** | `brown` *(or notes)* | `other` | `other` |
| **gold** | `yellow` | `other` | `other` |
| **pink** | `other` | `other` | `other` |
| **purple** | `other` | `other` | `other` |
| **tan** | `brown` | `brown` | `other` |
| **Effective Target Classes** | **11** (10 primary + `other`) | **11** (10 primary + `other`) | **11** (10 primary + `other`) |
| **Samples Mapped to `other`** | 1,454 (14.0%) | 2,355 (22.7%) | 2,926 (28.2%) |
| **Registry Interoperability** | **High** (matches RTO/DMV rules) | **Moderate** | **Low** |
| **Human Investigator Trust** | **High** (tan$\rightarrow$brown, rare$\rightarrow$other) | **Highest** (zero forced mappings) | **Moderate** (too many vehicles become 'other') |

### Analysis of Trade-offs:
- **Strategy 1 (Registry-Aligned):** Maps `tan` and `beige` to `brown`, `gold` to `yellow`, and leaves `pink` and `purple` as `other`. This maximizes coverage over official vehicle databases where "gold" cars are registered as yellow and "tan" cars are registered as brown.
- **Strategy 2 (Conservative Evidentiary - Strongly Recommended):** Maps only `tan` to `brown`. Leaves `beige`, `gold`, `pink`, and `purple` as `other`. This preserves highest investigator credibility: an investigator reading a report will never see a beige luxury sedan labelled "BROWN" or a gold metallic car labelled "YELLOW".
- **Strategy 3 (Strict 10 + Other):** Maps all 5 non-standard classes directly to `other`. This discards the clear physical relationship between tan and brown, sending nearly 28.2% of the VCoR dataset into `other`.

---

## 5. Decision Request

This proposal is submitted for user review. No production code in `tracevision/colour.py` has been modified.

**Questions for User Alignment:**
1. Do you prefer **Strategy 2 (Conservative Evidentiary)** where only `tan` maps to `brown` and `beige, gold, pink, purple` map to `other`, or **Strategy 1 (Registry-Aligned)**?
2. When training a classifier (Phase 3), should samples mapped to `other` be:
   - Trained as a dedicated 11th multiclass output (`other`), or
   - Retained as a 15-class fine-grained feature head with a runtime software mapping to the 12 TRACEVISION labels?

