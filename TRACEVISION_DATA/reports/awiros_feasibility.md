# Awiros ANPR OCR — Feasibility Check (Phase 0C)

**Date:** 2026-11-22 · **Script:** `scripts/awiros_feasibility_check.py` · **Model:** HF `Awiros/anpr-ocr` (`model.safetensors`, sha256 `f9f1264e…2e68e47`, Apache-2.0)
**Environment:** Windows 11, Python 3.12.6, PaddlePaddle 3.3.1 (CPU build, oneDNN compiled in), PaddleOCR @ `dab3fe3` (`third_party/PaddleOCR`), 12 logical CPUs. Evaluation only: nothing was trained or tuned.

## Verdict

| Question | Answer |
|---|---|
| Does it install and run on our Windows laptop? | **Yes**, on CPU. PaddlePaddle 3.3.1 plus a few `ppocr` dependencies (tqdm, rapidfuzz, lmdb, shapely, pyclipper, scikit-image). |
| **Per-character probabilities?** | **Yes.** The CTC head gives a softmax over 64 classes at each of 40 timesteps. PaddleOCR's `CTCLabelDecode` already computes a probability per character and then averages them. Our script keeps the **probability of every emitted character plus its top-3 alternatives**, written to `char_probs.jsonl`. **The B1 fallback is not needed.** |
| Accuracy | Full 965 unique plates: **81.5% exact, 4.4% CER**. Standard-format labels only: **86.0% / 3.1%**. Two-row plates: 60.5%. At mean char prob ≥ 0.99: **97.1%** (61% of plates). |
| **Latency** | **GPU (RTX 3050, `paddlepaddle-gpu` 3.3.1 cu126): median 15 ms, p95 53 ms per crop.** That is fast enough for video. The CPU build takes about 3.8 s per crop, which is too slow (see Finding 2). |
| Official preprocessing | **It has a bug that drops characters.** Use `--preprocess paddle`. See below. |

## Finding 1: the official `test.py` preprocessing drops characters

`test.py` resizes the crop to a height of 48, pads the right side with **black pixels**, and *then* normalises. That turns the padding into **−1**. PaddleOCR's own `resize_norm_img` normalises first and then pads with **0** (mid-grey), which is what the model was trained on.

On the 9 model-card sample crops (7 of them have ground truth in the card's README):

| Preprocessing | Correct of 7 | Notes |
|---|---|---|
| Official `test.py` (pad −1) | **3 / 7** | Drops one character on 4 plates, e.g. `HR38AB2421`→`HR38AB421` and `UP14BQ9208`→`UP14BQ208`, at confidence ≥ 0.97. **This exactly reproduces the published `sample_results.json`**, so the published outputs are wrong too. |
| **Pad 0 after normalising (PaddleOCR standard)** | **7 / 7** | Used as the default (`--preprocess paddle`) |
| Dynamic width (≥ 320) | 7 / 7 | Same as above for these crops |
| RGB instead of BGR | 7 / 7 | Channel order does not matter here |
| Stretch to 320×48 | 4 / 7 | Wrecks narrow and two-row plates |

On the 20-crop smoke test: **paddle 80% / CER 3.2%** against **official 70% / CER 4.8%**.

## Finding 2: CPU latency is dominated by the backbone

Profiled with a random 1×3×48×320 input (`scratchpad/awiros_speed.py`):

| Part | Median |
|---|---|
| Full forward | 4,150 ms |
| **Backbone (PPHGNetV2_B4) only** | **3,966 ms** |
| Head (CTC + SVTR neck) only | 137 ms |
| Batch of 8 | 33,100 ms (linear: batching does not help) |
| `paddle.jit.to_static` | 4,035 ms (no gain) |
| With `FLAGS_use_onednn=True` | 4,028 ms (no gain) |
| A single 512-channel 3×3 conv on 12×80 | 51 ms (plain conv speed is normal) |

So the CPU itself is not slow. Some backbone operator in Paddle 3.3.1's Windows CPU build is very slow. Since Awiros reports 5 ms on an RTX 3090, a GPU is the realistic route.

**Options, in order of preference:**
1. **Local RTX 3050 (6 GB):** install the `paddlepaddle-gpu` CUDA build. *Needs approval (the CPU build was what was approved).* Expect tens of milliseconds per crop.
2. **Colab GPU** for the benchmark. It doesn't help the live demo unless the app runs there.
3. **Reduce calls:** OCR only the best 3–5 frames per vehicle track (sharpness or plate-size ranking). Even at 4 s each, that is 12–20 s per vehicle. Acceptable for an offline investigator report, not for real time.
4. *Untested:* export to ONNX (`paddle2onnx`) and run with `onnxruntime` on CPU.

## Finding 3: on the GPU, the latency problem is solved

`paddlepaddle-gpu==3.3.1` (CUDA 12.6 wheel, driver 581.86 / CUDA 13.0) installed on 2026-11-22 with approval. It replaces the CPU build. `paddle.utils.run_check()` passes on the RTX 3050 (compute capability 8.6).

| Run | Median | p95 | Exact | CER |
|---|---|---|---|---|
| CPU, 965 plates | 3,800 ms | 3,876 ms | 81.45% | 4.39% |
| **GPU, 965 plates** | **15.4 ms** | **53.3 ms** | 81.45% | 4.40% |

The accuracy is the same. Only 1 of the 965 predictions differs, and it is a very low-confidence read (min char prob 0.31): `AP2D1014` on CPU against `AP32D1014` on GPU, where the label is `AP2D4014`. That is floating-point noise around a near-tie. GPU outputs are in `processed/ocr_evaluation/zenitsu09/awiros_full_paddle_gpu/`.

## Full benchmark: zenitsu09, 965 unique plates (`eval_primary = 1`, `--preprocess paddle`)

Completed 2026-11-22. 0 unreadable, 0 empty predictions. Raw outputs are in `processed/ocr_evaluation/zenitsu09/awiros_full_paddle/` (`metrics.json`, `predictions.csv`, `char_probs.jsonl`).

| Slice | n | Exact match | CER |
|---|---|---|---|
| **All unique plates** | 965 | **81.5%** | **4.39%** |
| **Standard format only** (regex passes) | 883 | **86.0%** | **3.12%** |
| Nonstandard / suspect labels | 82 | 32.9% | 19.1% |
| Single-row | 879 | 83.5% | 3.64% |
| **Two-row** | 86 | **60.5%** | 12.25% |
| Crop height < 20 px | 364 | 76.9% | 5.15% |
| 20–39 px | 351 | 88.0% | 2.63% |
| ≥ 40 px | 250 | 78.8% | 5.73% |

**Confidence is informative.** Mean character probability against exact-match accuracy:

| Mean char prob | n | Exact match |
|---|---|---|
| < 0.5 | 12 | 0% |
| 0.5–0.8 | 36 | 0% |
| 0.8–0.9 | 53 | 22.6% |
| 0.9–0.95 | 79 | 55.7% |
| 0.95–0.99 | 197 | 80.7% |
| **≥ 0.99** | **588 (61%)** | **97.1%** |

Taking only reads with a mean probability of at least 0.95 keeps 785 plates (81%) at **93.0%** exact. Everything below 0.8 was wrong, so reads in that range should be shown as "unreadable" or sent to multi-frame fusion, never shown as a plate.

**Error types (179 wrong):**
- 123 have the same length but wrong characters (for example `MH48AC6244`→`MH49…`).
- 45 dropped characters.
- 11 have extra characters.

**Confidently wrong:** 11 of the 124 standard-format errors still have a *minimum* character probability of at least 0.9, for example `OD14E3131`→`DD14E3131` (0.99) and `MH05EJ3005`→`MH05EJ3805` (0.9995). These need a state-code or format check, plus voting across frames. Some of them may be label errors. Nobody has checked them visually (A20).

**Latency over the full run:** median 3,800 ms, p95 3,876 ms, max 4,300 ms on CPU. That is about 3.8 s per crop and 61 minutes for 965 crops. It confirms B7.

**What the numbers say:**
- Large crops (≥ 40 px) score *worse* than mid-size ones. Those are mostly close-up photos with tilt, two rows and stylised fonts, not a resolution problem.
- Two-row plates are the weakest slice. The model reads them as a single line.

## Reproduce

```powershell
# 20-crop smoke test (both preprocessing modes)
python TRACEVISION_DATA/scripts/awiros_feasibility_check.py --gt TRACEVISION_DATA/processed/ocr_evaluation/zenitsu09/ground_truth.csv --out TRACEVISION_DATA/processed/ocr_evaluation/zenitsu09/awiros_smoke20_paddle --sample 20 --primary-only --preprocess paddle
python TRACEVISION_DATA/scripts/awiros_feasibility_check.py --gt TRACEVISION_DATA/processed/ocr_evaluation/zenitsu09/ground_truth.csv --out TRACEVISION_DATA/processed/ocr_evaluation/zenitsu09/awiros_smoke20_official --sample 20 --primary-only --preprocess official
# Full benchmark: about 20 s on the GPU (--device gpu), about 61 min on the CPU
python TRACEVISION_DATA/scripts/awiros_feasibility_check.py --gt TRACEVISION_DATA/processed/ocr_evaluation/zenitsu09/ground_truth.csv --out TRACEVISION_DATA/processed/ocr_evaluation/zenitsu09/awiros_full_paddle --primary-only --preprocess paddle
```

## Caveats
- zenitsu09 crops are mostly small (median 23 px tall; 364 of 965 are under 20 px) and come from the same images as Quobotic (PROBLEMS A16).
- 82 of the 965 ground-truth labels fail the plate regex and some are clearly wrong (`TERRANO`). Scores are reported with and without them (A20).
- Still photos, not CCTV. The headline OCR numbers must come from our own clips (A13).
