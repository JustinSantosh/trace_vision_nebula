import os
import time
import torch
import open_clip

for threads in [4, 6, 8]:
    torch.set_num_threads(threads)
    model, _, _ = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai", device="cpu")
    model.eval()
    x = torch.randn(32, 3, 224, 224)
    with torch.no_grad():
        out = model.encode_image(x) # warmup
        t0 = time.time()
        for _ in range(3):
            out = model.encode_image(x)
        dt = (time.time() - t0) / 3
    rate = 32 / dt
    print(f"Threads: {threads} -> {dt:.3f}s per 32 batch ({rate:.1f} imgs/sec, ~{10295/rate/60:.1f} min total)")

