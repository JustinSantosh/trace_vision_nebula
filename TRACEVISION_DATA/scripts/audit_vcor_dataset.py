#!/usr/bin/env python3
"""TRACEVISION AI - Phase 2: VCoR Dataset Audit and Integrity Verification.

Performs a read-only, non-destructive audit of the VCoR dataset located at
TRACEVISION_DATA/datasets/vcor/:
  1. Structure verification (splits, classes, unexpected files, empty folders)
  2. Image validity and decoding (corrupt/truncated images, dimensions, small crops, aspect ratios)
  3. Exact and perceptual duplicate detection (SHA-256, dHash, intra-split and cross-split leakage)
  4. Class distribution and imbalance analysis
  5. Generates structured JSON, CSV, and Markdown audit reports in TRACEVISION_DATA/reports/vcor_audit/

Usage:
    python TRACEVISION_DATA/scripts/audit_vcor_dataset.py
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from PIL import Image, ImageFile

# Ensure truncated images are caught rather than silently loaded
ImageFile.LOAD_TRUNCATED_IMAGES = False

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = ROOT / "TRACEVISION_DATA" / "datasets" / "vcor"
DEFAULT_OUT_DIR = ROOT / "TRACEVISION_DATA" / "reports" / "vcor_audit"

EXPECTED_SPLITS = ("train", "val", "test")
EXPECTED_CLASSES = (
    "beige", "black", "blue", "brown", "gold", "green", "grey",
    "orange", "pink", "purple", "red", "silver", "tan", "white", "yellow"
)


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hash of file contents."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def compute_dhash(img: Image.Image, hash_size: int = 8) -> str:
    """Compute standard 64-bit difference hash (dHash) for perceptual similarity."""
    gray = img.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.BILINEAR)
    pixels = list(gray.getdata())
    diff = []
    for row in range(hash_size):
        row_offset = row * (hash_size + 1)
        for col in range(hash_size):
            diff.append(pixels[row_offset + col] > pixels[row_offset + col + 1])
    val = 0
    for bit in diff:
        val = (val << 1) | int(bit)
    return f"{val:016x}"


def hamming_distance(h1_str: str, h2_str: str) -> int:
    """Compute Hamming distance between two 16-character hex strings."""
    v1 = int(h1_str, 16)
    v2 = int(h2_str, 16)
    return bin(v1 ^ v2).count("1")


def inspect_single_image(args: tuple[str, str, str]) -> dict:
    """Audit a single image file for validity, dimensions, hashes."""
    rel_path, split, cls = args
    full_path = ROOT / rel_path
    file_size = full_path.stat().st_size

    res = {
        "rel_path": rel_path.replace("\\", "/"),
        "filename": full_path.name,
        "split": split,
        "class": cls,
        "file_size": file_size,
        "valid": False,
        "error": None,
        "width": 0,
        "height": 0,
        "format": None,
        "mode": None,
        "aspect_ratio": 0.0,
        "sha256": None,
        "dhash": None,
    }

    try:
        sha256_val = compute_sha256(full_path)
        res["sha256"] = sha256_val

        with Image.open(full_path) as im:
            res["format"] = im.format
            res["mode"] = im.mode
            w, h = im.size
            res["width"] = w
            res["height"] = h
            res["aspect_ratio"] = round(w / h, 4) if h > 0 else 0.0

            # Force complete pixel decode to detect corrupt/truncated payloads
            im.load()
            res["dhash"] = compute_dhash(im)
            res["valid"] = True

    except Exception as e:
        res["valid"] = False
        res["error"] = f"{type(e).__name__}: {str(e)}"

    return res


def percentile(data: list[float | int], p: float) -> float:
    """Calculate percentile value."""
    if not data:
        return 0.0
    return float(np.percentile(data, p))


def run_audit(data_dir: Path, out_dir: Path):
    start_time = time.time()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== TRACEVISION VCoR Dataset Audit ===")
    print(f"Dataset root: {data_dir}")
    print(f"Output directory: {out_dir}\n")

    # 1. Structure Verification
    structure_info = {
        "dataset_root": str(data_dir.relative_to(ROOT)).replace("\\", "/"),
        "splits_found": [],
        "splits_missing": [],
        "classes_per_split": {},
        "missing_classes_per_split": {},
        "unexpected_files": [],
        "empty_folders": [],
        "file_counts": {},
        "total_files": 0
    }

    image_tasks = []
    class_split_counts = defaultdict(lambda: defaultdict(int))
    non_image_files = []

    for split in EXPECTED_SPLITS:
        split_dir = data_dir / split
        if split_dir.exists() and split_dir.is_dir():
            structure_info["splits_found"].append(split)
            classes_present = []
            classes_missing = []

            for cls in EXPECTED_CLASSES:
                cls_dir = split_dir / cls
                if cls_dir.exists() and cls_dir.is_dir():
                    classes_present.append(cls)
                    files = list(cls_dir.iterdir())
                    if not files:
                        structure_info["empty_folders"].append(str(cls_dir.relative_to(ROOT)).replace("\\", "/"))
                    for f in files:
                        if f.is_file():
                            ext = f.suffix.lower()
                            rel = str(f.relative_to(ROOT))
                            if ext in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
                                image_tasks.append((rel, split, cls))
                                class_split_counts[cls][split] += 1
                            else:
                                non_image_files.append({
                                    "path": rel.replace("\\", "/"),
                                    "filename": f.name,
                                    "extension": f.suffix,
                                    "size": f.stat().st_size
                                })
                else:
                    classes_missing.append(cls)

            structure_info["classes_per_split"][split] = sorted(classes_present)
            structure_info["missing_classes_per_split"][split] = sorted(classes_missing)
        else:
            structure_info["splits_missing"].append(split)

    structure_info["unexpected_files"] = non_image_files
    structure_info["total_files"] = len(image_tasks) + len(non_image_files)
    structure_info["image_files_count"] = len(image_tasks)

    # Count by split
    for split in EXPECTED_SPLITS:
        structure_info["file_counts"][split] = sum(class_split_counts[c][split] for c in EXPECTED_CLASSES)

    print(f"[1/4] Scanning files and decoding images ({len(image_tasks)} images)...")

    # 2. Process all images
    results = []
    # Using ProcessPoolExecutor for CPU-bound image decoding and hashing
    num_workers = min(os.cpu_count() or 4, 8)
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        for res in executor.map(inspect_single_image, image_tasks, chunksize=128):
            results.append(res)

    print(f"[2/4] Analyzing validity, dimensions, and corrupt images...")

    valid_images = [r for r in results if r["valid"]]
    corrupt_images = [r for r in results if not r["valid"]]

    # Image Dimensions Analysis
    widths = [r["width"] for r in valid_images]
    heights = [r["height"] for r in valid_images]
    aspect_ratios = [r["aspect_ratio"] for r in valid_images]
    file_sizes = [r["file_size"] for r in valid_images]
    formats = Counter(r["format"] for r in valid_images)
    modes = Counter(r["mode"] for r in valid_images)

    extremely_small_images = [
        r["rel_path"] for r in valid_images
        if r["width"] < 64 or r["height"] < 64
    ]
    tiny_images_32 = [
        r["rel_path"] for r in valid_images
        if r["width"] < 32 or r["height"] < 32
    ]
    unusual_aspect_ratios = [
        {
            "path": r["rel_path"],
            "width": r["width"],
            "height": r["height"],
            "aspect_ratio": r["aspect_ratio"],
            "class": r["class"]
        }
        for r in valid_images
        if r["aspect_ratio"] < 0.5 or r["aspect_ratio"] > 3.0
    ]

    # Per-class dimension stats
    per_class_dims = {}
    for cls in EXPECTED_CLASSES:
        cls_imgs = [r for r in valid_images if r["class"] == cls]
        if cls_imgs:
            c_w = [r["width"] for r in cls_imgs]
            c_h = [r["height"] for r in cls_imgs]
            c_ar = [r["aspect_ratio"] for r in cls_imgs]
            per_class_dims[cls] = {
                "count": len(cls_imgs),
                "width_mean": round(float(np.mean(c_w)), 1),
                "height_mean": round(float(np.mean(c_h)), 1),
                "aspect_ratio_mean": round(float(np.mean(c_ar)), 2),
                "aspect_ratio_median": round(float(np.median(c_ar)), 2),
            }

    dim_report = {
        "total_valid_images": len(valid_images),
        "total_corrupt_images": len(corrupt_images),
        "formats": dict(formats),
        "modes": dict(modes),
        "width": {
            "min": int(np.min(widths)) if widths else 0,
            "max": int(np.max(widths)) if widths else 0,
            "mean": round(float(np.mean(widths)), 2) if widths else 0,
            "median": round(float(np.median(widths)), 2) if widths else 0,
            "std": round(float(np.std(widths)), 2) if widths else 0,
            "p10": round(percentile(widths, 10), 2) if widths else 0,
            "p25": round(percentile(widths, 25), 2) if widths else 0,
            "p75": round(percentile(widths, 75), 2) if widths else 0,
            "p90": round(percentile(widths, 90), 2) if widths else 0,
        },
        "height": {
            "min": int(np.min(heights)) if heights else 0,
            "max": int(np.max(heights)) if heights else 0,
            "mean": round(float(np.mean(heights)), 2) if heights else 0,
            "median": round(float(np.median(heights)), 2) if heights else 0,
            "std": round(float(np.std(heights)), 2) if heights else 0,
            "p10": round(percentile(heights, 10), 2) if heights else 0,
            "p25": round(percentile(heights, 25), 2) if heights else 0,
            "p75": round(percentile(heights, 75), 2) if heights else 0,
            "p90": round(percentile(heights, 90), 2) if heights else 0,
        },
        "aspect_ratio": {
            "min": round(float(np.min(aspect_ratios)), 3) if aspect_ratios else 0,
            "max": round(float(np.max(aspect_ratios)), 3) if aspect_ratios else 0,
            "mean": round(float(np.mean(aspect_ratios)), 3) if aspect_ratios else 0,
            "median": round(float(np.median(aspect_ratios)), 3) if aspect_ratios else 0,
            "std": round(float(np.std(aspect_ratios)), 3) if aspect_ratios else 0,
            "p10": round(percentile(aspect_ratios, 10), 3) if aspect_ratios else 0,
            "p90": round(percentile(aspect_ratios, 90), 3) if aspect_ratios else 0,
        },
        "file_size_bytes": {
            "min": int(np.min(file_sizes)) if file_sizes else 0,
            "max": int(np.max(file_sizes)) if file_sizes else 0,
            "mean": round(float(np.mean(file_sizes)), 1) if file_sizes else 0,
            "median": round(float(np.median(file_sizes)), 1) if file_sizes else 0,
            "p10": round(percentile(file_sizes, 10), 1) if file_sizes else 0,
            "p90": round(percentile(file_sizes, 90), 1) if file_sizes else 0,
        },
        "extremely_small_images_under_64px": {
            "count": len(extremely_small_images),
            "paths": extremely_small_images[:50]
        },
        "tiny_images_under_32px": {
            "count": len(tiny_images_32),
            "paths": tiny_images_32
        },
        "unusual_aspect_ratios": {
            "count": len(unusual_aspect_ratios),
            "samples": unusual_aspect_ratios[:50]
        },
        "per_class_summary": per_class_dims
    }

    # 3. Duplicate and Leakage Detection
    print(f"[3/4] Checking exact and perceptual duplicates across splits...")

    sha_to_records = defaultdict(list)
    dhash_to_records = defaultdict(list)
    for r in valid_images:
        sha_to_records[r["sha256"]].append(r)
        dhash_to_records[r["dhash"]].append(r)

    exact_duplicate_groups = []
    cross_split_exact_leakage = []
    intra_split_exact_duplicates = defaultdict(list)

    for h, group in sha_to_records.items():
        if len(group) > 1:
            paths = [g["rel_path"] for g in group]
            splits = set(g["split"] for g in group)
            classes = set(g["class"] for g in group)
            group_entry = {
                "sha256": h,
                "count": len(group),
                "splits": sorted(list(splits)),
                "classes": sorted(list(classes)),
                "items": [
                    {"path": g["rel_path"], "split": g["split"], "class": g["class"]}
                    for g in group
                ]
            }
            exact_duplicate_groups.append(group_entry)

            if len(splits) > 1:
                cross_split_exact_leakage.append(group_entry)
            else:
                s = list(splits)[0]
                intra_split_exact_duplicates[s].append(group_entry)

    # Perceptual duplicates (exact dHash match)
    perceptual_dhash_groups = []
    cross_split_perceptual_leakage = []
    for dh, group in dhash_to_records.items():
        if len(group) > 1:
            # Check if this group has items with different SHA-256 (true perceptual duplicates)
            distinct_shas = set(g["sha256"] for g in group)
            splits = set(g["split"] for g in group)
            classes = set(g["class"] for g in group)
            entry = {
                "dhash": dh,
                "distinct_sha256_count": len(distinct_shas),
                "total_items": len(group),
                "splits": sorted(list(splits)),
                "classes": sorted(list(classes)),
                "items": [
                    {"path": g["rel_path"], "split": g["split"], "class": g["class"], "sha256": g["sha256"][:12]}
                    for g in group
                ]
            }
            perceptual_dhash_groups.append(entry)
            if len(splits) > 1:
                cross_split_perceptual_leakage.append(entry)

    duplicate_report = {
        "summary": {
            "total_images_analyzed": len(valid_images),
            "unique_sha256_hashes": len(sha_to_records),
            "unique_dhash_hashes": len(dhash_to_records),
            "exact_duplicate_groups_count": len(exact_duplicate_groups),
            "total_exact_duplicate_instances": sum(g["count"] for g in exact_duplicate_groups),
            "cross_split_exact_leakage_groups_count": len(cross_split_exact_leakage),
            "intra_split_exact_duplicate_groups": {s: len(intra_split_exact_duplicates[s]) for s in EXPECTED_SPLITS},
            "perceptual_dhash_groups_count": len(perceptual_dhash_groups),
            "cross_split_perceptual_leakage_groups_count": len(cross_split_perceptual_leakage),
        },
        "exact_duplicate_groups": exact_duplicate_groups,
        "perceptual_duplicate_groups": perceptual_dhash_groups[:100]
    }

    leakage_report = {
        "summary": {
            "cross_split_exact_leakage_count": len(cross_split_exact_leakage),
            "cross_split_perceptual_leakage_count": len(cross_split_perceptual_leakage),
            "train_val_exact_leaked_count": sum(1 for g in cross_split_exact_leakage if "train" in g["splits"] and "val" in g["splits"]),
            "train_test_exact_leaked_count": sum(1 for g in cross_split_exact_leakage if "train" in g["splits"] and "test" in g["splits"]),
            "val_test_exact_leaked_count": sum(1 for g in cross_split_exact_leakage if "val" in g["splits"] and "test" in g["splits"]),
        },
        "exact_leakage_groups": cross_split_exact_leakage,
        "perceptual_leakage_groups": cross_split_perceptual_leakage
    }

    # 4. Class Distribution & Imbalance
    print(f"[4/4] Generating CSV and JSON reports...")

    total_images = len(results)
    class_rows = []
    class_totals = {}
    for cls in sorted(EXPECTED_CLASSES):
        tr = class_split_counts[cls]["train"]
        va = class_split_counts[cls]["val"]
        te = class_split_counts[cls]["test"]
        tot = tr + va + te
        class_totals[cls] = tot
        pct_dataset = round((tot / total_images) * 100, 2) if total_images else 0.0
        tr_pct = round((tr / tot) * 100, 2) if tot else 0.0
        va_pct = round((va / tot) * 100, 2) if tot else 0.0
        te_pct = round((te / tot) * 100, 2) if tot else 0.0
        class_rows.append({
            "class": cls,
            "train": tr,
            "val": va,
            "test": te,
            "total": tot,
            "pct_of_dataset": pct_dataset,
            "train_pct_of_class": tr_pct,
            "val_pct_of_class": va_pct,
            "test_pct_of_class": te_pct
        })

    # Imbalance metrics
    max_cls = max(class_totals.items(), key=lambda x: x[1])
    min_cls = min(class_totals.items(), key=lambda x: x[1])
    imbalance_ratio = round(max_cls[1] / min_cls[1], 2)

    # Save Class Distribution CSV
    csv_path = out_dir / "class_distribution.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "class", "train", "val", "test", "total",
            "pct_of_dataset", "train_pct_of_class", "val_pct_of_class", "test_pct_of_class"
        ])
        writer.writeheader()
        writer.writerows(class_rows)

    # Save JSON reports
    with open(out_dir / "dataset_structure.json", "w", encoding="utf-8") as f:
        json.dump(structure_info, f, indent=2)

    with open(out_dir / "corrupt_images.json", "w", encoding="utf-8") as f:
        json.dump({
            "corrupt_count": len(corrupt_images),
            "corrupt_images": corrupt_images
        }, f, indent=2)

    with open(out_dir / "image_dimensions.json", "w", encoding="utf-8") as f:
        json.dump(dim_report, f, indent=2)

    with open(out_dir / "duplicate_images.json", "w", encoding="utf-8") as f:
        json.dump(duplicate_report, f, indent=2)

    with open(out_dir / "split_leakage_report.json", "w", encoding="utf-8") as f:
        json.dump(leakage_report, f, indent=2)

    elapsed = round(time.time() - start_time, 2)
    print(f"\nAudit completed in {elapsed}s.")
    print(f"Total images audited: {total_images}")
    print(f"Corrupt / unreadable: {len(corrupt_images)}")
    print(f"Exact duplicate groups: {len(exact_duplicate_groups)}")
    print(f"Cross-split exact leakage: {len(cross_split_exact_leakage)}")
    print(f"Class imbalance ratio (max/min): {max_cls[0]} ({max_cls[1]}) / {min_cls[0]} ({min_cls[1]}) = {imbalance_ratio}")
    print(f"Reports saved in: {out_dir}")

    return {
        "structure": structure_info,
        "valid_count": len(valid_images),
        "corrupt_count": len(corrupt_images),
        "dimensions": dim_report,
        "duplicates": duplicate_report,
        "leakage": leakage_report,
        "class_rows": class_rows,
        "max_cls": max_cls,
        "min_cls": min_cls,
        "imbalance_ratio": imbalance_ratio,
        "elapsed": elapsed
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit VCoR Dataset Integrity")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR, help="Path to vcor dataset root")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Output directory for reports")
    args = parser.parse_args()

    run_audit(args.data_dir, args.out_dir)

