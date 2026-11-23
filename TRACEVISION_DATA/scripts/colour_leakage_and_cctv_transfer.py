"""1) near-duplicate leakage across VCoR splits (embedding cosine >= 0.98 / 0.995)
2) CCTV transfer (REPORTING ONLY): heuristic / CLIP zero-shot / probe v1 / probe v2 on the 62 labelled CCTV crops,
   using the production estimate_colour path (night rule included). Writes JSON to argv[1]."""
import csv, json, sys, time, collections, os
from pathlib import Path
ROOT = Path(r"c:\Users\PC-01\trace_vision_nebula"); sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
import cv2, torch
from tracevision import colour

d = torch.load("TRACEVISION_DATA/models/vcor_clip_embeddings.pt", weights_only=False)
E, S = d["embeddings"].float(), d["splits"]
tr = torch.tensor([i for i, s in enumerate(S) if s == "train"])
leak = {}
for split in ("val", "test"):
    ix = torch.tensor([i for i, s in enumerate(S) if s == split])
    sim = (E[ix] @ E[tr].T).max(1).values
    leak[split] = {"n": len(ix), "max_cos_ge_0.995": int((sim >= 0.995).sum()), "max_cos_ge_0.98": int((sim >= 0.98).sum()),
                   "median_max_cos": round(float(sim.median()), 4)}
vt = (E[[i for i, s in enumerate(S) if s == "val"]] @ E[[i for i, s in enumerate(S) if s == "test"]].T).max(1).values
leak["val_vs_test_ge_0.995"] = int((vt >= 0.995).sum())
print("leakage:", leak)

NEAR = {"white": {"white", "silver", "grey"}, "silver": {"silver", "white", "grey"}, "grey": {"grey", "silver", "black"},
        "black": {"black", "grey"}, "red": {"red", "brown", "orange"}, "brown": {"brown", "red", "orange", "black"},
        "orange": {"orange", "yellow", "brown", "red"}, "yellow": {"yellow", "orange"}, "green": {"green", "yellow", "blue"},
        "blue": {"blue", "green", "black", "grey"}}
rows = list(csv.DictReader(open("TRACEVISION_DATA/evaluation/test_clip_labels.csv", encoding="utf-8")))
samples = []
for r in rows:
    vp = ROOT / "TRACEVISION_DATA/raw/test_videos" / f"{r['clip_id']}.mp4"
    bb = (r.get("vehicle_bbox_first_frame") or "").strip()
    if not vp.exists() or not bb:
        continue
    cap = cv2.VideoCapture(str(vp)); cap.set(cv2.CAP_PROP_POS_FRAMES, int(r["first_frame"])); ok, fr = cap.read(); cap.release()
    if not ok:
        continue
    x1, y1, x2, y2 = [int(float(v)) for v in bb.split(",")]
    h, w = fr.shape[:2]
    cr = fr[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
    if cr.size == 0 or min(cr.shape[:2]) < 8:
        continue
    samples.append((r["clip_id"], r["target_vehicle_id"], r["colour"].strip().lower(), r.get("vehicle_type", "car").strip(), cr))

methods = {"heuristic": dict(method="heuristic"), "clip_zero_shot": dict(method="clip"),
           "probe_v1": dict(method="linear_probe", probe_path=ROOT / "TRACEVISION_DATA/models/vcor_linear_probe.pt"),
           "probe_v2": dict(method="linear_probe", probe_path=ROOT / "TRACEVISION_DATA/models/vcor_linear_probe_v2.pt")}
out = {"leakage": leak, "n": len(samples), "methods": {}}
for name, kw in methods.items():
    preds, t0 = [], time.time()
    for clip, tid, gt, vt_, cr in samples:
        res = colour.estimate_colour([cr], vt_, **kw)
        preds.append(res["label"])
    dt = (time.time() - t0) / max(1, len(samples)) * 1000
    gts = [s[2] for s in samples]
    ex = sum(p == g for p, g in zip(preds, gts)); nr = sum(p in NEAR.get(g, {g}) for p, g in zip(preds, gts))
    unk = sum(p == "unknown" for p in preds)
    per = collections.defaultdict(lambda: [0, 0])
    for p, g in zip(preds, gts):
        per[g][1] += 1; per[g][0] += p == g
    out["methods"][name] = {"exact": ex, "near": nr, "unknown": unk, "ms_per_crop": round(dt, 1),
                            "pred_dist": dict(collections.Counter(preds)), "per_class_exact": {k: f"{a}/{b}" for k, (a, b) in sorted(per.items())}}
    print(name, out["methods"][name])
Path(sys.argv[1]).write_text(json.dumps(out, indent=2), encoding="utf-8")
