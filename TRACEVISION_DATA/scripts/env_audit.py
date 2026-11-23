import sys
import os
import shutil
import torch
import open_clip

print("=== Python & Framework Environment ===")
print("Python executable:", sys.executable)
print("Python version:", sys.version)
print("PyTorch version:", torch.__version__)
print("OpenCLIP version:", getattr(open_clip, "__version__", "unknown"))

print("\n=== Hardware & Acceleration ===")
cuda_available = torch.cuda.is_available()
print("CUDA available:", cuda_available)
if cuda_available:
    print("CUDA device count:", torch.cuda.device_count())
    print("Device name:", torch.cuda.get_device_name(0))
    print("Device capability:", torch.cuda.get_device_capability(0))
    print("Device memory (GB):", torch.cuda.get_device_properties(0).total_memory / (1024**3))
else:
    print("CUDA is NOT available in this PyTorch build. CPU fallback will be utilized.")

print("\n=== Optional / ML Libraries ===")
for pkg in ["sklearn", "scipy", "numpy", "pandas", "PIL", "torchvision"]:
    try:
        mod = __import__(pkg)
        print(f"{pkg}: {getattr(mod, '__version__', 'installed')}")
    except ImportError:
        print(f"{pkg}: NOT installed")

print("\n=== Storage & Disk Space ===")
total, used, free = shutil.disk_usage(".")
print(f"Total disk space: {total / (1024**3):.2f} GB")
print(f"Used disk space:  {used / (1024**3):.2f} GB")
print(f"Free disk space:  {free / (1024**3):.2f} GB")

print("\n=== Model Checkpoints & Cache Inspection ===")
user_home = os.path.expanduser("~")
cache_roots = [
    os.path.join(user_home, ".cache", "clip"),
    os.path.join(user_home, ".cache", "huggingface", "hub"),
    os.path.join(user_home, ".cache", "torch", "hub", "checkpoints"),
    "models",
    "TRACEVISION_DATA/models",
]
for cr in cache_roots:
    if os.path.exists(cr):
        size_mb = sum(os.path.getsize(os.path.join(dirpath, f)) for dirpath, _, filenames in os.walk(cr) for f in filenames) / (1024**2)
        print(f"Found cache dir: {cr} ({size_mb:.2f} MB)")
        for root, dirs, files in os.walk(cr):
            for f in files:
                f_path = os.path.join(root, f)
                print(f"  - {f_path} ({os.path.getsize(f_path)/(1024**2):.2f} MB)")
    else:
        print(f"Directory not found: {cr}")

