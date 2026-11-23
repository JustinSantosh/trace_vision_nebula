"""VCoR colour linear probe, v2 (final Claude audit, 2026-11-23).

Why a v2: the v1 probe (train_linear_probe.py) is under-fit. Its loss is mean cross-entropy + 0.5 * (1/C) * ||W||^2,
i.e. a penalty N (=7,208) times stronger than the usual (scikit-learn) convention 0.5 * ||W||^2 + C * sum(CE).
On unit-norm CLIP features this keeps every class weight row at norm ~1.3, so all logits sit within ~0.2 of each
other and the per-class bias decides most predictions (the 'other' bias +0.18 wins on CCTV crops: 37/62 'other').
Validation accuracy was still climbing at the top of the v1 C grid (C=100), which is the textbook sign.

v2, same data and the same splits, nothing else changed:
  * features standardised with TRAIN-split mean/std (folded back into W and b when saving, so the checkpoint keeps
    v1's format {weight, bias, target_classes} and tracevision/colour.py needs no change)
  * penalty in the standard convention: mean CE + 0.5 / (C * N_train) * ||W||^2
  * L-BFGS run to convergence (repeated steps until the loss stops changing), not a single 150-iteration call
  * C chosen on the VALIDATION split only (macro-F1), from a wider grid; TEST split evaluated once, at the end
  * the 19 labelled CCTV clips are NOT used here at all

Writes (never overwrites v1):
  TRACEVISION_DATA/models/vcor_linear_probe_v2.pt
  TRACEVISION_DATA/models/vcor_linear_probe_v2_config.json
  TRACEVISION_DATA/reports/final_claude_audit/vcor_probe_v2_evaluation.md

    .venv/Scripts/python.exe TRACEVISION_DATA/scripts/train_linear_probe_v2.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_linear_probe import (ACTIVE_CLASSES, TARGET_CLASSES, compute_metrics,  # noqa: E402
                                compute_zero_shot_text_features, evaluate_zero_shot_clip)

EMB = ROOT / "TRACEVISION_DATA/models/vcor_clip_embeddings.pt"
OUT_PT = ROOT / "TRACEVISION_DATA/models/vcor_linear_probe_v2.pt"
OUT_CFG = ROOT / "TRACEVISION_DATA/models/vcor_linear_probe_v2_config.json"
OUT_MD = ROOT / "TRACEVISION_DATA/reports/final_claude_audit/vcor_probe_v2_evaluation.md"
GRID = [0.001, 0.003, 0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0]
SEED = 42


def fit(X, y, w_cls, C, n_cls, max_rounds=60):
    torch.manual_seed(SEED)
    W = torch.zeros(n_cls, X.shape[1], requires_grad=True)
    b = torch.zeros(n_cls, requires_grad=True)
    lam = 1.0 / (C * len(X))
    opt = torch.optim.LBFGS([W, b], lr=1.0, max_iter=200, history_size=20, tolerance_grad=1e-6,
                            tolerance_change=1e-10, line_search_fn="strong_wolfe")

    def closure():
        opt.zero_grad()
        loss = F.cross_entropy(X @ W.T + b, y, weight=w_cls) + 0.5 * lam * (W * W).sum()
        loss.backward()
        return loss

    prev = None
    for _ in range(max_rounds):
        loss = float(opt.step(closure))
        if prev is not None and abs(prev - loss) < 1e-7:
            break
        prev = loss
    return W.detach(), b.detach(), loss


def evaluate(W, b, X, y):
    with torch.inference_mode():
        p = F.softmax(X @ W.T + b, dim=-1).numpy()
    return compute_metrics(y.numpy(), p.argmax(1), p, ACTIVE_CLASSES)


def main():
    t_start = time.time()
    d = torch.load(EMB, weights_only=False)
    E, splits, mapped = d["embeddings"].float(), d["splits"], d["mapped_classes"]
    c2i = {c: i for i, c in enumerate(ACTIVE_CLASSES)}
    idx = {s: [i for i, x in enumerate(splits) if x == s] for s in ("train", "val", "test")}
    X = {s: E[v] for s, v in idx.items()}
    Y = {s: torch.tensor([c2i[mapped[i]] for i in v]) for s, v in idx.items()}

    mu, sd = X["train"].mean(0), X["train"].std(0).clamp_min(1e-6)       # TRAIN statistics only
    Z = {s: (x - mu) / sd for s, x in X.items()}

    n, k = len(Y["train"]), len(ACTIVE_CLASSES)
    counts = torch.bincount(Y["train"], minlength=k).float()
    w_cls = n / (k * counts)
    w_cls = w_cls / w_cls.mean()

    history, best = [], None
    for C in GRID:
        W, b, loss = fit(Z["train"], Y["train"], w_cls, C, k)
        m = evaluate(W, b, Z["val"], Y["val"])
        tr = evaluate(W, b, Z["train"], Y["train"])
        history.append({"C": C, "train_acc": tr["accuracy"], "val_acc": m["accuracy"], "val_macro_f1": m["macro_f1"],
                        "final_loss": round(loss, 5), "weight_row_norm_mean": round(float((W / sd).norm(dim=1).mean()), 2)})
        print(f"C={C:<7} train_acc={tr['accuracy']:.4f} val_acc={m['accuracy']:.4f} val_f1={m['macro_f1']:.4f}")
        if best is None or m["macro_f1"] > best[0]:
            best = (m["macro_f1"], C, W, b)

    _, C, W, b = best
    val = evaluate(W, b, Z["val"], Y["val"])
    test = evaluate(W, b, Z["test"], Y["test"])                         # evaluated once, after selection

    # fold the standardisation into the head: logits = ((x - mu)/sd) W^T + b = x (W/sd)^T + (b - (mu/sd) W^T)
    Wf = W / sd
    bf = b - (mu / sd) @ W.T
    full_W = torch.zeros(len(TARGET_CLASSES), E.shape[1])
    full_b = torch.zeros(len(TARGET_CLASSES))
    full_b[TARGET_CLASSES.index("unknown")] = -1e4                      # never predicted by the head itself
    for a, name in enumerate(ACTIVE_CLASSES):
        full_W[TARGET_CLASSES.index(name)] = Wf[a]
        full_b[TARGET_CLASSES.index(name)] = bf[a]
    # sanity: folded head on raw features == standardised head
    with torch.inference_mode():
        a1 = (Z["val"] @ W.T + b).argmax(1)
        a2 = (X["val"] @ full_W.T + full_b).argmax(1)
        a2 = torch.tensor([ACTIVE_CLASSES.index(TARGET_CLASSES[int(i)]) for i in a2])
    assert bool((a1 == a2).all()), "folded head disagrees with the standardised head"

    torch.save({"weight": full_W, "bias": full_b, "target_classes": TARGET_CLASSES, "active_classes": ACTIVE_CLASSES,
                "best_C": C, "seed": SEED, "in_dim": int(E.shape[1]), "num_classes": len(TARGET_CLASSES),
                "backbone": "ViT-B-32", "pretrained": "openai", "version": 2,
                "note": "features standardised with train statistics, folded into weight/bias"}, OUT_PT)

    text, cols = compute_zero_shot_text_features(device="cpu")
    zs_val = evaluate_zero_shot_clip(X["val"], Y["val"], text, cols, ACTIVE_CLASSES)
    zs_test = evaluate_zero_shot_clip(X["test"], Y["test"], text, cols, ACTIVE_CLASSES)
    v1 = json.loads((ROOT / "TRACEVISION_DATA/models/vcor_linear_probe_config.json").read_text(encoding="utf-8"))

    cfg = {"model_architecture": "LogisticRegression_LinearProbe_v2", "backbone": "ViT-B-32", "pretrained": "openai",
           "target_classes": TARGET_CLASSES, "active_classes": ACTIVE_CLASSES, "optimal_C": C,
           "regularisation": "mean CE + 0.5/(C*N_train)*||W||^2 on train-standardised features",
           "selection": "validation macro-F1", "tuning_history": history,
           "training_samples": len(idx["train"]), "validation_samples": len(idx["val"]), "test_samples": len(idx["test"]),
           "val_metrics": {"probe_v2": val, "clip_zero_shot": zs_val, "probe_v1": v1["val_metrics"]["probe"]},
           "test_metrics": {"probe_v2": test, "clip_zero_shot": zs_test, "probe_v1": v1["test_metrics"]["probe"]},
           "runtime_s": round(time.time() - t_start, 1)}
    OUT_CFG.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    def row(name, m):
        return f"| {name} | {m['accuracy']*100:.2f}% | {m['top2_accuracy']*100:.2f}% | {m['macro_f1']*100:.2f}% |"
    lines = ["# VCoR colour probe v2: evaluation", "",
             f"Generated by `TRACEVISION_DATA/scripts/train_linear_probe_v2.py` on {time.strftime('%Y-%m-%d %H:%M')}.",
             f"C selected on the validation split (macro-F1): **C = {C}**. Test split evaluated once after selection.", "",
             "## Validation split (1,542 VCoR crops)", "", "| Model | Accuracy | Top-2 | Macro F1 |", "|---|---|---|---|",
             row("CLIP zero-shot (10 colours, no 'other')", zs_val), row("Probe v1 (shipped, under-fit)", v1["val_metrics"]["probe"]),
             row("**Probe v2**", val), "", "## Test split (1,545 VCoR crops)", "",
             "| Model | Accuracy | Top-2 | Macro F1 |", "|---|---|---|---|",
             row("CLIP zero-shot (10 colours, no 'other')", zs_test), row("Probe v1 (shipped, under-fit)", v1["test_metrics"]["probe"]),
             row("**Probe v2**", test), "", "## C grid (validation)", "", "| C | train acc | val acc | val macro-F1 | mean weight-row norm (raw-feature scale) |",
             "|---|---|---|---|---|"]
    lines += [f"| {h['C']} | {h['train_acc']:.4f} | {h['val_acc']:.4f} | {h['val_macro_f1']:.4f} | {h['weight_row_norm_mean']} |" for h in history]
    lines += ["", "## Test per-class (probe v2)", "", "| Class | Support | Precision | Recall | F1 |", "|---|---|---|---|---|"]
    lines += [f"| {c} | {m['support']} | {m['precision']:.3f} | {m['recall']:.3f} | {m['f1_score']:.3f} |" for c, m in test["per_class"].items()]
    lines += ["", "## Test confusion matrix (probe v2; rows = truth)", "", "```",
              f"{'':>8} " + " ".join(f"{c[:5]:>6}" for c in ACTIVE_CLASSES)]
    lines += [f"{c:>8} " + " ".join(f"{v:>6}" for v in r) for c, r in zip(ACTIVE_CLASSES, test["confusion_matrix"])]
    lines += ["```", "", "VCoR accuracy is not CCTV accuracy: see `model_accuracy_audit.md` for the separate CCTV transfer check."]
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"best C={C} val_acc={val['accuracy']} test_acc={test['accuracy']} -> {OUT_PT.name}  ({time.time()-t_start:.0f}s)")


if __name__ == "__main__":
    main()
