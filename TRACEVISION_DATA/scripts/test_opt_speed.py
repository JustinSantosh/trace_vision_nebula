import os
import time
import torch
import open_clip

torch.set_num_threads(6)
os.environ["HF_HUB_OFFLINE"] = "1"

model, _, _ = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai", device="cpu")
model.eval()

# Test with inference_mode and batch size 64
x = torch.randn(64, 3, 224, 224)
with torch.inference_mode():
    out = model.encode_image(x)
    t0 = time.time()
    for _ in range(3):
        out = model.encode_image(x)
    dt = (time.time() - t0) / 3

rate = 64 / dt
print(f"Batch 64 with inference_mode: {dt:.3f}s ({rate:.1f} imgs/sec, ~{10295/rate/60:.1f} min total)")

