import os
import time
import torch
import open_clip

print("CPU count:", os.cpu_count(), "Torch threads:", torch.get_num_threads())
model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai", device="cpu")
model.eval()

# Benchmark batch of 32 dummy images
x = torch.randn(32, 3, 224, 224)
t0 = time.time()
with torch.no_grad():
    for _ in range(3):
        out = model.encode_image(x)
dt = (time.time() - t0) / 3
rate = 32 / dt
print(f"Time per batch of 32: {dt:.3f}s ({rate:.1f} imgs/sec)")
total_imgs = 10295
est_sec = total_imgs / rate
print(f"Estimated extraction time for {total_imgs} images: {est_sec/60:.1f} minutes")

