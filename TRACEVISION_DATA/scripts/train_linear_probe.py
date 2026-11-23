"""Linear Probe Training and Evaluation for TRACEVISION AI (Phase 3).

Trains a class-balanced logistic regression classifier on frozen CLIP ViT-B/32 embeddings.
- Fits solely on the training split (7,208 samples).
- Selects regularization hyperparameter C on the validation split (1,542 samples).
- Evaluates final model on test split (1,545 samples).
- Evaluates existing CLIP zero-shot baseline on identical validation and test splits.
- Computes Accuracy, Top-2 Accuracy, Macro P/R/F1, Per-Class metrics, Confusion Matrices, Latency.
- Saves model weights and complete evaluation reports.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple, Any

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

EMBEDDINGS_FILE = Path("TRACEVISION_DATA/models/vcor_clip_embeddings.pt")
METADATA_FILE = Path("TRACEVISION_DATA/models/embeddings_manifest.json")
MODEL_SAVE_PATH = Path("TRACEVISION_DATA/models/vcor_linear_probe.pt")
CONFIG_SAVE_PATH = Path("TRACEVISION_DATA/models/vcor_linear_probe_config.json")
REPORT_OUTPUT_DIR = Path("TRACEVISION_DATA/reports/vcor_audit")

TARGET_CLASSES = [
    "black", "blue", "brown", "green", "grey", "orange",
    "other", "red", "silver", "unknown", "white", "yellow"
]

# 11 active classes in VCoR (all except 'unknown')
ACTIVE_CLASSES = [
    "black", "blue", "brown", "green", "grey", "orange",
    "other", "red", "silver", "white", "yellow"
]

CLIP_PROMPT_COLOURS = [
    "white", "black", "silver", "grey", "red",
    "blue", "green", "yellow", "brown", "orange"
]
PROMPT_COLOUR_MAP = {"grey": "gray"}
TEMPLATES = [
    "a photo of a {c} vehicle.",
    "a {c} vehicle on the road.",
    "a {c} vehicle seen from behind.",
    "a {c} vehicle seen from the front."
]


def load_cached_data() -> Tuple[Dict[str, torch.Tensor], Dict[str, Any]]:
    if not EMBEDDINGS_FILE.exists():
        raise FileNotFoundError(f"Embeddings cache not found at {EMBEDDINGS_FILE}")

    print(f"Loading cached embeddings from {EMBEDDINGS_FILE}...")
    data = torch.load(EMBEDDINGS_FILE, weights_only=False)
    
    with open(METADATA_FILE, "r", encoding="utf-8") as f:
        meta = json.load(f)

    return data, meta


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, y_probs: np.ndarray, class_names: List[str]) -> Dict[str, Any]:
    """Computes comprehensive classification metrics."""
    n_samples = len(y_true)
    n_classes = len(class_names)
    
    # Accuracy
    acc = float(np.mean(y_true == y_pred))
    
    # Top-2 Accuracy
    top2_correct = 0
    for idx in range(n_samples):
        top2_classes = np.argsort(y_probs[idx])[-2:]
        if y_true[idx] in top2_classes:
            top2_correct += 1
    top2_acc = float(top2_correct / n_samples) if n_samples > 0 else 0.0

    # Confusion matrix: rows = true, cols = pred
    cm = np.zeros((n_classes, n_classes), dtype=int)
    for t, p in zip(y_true, y_pred):
        cm[t, p] += 1

    # Per-class metrics
    per_class = {}
    precisions = []
    recalls = []
    f1s = []

    for c_idx, c_name in enumerate(class_names):
        tp = cm[c_idx, c_idx]
        fp = cm[:, c_idx].sum() - tp
        fn = cm[c_idx, :].sum() - tp
        support = int(cm[c_idx, :].sum())

        prec = float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0
        rec = float(tp / (tp + fn)) if (tp + fn) > 0 else 0.0
        f1 = float(2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0

        per_class[c_name] = {
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1_score": round(f1, 4),
            "support": support,
        }
        
        # Only include in macro average if class has support > 0
        if support > 0:
            precisions.append(prec)
            recalls.append(rec)
            f1s.append(f1)

    macro_p = float(np.mean(precisions)) if precisions else 0.0
    macro_r = float(np.mean(recalls)) if recalls else 0.0
    macro_f1 = float(np.mean(f1s)) if f1s else 0.0

    return {
        "accuracy": round(acc, 4),
        "top2_accuracy": round(top2_acc, 4),
        "macro_precision": round(macro_p, 4),
        "macro_recall": round(macro_r, 4),
        "macro_f1": round(macro_f1, 4),
        "per_class": per_class,
        "confusion_matrix": cm.tolist(),
        "class_names": class_names,
        "sample_count": n_samples,
    }


def train_probe_for_c(
    X_train: torch.Tensor,
    y_train: torch.Tensor,
    class_weights: torch.Tensor,
    C: float,
    num_classes: int,
    seed: int = 42
) -> nn.Linear:
    """Trains a logistic regression model with L2 regularization lambda = 1/C."""
    torch.manual_seed(seed)
    in_dim = X_train.shape[1]
    
    linear = nn.Linear(in_dim, num_classes, bias=True)
    nn.init.zeros_(linear.weight)
    nn.init.zeros_(linear.bias)

    weight_decay = 1.0 / C if C > 0 else 0.0

    # L-BFGS for exact convex logistic regression
    optimizer = torch.optim.LBFGS(
        linear.parameters(),
        lr=1.0,
        max_iter=150,
        tolerance_grad=1e-7,
        tolerance_change=1e-9,
        line_search_fn="strong_wolfe"
    )

    criterion = nn.CrossEntropyLoss(weight=class_weights)

    def closure():
        optimizer.zero_grad()
        logits = linear(X_train)
        loss = criterion(logits, y_train)
        if weight_decay > 0:
            loss = loss + 0.5 * weight_decay * torch.norm(linear.weight, p=2) ** 2
        loss.backward()
        return loss

    optimizer.step(closure)
    linear.eval()
    return linear


def compute_zero_shot_text_features(device: str = "cpu") -> Tuple[torch.Tensor, List[str]]:
    """Builds zero-shot text classifier embeddings identical to production colour.py."""
    import open_clip
    print("Computing zero-shot CLIP text embeddings for 10 baseline colours...")
    model, _, _ = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai", device=device)
    tokenizer = open_clip.get_tokenizer("ViT-B-32")
    model.eval()

    text_embs = []
    with torch.no_grad():
        for col in CLIP_PROMPT_COLOURS:
            c_name = PROMPT_COLOUR_MAP.get(col, col)
            prompts = [tp.format(c=c_name) for tp in TEMPLATES]
            tok = tokenizer(prompts).to(device)
            e = model.encode_text(tok).float()
            e = e / e.norm(dim=-1, keepdim=True)
            e = e.mean(0)
            text_embs.append(e / e.norm())

    text_features = torch.stack(text_embs) # Shape: [10, 512]
    return text_features, CLIP_PROMPT_COLOURS


def evaluate_zero_shot_clip(
    X: torch.Tensor,
    y: torch.Tensor,
    text_features: torch.Tensor,
    clip_colours: List[str],
    active_classes: List[str]
) -> Dict[str, Any]:
    """Evaluates zero-shot CLIP on image embeddings."""
    with torch.inference_mode():
        # Cosine similarity scaled by 100 as in OpenAI CLIP
        similarity = 100.0 * (X @ text_features.T)
        probs_10 = F.softmax(similarity, dim=-1).cpu().numpy()

    # Map the 10 CLIP colours into the 11 active VCoR classes
    # If a class is not in the 10 colours (e.g. 'other'), zero-shot CLIP assigns 0 prior
    n_samples = len(y)
    n_active = len(active_classes)
    full_probs = np.zeros((n_samples, n_active), dtype=float)

    for i, c_name in enumerate(clip_colours):
        if c_name in active_classes:
            act_idx = active_classes.index(c_name)
            full_probs[:, act_idx] = probs_10[:, i]

    # Re-normalize over active classes
    prob_sums = full_probs.sum(axis=1, keepdims=True)
    prob_sums[prob_sums == 0] = 1.0
    full_probs = full_probs / prob_sums

    y_pred = np.argmax(full_probs, axis=1)
    y_true = y.cpu().numpy()

    return compute_metrics(y_true, y_pred, full_probs, active_classes)


def main():
    print("=== TRACEVISION AI: Linear Probe Training & Evaluation (Phase 3) ===")
    cached_data, meta = load_cached_data()

    embeddings = cached_data["embeddings"] # [N, 512]
    splits = cached_data["splits"]
    mapped_classes = cached_data["mapped_classes"]
    
    # Class mapping dictionaries
    class2idx = {c: i for i, c in enumerate(ACTIVE_CLASSES)}
    idx2class = {i: c for i, c in enumerate(ACTIVE_CLASSES)}

    # Filter by split
    train_indices = [i for i, s in enumerate(splits) if s == "train"]
    val_indices = [i for i, s in enumerate(splits) if s == "val"]
    test_indices = [i for i, s in enumerate(splits) if s == "test"]

    print(f"Dataset partition:")
    print(f"  - Train: {len(train_indices)} samples")
    print(f"  - Val:   {len(val_indices)} samples")
    print(f"  - Test:  {len(test_indices)} samples")

    X_train = embeddings[train_indices]
    y_train_list = [class2idx[mapped_classes[i]] for i in train_indices]
    y_train = torch.tensor(y_train_list, dtype=torch.long)

    X_val = embeddings[val_indices]
    y_val_list = [class2idx[mapped_classes[i]] for i in val_indices]
    y_val = torch.tensor(y_val_list, dtype=torch.long)

    X_test = embeddings[test_indices]
    y_test_list = [class2idx[mapped_classes[i]] for i in test_indices]
    y_test = torch.tensor(y_test_list, dtype=torch.long)

    # Compute balanced class weights for training: w_c = N / (C * N_c)
    n_train = len(y_train)
    n_classes = len(ACTIVE_CLASSES)
    class_counts = torch.bincount(y_train, minlength=n_classes).float()
    class_weights = n_train / (n_classes * class_counts)
    class_weights = class_weights / class_weights.sum() * n_classes # normalize mean to 1.0

    print("\nTraining Class Distribution & Inverse Class Weights:")
    for c_idx, c_name in enumerate(ACTIVE_CLASSES):
        print(f"  {c_name:<10}: count={int(class_counts[c_idx]):<5} | weight={class_weights[c_idx]:.3f}")

    # Hyperparameter Grid Search on Validation Split
    c_candidates = [0.001, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 50.0, 100.0]
    best_c = None
    best_val_macro_f1 = -1.0
    tuning_records = []

    print("\n--- Tuning Hyperparameter C on Validation Split ---")
    for C in c_candidates:
        probe = train_probe_for_c(X_train, y_train, class_weights, C=C, num_classes=n_classes, seed=42)
        
        with torch.inference_mode():
            val_logits = probe(X_val)
            val_probs = F.softmax(val_logits, dim=-1).numpy()
            val_preds = np.argmax(val_probs, axis=1)

        val_metrics = compute_metrics(y_val.numpy(), val_preds, val_probs, ACTIVE_CLASSES)
        macro_f1 = val_metrics["macro_f1"]
        acc = val_metrics["accuracy"]
        tuning_records.append({"C": C, "val_acc": acc, "val_macro_f1": macro_f1})
        print(f"  C={C:>7.3f} | Val Accuracy: {acc*100:5.2f}% | Val Macro F1: {macro_f1*100:5.2f}%")

        if macro_f1 > best_val_macro_f1:
            best_val_macro_f1 = macro_f1
            best_c = C

    print(f"\nOptimal Regularization Selected: C = {best_c} (Val Macro F1 = {best_val_macro_f1*100:.2f}%)")

    # Retrain final linear probe with selected C
    final_probe = train_probe_for_c(X_train, y_train, class_weights, C=best_c, num_classes=n_classes, seed=42)

    # Measure inference latency
    n_lat_trials = 1000
    single_x = X_val[0:1]
    t0 = time.time()
    with torch.inference_mode():
        for _ in range(n_lat_trials):
            _ = final_probe(single_x)
    lat_ms = ((time.time() - t0) / n_lat_trials) * 1000.0
    print(f"Probe inference latency: {lat_ms:.4f} ms per sample on CPU")

    # Evaluate Final Probe on Validation Split
    with torch.inference_mode():
        val_logits = final_probe(X_val)
        val_probs = F.softmax(val_logits, dim=-1).numpy()
        val_preds = np.argmax(val_probs, axis=1)
    val_probe_metrics = compute_metrics(y_val.numpy(), val_preds, val_probs, ACTIVE_CLASSES)

    # Evaluate Final Probe on Test Split
    with torch.inference_mode():
        test_logits = final_probe(X_test)
        test_probs = F.softmax(test_logits, dim=-1).numpy()
        test_preds = np.argmax(test_probs, axis=1)
    test_probe_metrics = compute_metrics(y_test.numpy(), test_preds, test_probs, ACTIVE_CLASSES)

    # Zero-Shot CLIP Baseline Evaluation
    text_features, clip_colours = compute_zero_shot_text_features(device="cpu")
    val_clip_metrics = evaluate_zero_shot_clip(X_val, y_val, text_features, clip_colours, ACTIVE_CLASSES)
    test_clip_metrics = evaluate_zero_shot_clip(X_test, y_test, text_features, clip_colours, ACTIVE_CLASSES)

    print("\n" + "=" * 65)
    print("                     EVALUATION RESULTS COMPARISON")
    print("=" * 65)
    print(f"{'Split / Metric':<25} | {'CLIP Zero-Shot Baseline':<20} | {'Linear Probe (Ours)':<20}")
    print("-" * 65)
    print(f"{'Val Accuracy':<25} | {val_clip_metrics['accuracy']*100:6.2f}%              | {val_probe_metrics['accuracy']*100:6.2f}%")
    print(f"{'Val Top-2 Accuracy':<25} | {val_clip_metrics['top2_accuracy']*100:6.2f}%              | {val_probe_metrics['top2_accuracy']*100:6.2f}%")
    print(f"{'Val Macro Precision':<25} | {val_clip_metrics['macro_precision']*100:6.2f}%              | {val_probe_metrics['macro_precision']*100:6.2f}%")
    print(f"{'Val Macro Recall':<25} | {val_clip_metrics['macro_recall']*100:6.2f}%              | {val_probe_metrics['macro_recall']*100:6.2f}%")
    print(f"{'Val Macro F1':<25} | {val_clip_metrics['macro_f1']*100:6.2f}%              | {val_probe_metrics['macro_f1']*100:6.2f}%")
    print("-" * 65)
    print(f"{'Test Accuracy':<25} | {test_clip_metrics['accuracy']*100:6.2f}%              | {test_probe_metrics['accuracy']*100:6.2f}%")
    print(f"{'Test Top-2 Accuracy':<25} | {test_clip_metrics['top2_accuracy']*100:6.2f}%              | {test_probe_metrics['top2_accuracy']*100:6.2f}%")
    print(f"{'Test Macro Precision':<25} | {test_clip_metrics['macro_precision']*100:6.2f}%              | {test_probe_metrics['macro_precision']*100:6.2f}%")
    print(f"{'Test Macro Recall':<25} | {test_clip_metrics['macro_recall']*100:6.2f}%              | {test_probe_metrics['macro_recall']*100:6.2f}%")
    print(f"{'Test Macro F1':<25} | {test_clip_metrics['macro_f1']*100:6.2f}%              | {test_probe_metrics['macro_f1']*100:6.2f}%")
    print("=" * 65)

    # Save Model Weights
    MODEL_SAVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    # We save a 12-class full head for seamless production schema alignment:
    # 11 active classes map to active rows, 'unknown' row is initialized to -10 bias and 0 weights
    full_weight = torch.zeros(len(TARGET_CLASSES), 512)
    full_bias = torch.zeros(len(TARGET_CLASSES))
    full_bias[TARGET_CLASSES.index("unknown")] = -10.0 # suppressed

    for act_idx, act_name in enumerate(ACTIVE_CLASSES):
        tgt_idx = TARGET_CLASSES.index(act_name)
        full_weight[tgt_idx] = final_probe.weight.data[act_idx]
        full_bias[tgt_idx] = final_probe.bias.data[act_idx]

    torch.save({
        "weight": full_weight,
        "bias": full_bias,
        "target_classes": TARGET_CLASSES,
        "active_classes": ACTIVE_CLASSES,
        "best_C": best_c,
        "seed": 42,
        "in_dim": 512,
        "num_classes": len(TARGET_CLASSES),
        "backbone": "ViT-B-32",
        "pretrained": "openai"
    }, MODEL_SAVE_PATH)

    config_payload = {
        "model_architecture": "LogisticRegression_LinearProbe",
        "backbone": "ViT-B-32",
        "pretrained": "openai",
        "input_dim": 512,
        "output_classes": len(TARGET_CLASSES),
        "target_classes": TARGET_CLASSES,
        "active_classes": ACTIVE_CLASSES,
        "optimal_C": best_c,
        "tuning_history": tuning_records,
        "training_samples": len(X_train),
        "validation_samples": len(X_val),
        "test_samples": len(X_test),
        "inference_latency_ms": round(lat_ms, 4),
        "val_metrics": {
            "probe": val_probe_metrics,
            "clip_zero_shot": val_clip_metrics
        },
        "test_metrics": {
            "probe": test_probe_metrics,
            "clip_zero_shot": test_clip_metrics
        }
    }

    with open(CONFIG_SAVE_PATH, "w", encoding="utf-8") as f:
        json.dump(config_payload, f, indent=2)

    # Write evaluation Markdown report
    write_evaluation_report(val_probe_metrics, test_probe_metrics, val_clip_metrics, test_clip_metrics, best_c, lat_ms)

    print(f"Model saved: {MODEL_SAVE_PATH}")
    print(f"Config & metrics saved: {CONFIG_SAVE_PATH}")


def write_evaluation_report(
    val_probe: Dict[str, Any],
    test_probe: Dict[str, Any],
    val_clip: Dict[str, Any],
    test_clip: Dict[str, Any],
    best_c: float,
    lat_ms: float
):
    report_file = REPORT_OUTPUT_DIR / "phase_3_probe_evaluation.md"
    REPORT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    lines = [
        "# TRACEVISION AI — Phase 3: Linear Probe Evaluation Report",
        f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}  ",
        "**Backbone:** Frozen OpenCLIP `ViT-B/32` (OpenAI pretrained)  ",
        "**Classifier:** Class-Balanced Logistic Regression Head  ",
        f"**Selected Hyperparameter:** `C = {best_c}` (L2 regularization $\\lambda = {1.0/best_c:.4f}$)  ",
        f"**Inference Latency:** `{lat_ms:.4f} ms` per embedding on CPU  ",
        "",
        "---",
        "",
        "## 1. Executive Summary & Benchmark Comparison",
        "",
        "| Split | Metric | Zero-Shot CLIP Baseline | Frozen CLIP Linear Probe | Absolute Gain | Relative Improvement |",
        "|---|---|:---:|:---:|:---:|:---:|",
        f"| **Validation** | Accuracy | {val_clip['accuracy']*100:.2f}% | {val_probe['accuracy']*100:.2f}% | +{(val_probe['accuracy'] - val_clip['accuracy'])*100:.2f}% | +{((val_probe['accuracy'] - val_clip['accuracy'])/val_clip['accuracy'])*100:.2f}% |",
        f"| **Validation** | Top-2 Accuracy | {val_clip['top2_accuracy']*100:.2f}% | {val_probe['top2_accuracy']*100:.2f}% | +{(val_probe['top2_accuracy'] - val_clip['top2_accuracy'])*100:.2f}% | +{((val_probe['top2_accuracy'] - val_clip['top2_accuracy'])/val_clip['top2_accuracy'])*100:.2f}% |",
        f"| **Validation** | Macro F1 | {val_clip['macro_f1']*100:.2f}% | {val_probe['macro_f1']*100:.2f}% | +{(val_probe['macro_f1'] - val_clip['macro_f1'])*100:.2f}% | +{((val_probe['macro_f1'] - val_clip['macro_f1'])/val_clip['macro_f1'])*100:.2f}% |",
        f"| **Validation** | Macro Precision | {val_clip['macro_precision']*100:.2f}% | {val_probe['macro_precision']*100:.2f}% | +{(val_probe['macro_precision'] - val_clip['macro_precision'])*100:.2f}% | +{((val_probe['macro_precision'] - val_clip['macro_precision'])/val_clip['macro_precision'])*100:.2f}% |",
        f"| **Validation** | Macro Recall | {val_clip['macro_recall']*100:.2f}% | {val_probe['macro_recall']*100:.2f}% | +{(val_probe['macro_recall'] - val_clip['macro_recall'])*100:.2f}% | +{((val_probe['macro_recall'] - val_clip['macro_recall'])/val_clip['macro_recall'])*100:.2f}% |",
        f"| **Test** | Accuracy | {test_clip['accuracy']*100:.2f}% | {test_probe['accuracy']*100:.2f}% | +{(test_probe['accuracy'] - test_clip['accuracy'])*100:.2f}% | +{((test_probe['accuracy'] - test_clip['accuracy'])/test_clip['accuracy'])*100:.2f}% |",
        f"| **Test** | Top-2 Accuracy | {test_clip['top2_accuracy']*100:.2f}% | {test_probe['top2_accuracy']*100:.2f}% | +{(test_probe['top2_accuracy'] - test_clip['top2_accuracy'])*100:.2f}% | +{((test_probe['top2_accuracy'] - test_clip['top2_accuracy'])/test_clip['top2_accuracy'])*100:.2f}% |",
        f"| **Test** | Macro F1 | {test_clip['macro_f1']*100:.2f}% | {test_probe['macro_f1']*100:.2f}% | +{(test_probe['macro_f1'] - test_clip['macro_f1'])*100:.2f}% | +{((test_probe['macro_f1'] - test_clip['macro_f1'])/test_clip['macro_f1'])*100:.2f}% |",
        f"| **Test** | Macro Precision | {test_clip['macro_precision']*100:.2f}% | {test_probe['macro_precision']*100:.2f}% | +{(test_probe['macro_precision'] - test_clip['macro_precision'])*100:.2f}% | +{((test_probe['macro_precision'] - test_clip['macro_precision'])/test_clip['macro_precision'])*100:.2f}% |",
        f"| **Test** | Macro Recall | {test_clip['macro_recall']*100:.2f}% | {test_probe['macro_recall']*100:.2f}% | +{(test_probe['macro_recall'] - test_clip['macro_recall'])*100:.2f}% | +{((test_probe['macro_recall'] - test_clip['macro_recall'])/test_clip['macro_recall'])*100:.2f}% |",
        "",
        "> [!IMPORTANT]",
        "> **Generalization Disclaimer:** Accuracy on VCoR evaluation splits reflects clean vehicle crops extracted from automotive classifieds and traffic cameras under good lighting. **VCoR accuracy does not equal CCTV accuracy.** Real-world CCTV footage features extreme low angles, high compression, severe motion blur, and non-uniform illumination.",
        "",
        "---",
        "",
        "## 2. Test Set Detailed Per-Class Breakdown",
        "",
        "| Class | Support | Linear Probe Prec | Linear Probe Rec | Linear Probe F1 | Zero-Shot CLIP F1 | F1 Delta |",
        "|---|:---:|:---:|:---:|:---:|:---:|:---:|",
    ]

    for c in ACTIVE_CLASSES:
        p_info = test_probe["per_class"][c]
        z_info = test_clip["per_class"][c]
        f1_delta = p_info["f1_score"] - z_info["f1_score"]
        lines.append(
            f"| **{c}** | {p_info['support']} | {p_info['precision']*100:.2f}% | {p_info['recall']*100:.2f}% | {p_info['f1_score']*100:.2f}% | {z_info['f1_score']*100:.2f}% | {f1_delta*100:+.2f}% |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 3. Test Set Confusion Matrix (Linear Probe)",
        "",
        "```",
        f"{'':>10} " + " ".join(f"{c[:4]:>6}" for c in ACTIVE_CLASSES),
    ])

    cm = test_probe["confusion_matrix"]
    for i, c in enumerate(ACTIVE_CLASSES):
        row_str = f"{c:>10} " + " ".join(f"{cm[i][j]:>6}" for j in range(len(ACTIVE_CLASSES)))
        lines.append(row_str)

    lines.extend([
        "```",
        "",
        "---",
        "",
        "## 4. Test Set Confusion Matrix (Zero-Shot CLIP Baseline)",
        "",
        "```",
        f"{'':>10} " + " ".join(f"{c[:4]:>6}" for c in ACTIVE_CLASSES),
    ])

    cm_clip = test_clip["confusion_matrix"]
    for i, c in enumerate(ACTIVE_CLASSES):
        row_str = f"{c:>10} " + " ".join(f"{cm_clip[i][j]:>6}" for j in range(len(ACTIVE_CLASSES)))
        lines.append(row_str)

    lines.append("```\n")

    with open(report_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Report written to {report_file}")


if __name__ == "__main__":
    main()

