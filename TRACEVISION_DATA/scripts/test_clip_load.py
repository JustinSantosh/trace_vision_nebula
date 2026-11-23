import open_clip
import torch

print("Loading local OpenCLIP ViT-B-32 on CPU...")
model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai", device="cpu")
model.eval()
params = sum(p.numel() for p in model.parameters())
print(f"Loaded successfully! Parameter count: {params:,}")
print("Preprocess pipeline:", preprocess)

