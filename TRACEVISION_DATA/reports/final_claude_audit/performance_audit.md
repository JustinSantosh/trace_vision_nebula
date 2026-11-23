# Performance audit

All figures measured on this machine (Windows 11, CPU-only torch 2.15, GPU MX130 2 GB unused). The README's
5–24 s per clip figures were measured by the team on an RTX 3050 and could not be reproduced here.

## End-to-end pipeline (real upload through `/jobs` on the running engine)
clip13.mp4 (4.8 s, 848×478, 60 fps):

| Stage | This machine (CPU) | Stored team run (RTX 3050) |
|---|---|---|
| Detect + track (UVH-26 + COCO ensemble) | 180.0 s | 3.8 s |
| Plate detection | 23.4 s | 0.6 s |
| OCR (Awiros, separate process) | 142.3 s | 0.2 s |
| Assemble (fusion, colour CLIP, matching) | 38.1 s | 0.1 s |
| **Total** | **398.4 s** (421 s wall incl. report) | 5.4 s |

**Output identical to the stored GPU result**: 3 vehicles, T1 `CG04NL3024` → match, two no-confident-match,
same types and colours. Report HTML, PDF, result JSON and the viewer all served 200.

Conclusion: the code path is correct on CPU, but CPU is ≈ 75× slower; live analysis needs the CUDA setup in the
README. Stored results and all review/enforcement features are instant either way.

## API latency (single request, warm, localhost)
`/api/overview` 104 ms · `/api/violations` 241 ms (runs the wrong-side check over 19 stored results each call) ·
`/api/review` 22 ms · `/api/colour/model_info` 27 ms · `/api/parking/scan/runs/clip02` 27 ms ·
parking/e-challan lists 5–7 ms · `/` 88 ms.

## Colour inference (CPU, per crop, 62 CCTV crops)
Heuristic 6 ms · CLIP zero-shot ≈ 1.8 s average including first-call text-prompt encoding · probe ≈ 0.5–0.8 s
(dominated by the CLIP image encoder; the linear head itself is < 0.1 ms). Probe v2 training: 110 s CPU.

## Changes made for performance
None to the pipeline. Model loading was already done once per process (engine at startup, CLIP and the probe
cached in module dicts); the probe cache is now keyed per file so v1/v2 can coexist without reloading.

## Opportunities (not implemented: they need GPU benchmarking to justify)
1. `/api/violations` recomputes the wrong-side check for every stored run on every call; caching by result mtime would make it O(1).
2. Batch the colour CLIP call across vehicles of a clip instead of per vehicle.
3. Detection on every 2nd frame (`detect_every: 2`) is already in place; FP16 on GPU would roughly halve detector time but must be re-validated against the evaluation clips.

CPU/RAM/VRAM profiles were not captured (no profiler run); GPU usage could not be measured.
