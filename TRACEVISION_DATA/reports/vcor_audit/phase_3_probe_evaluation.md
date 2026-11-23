# TRACEVISION AI — Phase 3: Linear Probe Evaluation Report
**Date:** 2026-11-23 22:55:49  
**Backbone:** Frozen OpenCLIP `ViT-B/32` (OpenAI pretrained)  
**Classifier:** Class-Balanced Logistic Regression Head  
**Selected Hyperparameter:** `C = 100.0` (L2 regularization $\lambda = 0.0100$)  
**Inference Latency:** `0.0505 ms` per embedding on CPU  

---

## 1. Executive Summary & Benchmark Comparison

| Split | Metric | Zero-Shot CLIP Baseline | Frozen CLIP Linear Probe | Absolute Gain | Relative Improvement |
|---|---|:---:|:---:|:---:|:---:|
| **Validation** | Accuracy | 59.86% | 63.49% | +3.63% | +6.06% |
| **Validation** | Top-2 Accuracy | 68.16% | 77.50% | +9.34% | +13.70% |
| **Validation** | Macro F1 | 59.92% | 61.38% | +1.46% | +2.44% |
| **Validation** | Macro Precision | 54.12% | 63.13% | +9.01% | +16.65% |
| **Validation** | Macro Recall | 69.54% | 62.57% | +-6.97% | +-10.02% |
| **Test** | Accuracy | 60.06% | 60.78% | +0.72% | +1.20% |
| **Test** | Top-2 Accuracy | 67.38% | 74.89% | +7.51% | +11.15% |
| **Test** | Macro F1 | 59.70% | 58.91% | +-0.79% | +-1.32% |
| **Test** | Macro Precision | 53.83% | 60.77% | +6.94% | +12.89% |
| **Test** | Macro Recall | 69.47% | 59.65% | +-9.82% | +-14.14% |

> [!IMPORTANT]
> **Generalization Disclaimer:** Accuracy on VCoR evaluation splits reflects clean vehicle crops extracted from automotive classifieds and traffic cameras under good lighting. **VCoR accuracy does not equal CCTV accuracy.** Real-world CCTV footage features extreme low angles, high compression, severe motion blur, and non-uniform illumination.

---

## 2. Test Set Detailed Per-Class Breakdown

| Class | Support | Linear Probe Prec | Linear Probe Rec | Linear Probe F1 | Zero-Shot CLIP F1 | F1 Delta |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **black** | 85 | 49.02% | 58.82% | 53.48% | 62.31% | -8.83% |
| **blue** | 159 | 84.80% | 66.67% | 74.65% | 82.98% | -8.33% |
| **brown** | 207 | 49.11% | 53.14% | 51.04% | 58.92% | -7.88% |
| **green** | 120 | 96.97% | 80.00% | 87.67% | 88.19% | -0.52% |
| **grey** | 90 | 32.39% | 25.56% | 28.57% | 36.98% | -8.41% |
| **orange** | 114 | 85.58% | 78.07% | 81.65% | 82.20% | -0.55% |
| **other** | 351 | 74.81% | 55.84% | 63.95% | 0.00% | +63.95% |
| **red** | 135 | 87.38% | 66.67% | 75.63% | 78.47% | -2.84% |
| **silver** | 75 | 20.69% | 24.00% | 22.22% | 21.39% | +0.83% |
| **white** | 86 | 25.41% | 54.65% | 34.69% | 62.76% | -28.07% |
| **yellow** | 123 | 62.30% | 92.68% | 74.51% | 82.47% | -7.96% |

---

## 3. Test Set Confusion Matrix (Linear Probe)

```
             blac   blue   brow   gree   grey   oran   othe    red   silv   whit   yell
     black     50      1      3      0     11      0      3      0      8      7      2
      blue      3    106      5      0      1      1     15      0      4     11     13
     brown     10      2    110      1     10      7     20      0     15     24      8
     green      1      4      8     96      1      0      3      0      2      4      1
      grey     15      1      5      0     23      0      8      0     14     20      4
    orange      0      2      2      0      0     89      2      6      1      5      7
     other      5      7     70      1      8      2    196      7      9     21     25
       red      0      0      6      0      0      4      8     90      5     14      8
    silver      8      0      7      0     10      0      3      0     18     29      0
     white     10      1      6      0      7      0      3      0     11     47      1
    yellow      0      1      2      1      0      1      1      0      0      3    114
```

---

## 4. Test Set Confusion Matrix (Zero-Shot CLIP Baseline)

```
             blac   blue   brow   gree   grey   oran   othe    red   silv   whit   yell
     black     62      3      0      0     12      0      0      1      7      0      0
      blue      1    156      0      0      0      0      0      0      2      0      0
     brown      6      0    104      7     37      9      0      1     14     22      7
     green      1      4      0    112      0      0      0      0      0      1      2
      grey     11      3      1      1     49      0      0      0     20      5      0
    orange      0      0      0      0      0     97      0     15      0      0      2
     other     30     50     41     10     42     13      0     54     43     32     36
       red      0      0      0      1      0      1      0    133      0      0      0
    silver      3      1      0      0     32      0      0      0     20     18      1
     white      0      0      0      2      3      0      0      0      6     75      0
    yellow      0      0      0      1      0      2      0      0      0      0    120
```
