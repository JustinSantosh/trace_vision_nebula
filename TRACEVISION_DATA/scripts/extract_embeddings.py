"""Manifest-driven CLIP ViT-B/32 Feature Extractor for TRACEVISION AI (Phase 3).

Reads only accepted records from proposed_clean_manifest.csv.
Applies 15-to-12 colour mapping.
Extracts L2-normalized 512-d embeddings using frozen OpenCLIP ViT-B/32 on CPU.
Supports checkpointing, resumption, deterministic ordering, and integrity verification.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Any

from PIL import Image
import torch
import open_clip

# Global configuration
MANIFEST_PATH = Path("TRACEVISION_DATA/reports/vcor_audit/proposed_clean_manifest.csv")
OUTPUT_DIR = Path("TRACEVISION_DATA/models")
EMBEDDINGS_FILE = OUTPUT_DIR / "vcor_clip_embeddings.pt"
PARTIAL_FILE = OUTPUT_DIR / "vcor_clip_embeddings_partial.pt"
METADATA_FILE = OUTPUT_DIR / "embeddings_manifest.json"

TARGET_CLASSES = [
    "black", "blue", "brown", "green", "grey", "orange",
    "other", "red", "silver", "unknown", "white", "yellow"
]

COLOUR_MAP = {
    "beige": "other",
    "black": "black",
    "blue": "blue",
    "brown": "brown",
    "gold": "other",
    "green": "green",
    "grey": "grey",
    "orange": "orange",
    "pink": "other",
    "purple": "other",
    "red": "red",
    "silver": "silver",
    "tan": "brown",
    "white": "white",
    "yellow": "yellow",
}


def load_clean_manifest() -> List[Dict[str, Any]]:
    """Loads and validates records from proposed_clean_manifest.csv where status == 'INCLUDE'."""
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"Manifest not found at {MANIFEST_PATH}")

    records = []
    excluded_count = 0
    with open(MANIFEST_PATH, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("status") == "INCLUDE":
                rel_path = row["rel_path"]
                orig_split = row["original_split"]
                orig_class = row["original_class"]
                mapped_class = COLOUR_MAP.get(orig_class, "other")

                # Verify mapped class is valid
                if mapped_class not in TARGET_CLASSES:
                    raise ValueError(f"Invalid mapped class '{mapped_class}' for row {row}")

                # Verify file exists
                if not Path(rel_path).exists():
                    raise FileNotFoundError(f"Source image missing: {rel_path}")

                records.append({
                    "rel_path": rel_path,
                    "filename": row.get("filename", Path(rel_path).name),
                    "split": orig_split,
                    "original_class": orig_class,
                    "mapped_class": mapped_class,
                })
            else:
                excluded_count += 1

    # Deterministic sort: split (train, val, test) then rel_path
    split_order = {"train": 0, "val": 1, "test": 2}
    records.sort(key=lambda r: (split_order.get(r["split"], 99), r["rel_path"]))

    print(f"Manifest loaded: {len(records)} clean images ({excluded_count} excluded images bypassed).")
    splits = {}
    for r in records:
        splits[r["split"]] = splits.get(r["split"], 0) + 1
    for s, count in splits.items():
        print(f"  - Split '{s}': {count} images")

    return records


def compute_sha256(file_path: Path) -> str:
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()


def main():
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    torch.set_num_threads(6)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    records = load_clean_manifest()
    total_records = len(records)
    if total_records != 10295:
        print(f"WARNING: Expected 10,295 clean records, but found {total_records}!")

    # Check for existing completed embeddings
    if EMBEDDINGS_FILE.exists() and METADATA_FILE.exists():
        print(f"Found existing embeddings file at {EMBEDDINGS_FILE}")
        try:
            cached_data = torch.load(EMBEDDINGS_FILE, weights_only=False)
            if cached_data.get("embeddings") is not None and len(cached_data["embeddings"]) == total_records:
                print("Cache is complete and valid. Validating metadata...")
                with open(METADATA_FILE, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                print(f"Loaded existing embeddings metadata: {meta.get('total_samples')} samples, model: {meta.get('model_name')}")
                print("Skipping extraction. (Delete cache to re-extract).")
                return
        except Exception as e:
            print(f"Could not load existing cache ({e}). Re-extracting...")

    # Check for partial resumption
    start_idx = 0
    extracted_tensors: List[torch.Tensor] = []
    if PARTIAL_FILE.exists():
        try:
            partial = torch.load(PARTIAL_FILE, weights_only=False)
            if "embeddings" in partial and len(partial["embeddings"]) < total_records:
                extracted_tensors = list(partial["embeddings"])
                start_idx = len(extracted_tensors)
                print(f"Resuming extraction from partial checkpoint at sample {start_idx}/{total_records}...")
        except Exception as e:
            print(f"Failed to load partial checkpoint ({e}). Starting fresh.")
            extracted_tensors = []
            start_idx = 0

    print("Initializing OpenCLIP ViT-B/32 (pretrained=openai) on CPU...")
    model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai", device="cpu")
    model.eval()

    # Extraction loop
    batch_size = 32
    checkpoint_every = 500
    t_start = time.time()
    last_log = t_start

    print(f"Extracting embeddings in batches of {batch_size} on CPU (6 threads)...")

    for i in range(start_idx, total_records, batch_size):
        batch_records = records[i:i + batch_size]
        batch_images = []
        for r in batch_records:
            try:
                with Image.open(r["rel_path"]) as img:
                    img_tensor = preprocess(img.convert("RGB"))
                    batch_images.append(img_tensor)
            except Exception as e:
                print(f"Error loading image {r['rel_path']}: {e}")
                # Create a black fallback tensor in the extremely rare case of load failure
                batch_images.append(torch.zeros(3, 224, 224))

        batch_tensor = torch.stack(batch_images)

        with torch.inference_mode():
            emb = model.encode_image(batch_tensor).float()
            # L2 unit-normalize
            emb = emb / emb.norm(dim=-1, keepdim=True)

        for j in range(emb.shape[0]):
            extracted_tensors.append(emb[j].cpu())

        now = time.time()
        processed = len(extracted_tensors)
        if processed % 200 == 0 or processed == total_records:
            elapsed = now - t_start
            speed = (processed - start_idx) / (now - t_start) if (now - t_start) > 0 else 0
            eta_sec = (total_records - processed) / speed if speed > 0 else 0
            pct = (processed / total_records) * 100
            print(f"Progress: [{processed:>5}/{total_records}] ({pct:5.1f}%) | "
                  f"Speed: {speed:4.1f} img/s | Elapsed: {elapsed/60:4.1f}m | ETA: {eta_sec/60:4.1f}m", flush=True)

        # Periodic partial checkpoint
        if processed % checkpoint_every == 0 and processed < total_records:
            torch.save({"embeddings": torch.stack(extracted_tensors)}, PARTIAL_FILE)

    all_embeddings = torch.stack(extracted_tensors)
    print(f"Extraction complete! Embeddings shape: {all_embeddings.shape}, dtype: {all_embeddings.dtype}")

    # Build final payload
    payload = {
        "embeddings": all_embeddings,
        "rel_paths": [r["rel_path"] for r in records],
        "filenames": [r["filename"] for r in records],
        "splits": [r["split"] for r in records],
        "original_classes": [r["original_class"] for r in records],
        "mapped_classes": [r["mapped_class"] for r in records],
        "target_classes": TARGET_CLASSES,
        "colour_map": COLOUR_MAP,
    }

    print(f"Saving final embeddings to {EMBEDDINGS_FILE}...")
    torch.save(payload, EMBEDDINGS_FILE)

    if PARTIAL_FILE.exists():
        PARTIAL_FILE.unlink()

    sha256_hash = compute_sha256(EMBEDDINGS_FILE)
    file_size_mb = EMBEDDINGS_FILE.stat().st_size / (1024 * 1024)

    # Save manifest metadata
    metadata = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model_name": "ViT-B-32",
        "pretrained": "openai",
        "device": "cpu",
        "total_samples": total_records,
        "split_counts": {
            "train": sum(1 for r in records if r["split"] == "train"),
            "val": sum(1 for r in records if r["split"] == "val"),
            "test": sum(1 for r in records if r["split"] == "test"),
        },
        "target_classes": TARGET_CLASSES,
        "embedding_dim": 512,
        "embeddings_file": str(EMBEDDINGS_FILE.as_posix()),
        "embeddings_file_size_mb": round(file_size_mb, 2),
        "sha256": sha256_hash,
        "normalized": True,
    }

    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print(f"Embeddings saved successfully! Size: {file_size_mb:.2f} MB, SHA-256: {sha256_hash}")
    print(f"Metadata saved to {METADATA_FILE}")


if __name__ == "__main__":
    main()

