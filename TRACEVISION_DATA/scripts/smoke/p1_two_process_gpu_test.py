"""Torch/YOLO in the main process, Paddle/Awiros in a spawned worker - both on the same GPU."""
import multiprocessing as mp
import sys
import time

ROOT = r"E:\hack_a_sol"


def ocr_worker(q_in, q_out):
    sys.path.insert(0, ROOT + r"\TRACEVISION_DATA\scripts")
    import cv2
    import awiros_feasibility_check as a
    from pathlib import Path
    paddle, model, chars, awt = a.load_model(Path(ROOT + r"\TRACEVISION_DATA\models\awiros"), Path(ROOT + r"\third_party\PaddleOCR"), "gpu")
    q_out.put(("ready", None))
    while True:
        path = q_in.get()
        if path is None:
            break
        img = cv2.imread(path)
        t = time.perf_counter()
        x = paddle.to_tensor(a.prep_paddle(img)[None])
        with paddle.no_grad():
            p = model(x)
        p = (p["ctc"] if isinstance(p, dict) else p).numpy()[0]
        text, cp = a.ctc_decode(p, chars)
        q_out.put(("ok", (path.split("\\")[-1], text, round((time.perf_counter() - t) * 1000, 1), len(cp))))


if __name__ == "__main__":
    ctx = mp.get_context("spawn")
    q_in, q_out = ctx.Queue(), ctx.Queue()
    w = ctx.Process(target=ocr_worker, args=(q_in, q_out), daemon=True)
    w.start()
    import torch
    from ultralytics import YOLO
    m = YOLO(ROOT + r"\TRACEVISION_DATA\models\weights\UVH-26-MV-YOLOv11-S.pt")
    r = m.predict(ROOT + r"\TRACEVISION_DATA\processed\test_video_frames\clip02\fps1\clip02_f000000.jpg", device=0, verbose=False)
    print("main: torch", torch.__version__, "cudnn", torch.backends.cudnn.version(), "| YOLO boxes:", len(r[0].boxes))
    print("worker:", q_out.get(timeout=120)[0])
    import glob
    crops = sorted(glob.glob(ROOT + r"\TRACEVISION_DATA\processed\ocr_evaluation\zenitsu09\crops\*.png"))[:6]
    for c in crops:
        q_in.put(c)
    for _ in crops:
        status, (name, text, ms, n) = q_out.get(timeout=60)
        print("worker OCR:", name, "->", len(text), "chars,", ms, "ms")
    q_in.put(None); w.join(10)
    r = m.predict(ROOT + r"\TRACEVISION_DATA\processed\test_video_frames\clip02\fps1\clip02_f000030.jpg", device=0, verbose=False)
    print("main: YOLO still fine after worker, boxes:", len(r[0].boxes))
