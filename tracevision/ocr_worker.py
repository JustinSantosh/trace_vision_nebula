"""Awiros OCR in a separate process (DECISIONS M7: torch and Paddle can't share a process on Windows).

    with OCRWorker(device="gpu") as ocr:
        reads = ocr.read([crop_bgr, ...])   # -> [{"text": "...", "chars": [{"char","prob","t","top3"}], "ms": 14.2}, ...]

Uses exactly the preprocessing (`prep_paddle`, B8) and CTC decoding of `scripts/awiros_feasibility_check.py`.
"""
from __future__ import annotations

import multiprocessing as mp
import sys
import time

from . import ROOT

SCRIPTS = ROOT / "TRACEVISION_DATA/scripts"


def _serve(q_in, q_out, device):
    sys.path.insert(0, str(SCRIPTS))
    try:   # the import is inside the try too: a missing package must be REPORTED, not kill the process silently
        import awiros_feasibility_check as a
        paddle, model, chars, _ = a.load_model(ROOT / "TRACEVISION_DATA/models/awiros", ROOT / "third_party/PaddleOCR", device)
    except Exception as e:  # report start-up failure instead of hanging the caller
        q_out.put(("error", repr(e)))
        return
    q_out.put(("ready", device))
    while True:
        job = q_in.get()
        if job is None:
            break
        out = []
        for img in job:
            t = time.perf_counter()
            x = paddle.to_tensor(a.prep_paddle(img)[None])
            with paddle.no_grad():
                p = model(x)
            p = (p["ctc"] if isinstance(p, dict) else p).numpy()[0]
            text, cp = a.ctc_decode(p, chars)
            out.append({"text": text, "chars": cp, "ms": round((time.perf_counter() - t) * 1000, 1)})
        q_out.put(("ok", out))


class OCRWorker:
    def __init__(self, device="gpu", timeout=300):
        self.device, self.timeout = device, timeout
        self._ctx = mp.get_context("spawn")
        self.q_in, self.q_out = self._ctx.Queue(), self._ctx.Queue()
        self.proc = None

    def __enter__(self):
        self.proc = self._ctx.Process(target=_serve, args=(self.q_in, self.q_out, self.device), daemon=True)
        self.proc.start()
        status, info = self._get("start-up")
        if status != "ready":
            raise RuntimeError(f"OCR worker failed to start: {info}")
        return self

    def _get(self, what):
        """Wait for the worker's reply, but notice at once if the worker process died (instead of a silent
        `queue.Empty` after the full timeout, which hid the real cause; audit bug 1)."""
        import queue
        deadline = time.time() + self.timeout
        while True:
            try:
                return self.q_out.get(timeout=1.0)
            except queue.Empty:
                if not self.proc.is_alive():
                    raise RuntimeError(f"OCR worker process exited during {what} (exit code {self.proc.exitcode}). "
                                       "Check PaddlePaddle / third_party/PaddleOCR (git submodule update --init) "
                                       "and the Awiros weights (git lfs pull).")
                if time.time() > deadline:
                    raise RuntimeError(f"OCR worker did not answer within {self.timeout} s during {what}.")

    def read(self, crops):
        if not crops:
            return []
        self.q_in.put(list(crops))
        status, out = self._get("reading")
        if status != "ok":
            raise RuntimeError(f"OCR worker error: {out}")
        return out

    def __exit__(self, *exc):
        if self.proc and self.proc.is_alive():
            self.q_in.put(None)
            self.proc.join(15)
            if self.proc.is_alive():
                self.proc.terminate()
