#!/usr/bin/env python
"""Phase 0C - Awiros ANPR OCR feasibility check (evaluation only; nothing is trained or tuned).

Measures, on CPU by default:
  * per-image latency (preprocess + forward + decode), after a warm-up
  * per-character probabilities from the CTC head (needed for multi-frame recovery),
    with the top-3 alternative characters at each emitted position
  * CER and exact-plate accuracy against ground_truth.csv (from build_ocr_eval_set.py)

Preprocessing (--preprocess):
  paddle   (default) resize to height 48 keeping aspect, normalise to [-1,1], THEN zero-pad
           to width 320 (= PaddleOCR's resize_norm_img). Use this.
  official Awiros test.py: zero-pads with black pixels BEFORE normalising (pad value -1).
           Kept only for comparison - it drops characters (see reports/awiros_feasibility.md).

Inputs
  --gt           ground_truth.csv (filename relative to its folder, normalised_label, ...)
  --awiros-dir   folder with model.safetensors, en_dict.txt, test.py (from HF Awiros/anpr-ocr)
  --paddleocr-dir PaddleOCR clone (provides ppocr for model construction)
Outputs (in --out)
  predictions.csv     one row per crop: prediction, CER, exact, mean/min char prob, latency
  char_probs.jsonl    per crop: emitted chars, their probabilities, top-3 alternatives
  metrics.json        overall + by format_status / layout_guess / crop height bucket

Usage
  python TRACEVISION_DATA/scripts/awiros_feasibility_check.py --gt TRACEVISION_DATA/processed/ocr_evaluation/zenitsu09/ground_truth.csv --out TRACEVISION_DATA/processed/ocr_evaluation/zenitsu09/awiros_run --sample 20
  python TRACEVISION_DATA/scripts/awiros_feasibility_check.py --gt ... --out ... --primary-only      # full benchmark
"""
from __future__ import annotations

import argparse
import json
import math
import platform
import random
import statistics
import sys
import time
from pathlib import Path

try:
    import cv2
    import numpy as np
    import pandas as pd
    from rapidfuzz.distance import Levenshtein
except ImportError as e:
    sys.exit(f"missing dependency: {e}")

ROOT = Path(__file__).resolve().parents[2]  # E:\hack_a_sol


def load_model(awiros_dir: Path, paddleocr_dir: Path, device: str):
    sys.path.insert(0, str(paddleocr_dir))
    sys.path.insert(0, str(awiros_dir))
    import paddle
    import test as awt  # Awiros release script: MODEL_CONFIG + safetensors loader (main() is not run)
    from ppocr.modeling.architectures import build_model

    paddle.set_device(device)
    model = build_model(awt.MODEL_CONFIG["Architecture"])
    model.eval()
    model.set_state_dict(awt.load_safetensors_to_paddle(paddle, str(awiros_dir / "model.safetensors")))
    # CTC class order used by PaddleOCR CTCLabelDecode: blank, dict chars, space
    chars = ["<blank>"] + [l.rstrip("\n") for l in open(awiros_dir / "en_dict.txt", encoding="utf-8")] + [" "]
    return paddle, model, chars, awt


def prep_paddle(img, W=320, H=48):
    h, w = img.shape[:2]
    nw = min(W, int(math.ceil(H * w / h)))
    r = cv2.resize(img, (nw, H)).astype("float32").transpose(2, 0, 1) / 255.0
    r = (r - 0.5) / 0.5
    out = np.zeros((3, H, W), dtype="float32")
    out[:, :, :nw] = r
    return out


def ctc_decode(prob, chars):
    """Greedy CTC decode keeping per-character probability and top-3 alternatives."""
    idx = prob.argmax(1)
    keep = np.ones(len(idx), bool)
    keep[1:] = idx[1:] != idx[:-1]
    keep &= idx != 0
    out = []
    for t in np.where(keep)[0]:
        top = np.argsort(-prob[t])[:3]
        out.append({"char": chars[idx[t]].upper(), "prob": round(float(prob[t, idx[t]]), 4), "t": int(t),
                    "top3": [[chars[k].upper() if k else "<blank>", round(float(prob[t, k]), 4)] for k in top]})
    out = [c for c in out if c["char"].strip()]
    return "".join(c["char"] for c in out), out


def height_bucket(h):
    return "<20px" if h < 20 else "20-39px" if h < 40 else ">=40px"


def summarise(df):
    def m(d):
        return {"n": int(len(d)), "exact_acc": round(float(d.exact.mean()), 4) if len(d) else None,
                "cer": round(float(d.edits.sum() / max(d.gt_len.sum(), 1)), 4) if len(d) else None,
                "empty_pred": int((d.prediction == "").sum())}
    res = {"overall": m(df), "standard_format_only": m(df[df.format_status != "nonstandard_review"])}
    for col in ["format_status", "layout_guess", "height_bucket"]:
        res["by_" + col] = {k: m(g) for k, g in df.groupby(col)}
    # is the confidence informative? accuracy by mean-char-prob band
    bands = pd.cut(df.mean_char_prob, [0, .5, .8, .9, .95, .99, 1.0001], right=False)
    res["acc_by_mean_char_prob"] = {str(k): m(g) for k, g in df.groupby(bands, observed=True)}
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gt", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--awiros-dir", default=str(ROOT / "TRACEVISION_DATA/models/awiros"))
    ap.add_argument("--paddleocr-dir", default=str(ROOT / "third_party/PaddleOCR"))
    ap.add_argument("--device", default="cpu", choices=["cpu", "gpu"])
    ap.add_argument("--preprocess", default="paddle", choices=["paddle", "official"])
    ap.add_argument("--sample", type=int, default=None, help="random sample of N rows (seeded) - smoke test")
    ap.add_argument("--primary-only", action="store_true", help="only rows with eval_primary==1 (unique plates)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--warmup", type=int, default=3)
    a = ap.parse_args()

    gt_path = Path(a.gt)
    df = pd.read_csv(gt_path, dtype={"normalised_label": str, "original_label": str})
    if a.primary_only:
        df = df[df.eval_primary == 1]
    if a.sample:
        df = df.sample(n=min(a.sample, len(df)), random_state=a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    paddle, model, chars, awt = load_model(Path(a.awiros_dir), Path(a.paddleocr_dir), a.device)
    load_s = time.perf_counter() - t0
    prep = prep_paddle if a.preprocess == "paddle" else (lambda im: awt.preprocess(im, awt.IMAGE_SHAPE))

    def infer(img):
        x = paddle.to_tensor(prep(img)[None])
        with paddle.no_grad():
            p = model(x)
        p = (p["ctc"] if isinstance(p, dict) else p).numpy()[0]
        return ctc_decode(p, chars)

    first = cv2.imread(str(gt_path.parent / df.iloc[0].filename))
    for _ in range(a.warmup):
        infer(first)

    rows = []
    with open(out / "char_probs.jsonl", "w", encoding="utf-8") as cj:
        for r in df.itertuples(index=False):
            img = cv2.imread(str(gt_path.parent / r.filename))
            if img is None:
                rows.append({"filename": r.filename, "error": "unreadable"})
                continue
            s = time.perf_counter()
            pred, cp = infer(img)
            ms = (time.perf_counter() - s) * 1000
            gt = str(r.normalised_label)
            ed = Levenshtein.distance(pred, gt)
            probs = [c["prob"] for c in cp]
            rows.append({"filename": r.filename, "gt": gt, "prediction": pred, "exact": int(pred == gt),
                         "edits": ed, "gt_len": len(gt), "cer": round(ed / max(len(gt), 1), 4),
                         "len_diff": len(pred) - len(gt),
                         "mean_char_prob": round(float(np.mean(probs)), 4) if probs else 0.0,
                         "min_char_prob": round(float(np.min(probs)), 4) if probs else 0.0,
                         "latency_ms": round(ms, 2), "format_status": r.format_status,
                         "layout_guess": r.layout_guess, "height": r.height,
                         "height_bucket": height_bucket(r.height), "source_subset": r.source_subset})
            cj.write(json.dumps({"filename": r.filename, "gt": gt, "prediction": pred, "chars": cp}) + "\n")

    res = pd.DataFrame([x for x in rows if "error" not in x])
    res.to_csv(out / "predictions.csv", index=False)
    lat = res.latency_ms.tolist()
    metrics = {
        "args": vars(a), "model_load_s": round(load_s, 2),
        "environment": {"python": platform.python_version(), "paddle": paddle.__version__,
                        "cpu": platform.processor(), "device": a.device},
        "unreadable": sum(1 for x in rows if "error" in x),
        "latency_ms": {"mean": round(statistics.mean(lat), 2), "median": round(statistics.median(lat), 2),
                       "p95": round(float(np.percentile(lat, 95)), 2), "max": round(max(lat), 2)},
        "per_char_probabilities_available": True,
        "metrics": summarise(res),
        "error_types": {"dropped_chars(pred shorter)": int((res.len_diff < 0).sum()),
                        "extra_chars(pred longer)": int((res.len_diff > 0).sum()),
                        "same_length_wrong": int(((res.len_diff == 0) & (res.exact == 0)).sum())},
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str))
    m = metrics["metrics"]["overall"]
    print(f"n={m['n']} exact_acc={m['exact_acc']} CER={m['cer']} empty={m['empty_pred']} | "
          f"latency ms mean={metrics['latency_ms']['mean']} median={metrics['latency_ms']['median']} "
          f"p95={metrics['latency_ms']['p95']} | load {metrics['model_load_s']}s -> {out}")


if __name__ == "__main__":
    main()
