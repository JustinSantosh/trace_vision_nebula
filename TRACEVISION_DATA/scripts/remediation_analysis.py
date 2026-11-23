#!/usr/bin/env python3
"""TRACEVISION AI - Phase 2.1: Dataset Integrity Remediation Analysis.

Investigates:
  1. Exact duplicate groups and conflicting labels (Task 1).
  2. 47 cross-split perceptual duplicate groups with image comparison metrics (Task 2).
  3. Generates resolution tables and proposed clean manifest (Task 4 & 5).
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "TRACEVISION_DATA" / "datasets" / "vcor"
REPORTS_DIR = ROOT / "TRACEVISION_DATA" / "reports" / "vcor_audit"

PROVISIONAL_MAPPING = {
    "black": "black",
    "blue": "blue",
    "brown": "brown",
    "green": "green",
    "grey": "grey",
    "orange": "orange",
    "red": "red",
    "silver": "silver",
    "white": "white",
    "yellow": "yellow",
    "tan": "brown",
    "beige": "other",
    "gold": "other",
    "pink": "other",
    "purple": "other",
}


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def compute_dhash(img: Image.Image, hash_size: int = 8) -> str:
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


def compare_two_images(p1: Path, p2: Path) -> dict:
    """Compute detailed visual similarity metrics between two image files."""
    im1_cv = cv2.imread(str(p1))
    im2_cv = cv2.imread(str(p2))

    if im1_cv is None or im2_cv is None:
        return {"error": "Failed to read image"}

    h1, w1 = im1_cv.shape[:2]
    h2, w2 = im2_cv.shape[:2]

    # Normalized histogram correlation (Hue + Saturation)
    hsv1 = cv2.cvtColor(im1_cv, cv2.COLOR_BGR2HSV)
    hsv2 = cv2.cvtColor(im2_cv, cv2.COLOR_BGR2HSV)
    hist1 = cv2.calcHist([hsv1], [0, 1], None, [30, 32], [0, 180, 0, 256])
    hist2 = cv2.calcHist([hsv2], [0, 1], None, [30, 32], [0, 180, 0, 256])
    cv2.normalize(hist1, hist1, 0, 1, cv2.NORM_MINMAX)
    cv2.normalize(hist2, hist2, 0, 1, cv2.NORM_MINMAX)
    hist_corr = float(cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL))

    # Resize both to 256x256 for pixel MSE and Normalized Cross Correlation
    r1 = cv2.resize(im1_cv, (256, 256), interpolation=cv2.INTER_AREA)
    r2 = cv2.resize(im2_cv, (256, 256), interpolation=cv2.INTER_AREA)

    gray1 = cv2.cvtColor(r1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(r2, cv2.COLOR_BGR2GRAY)

    mse = float(np.mean((gray1.astype(float) - gray2.astype(float)) ** 2))
    psnr = float(cv2.PSNR(gray1, gray2)) if mse > 0 else 999.0

    # Cross-correlation coefficient of grayscale images
    ncc = float(np.corrcoef(gray1.ravel(), gray2.ravel())[0, 1]) if np.std(gray1) > 0 and np.std(gray2) > 0 else 0.0

    return {
        "dim1": f"{w1}x{h1}",
        "dim2": f"{w2}x{h2}",
        "same_dims": (w1 == w2 and h1 == h2),
        "hist_corr": round(hist_corr, 4),
        "mse": round(mse, 2),
        "psnr": round(psnr, 2),
        "ncc": round(ncc, 4),
    }


def analyze_exact_duplicates():
    dup_json = REPORTS_DIR / "duplicate_images.json"
    data = json.loads(dup_json.read_text(encoding="utf-8"))
    groups = data["exact_duplicate_groups"]

    results = []

    # Explanations for each group
    explanations = {
        0: (
            "Cross-Split Leakage & Category Ambiguity: Metallic Champagne/Beige vs Gold. "
            "Under sunlight, metallic beige/champagne finish shows warm golden specular reflections. "
            "Annotator in train classified as beige; annotator in val classified as gold. "
            "Critical cross-split leakage: training on this sample directly leaks to validation evaluation."
        ),
        1: (
            "Intra-Train Label Contradiction: Dark shadow/underexposure vs Tan body. "
            "Vehicle with high contrast: body is tan/brown, but deep shadows or dark roof/trim caused dual submission under black and tan."
        ),
        2: (
            "Intra-Train Label Contradiction: Two-tone vehicle or extreme annotation error (Blue vs Red). "
            "Vehicle contains distinct blue and red accents, or annotator uploaded erroneous label."
        ),
        3: (
            "Intra-Train Label Contradiction: Grey vs Silver achromatic boundary. "
            "Matte or non-metallic grey finish versus metallic silver. Highly prone to subjective label disagreement."
        ),
        4: (
            "Intra-Train Label Contradiction: Grey vs Silver achromatic boundary. "
            "Identical metallic grey/silver crossover vehicle crop."
        ),
        5: (
            "Intra-Train Label Contradiction: Orange vs Red chromatic boundary. "
            "Reddish-orange / burnt orange vehicle falling on the border of Hue 10-20."
        ),
        6: (
            "Intra-Train Label Contradiction: Silver vs White achromatic boundary. "
            "High-key silver car under bright overcast sky washed out to white."
        ),
        7: (
            "Cross-Split Leakage & Label Contradiction: Silver (test) vs White (train). "
            "Identical car image appears in train/white and test/silver. "
            "Severe evaluation hazard: test benchmark will unfairly penalize an accurate white prediction or vice-versa, with exact data leakage."
        ),
        8: (
            "Intra-Val Label Contradiction: Green vs Yellow chromatic boundary. "
            "Lime green / yellow-green vehicle crop falling directly on the Hue 35-45 border."
        ),
        9: (
            "Intra-Test Label Contradiction: Grey vs Silver in test set. "
            "Identical car in test/grey and test/silver. Any model evaluation on the test set will be penalized regardless of output."
        )
    }

    for idx, g in enumerate(groups):
        sha = g["sha256"]
        items = g["items"]
        splits = g["splits"]
        classes = g["classes"]
        is_cross_split = len(splits) > 1

        # Verify disk SHA256 for all items
        verified = True
        dims = []
        for it in items:
            p = ROOT / it["path"]
            actual_sha = compute_sha256(p)
            if actual_sha != sha:
                verified = False
            im = cv2.imread(str(p))
            dims.append(f"{im.shape[1]}x{im.shape[0]}" if im is not None else "error")

        expl = explanations.get(idx, "Label conflict between conflicting visual categories.")

        # Recommendation
        if is_cross_split:
            rec = "EXCLUDE_ALL_COPIES: High severity cross-split leakage. Exclude both training and evaluation instances to guarantee test purity and eliminate label noise."
        else:
            rec = "EXCLUDE_ALL_COPIES: Conflicting labels for identical image. Retaining either creates false supervised training gradients; exclude from clean manifest."

        for it, dim in zip(items, dims):
            results.append({
                "group_id": f"EXACT_DUP_{idx+1:02d}",
                "sha256": sha,
                "file_path": it["path"],
                "split": it["split"],
                "original_class": it["class"],
                "dimensions": dim,
                "verified_sha256_match": verified,
                "is_cross_split": is_cross_split,
                "splits_in_group": "+".join(splits),
                "classes_in_group": "+".join(classes),
                "label_conflict_analysis": expl,
                "recommendation": rec
            })

    # Save to CSV
    out_csv = REPORTS_DIR / "exact_duplicate_resolution.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "group_id", "sha256", "file_path", "split", "original_class",
            "dimensions", "verified_sha256_match", "is_cross_split",
            "splits_in_group", "classes_in_group", "label_conflict_analysis", "recommendation"
        ])
        writer.writeheader()
        writer.writerows(results)

    print(f"Exact duplicates analysis complete: {len(results)} files in {len(groups)} groups written to {out_csv}")
    return results


def analyze_perceptual_duplicates():
    leak_json = REPORTS_DIR / "split_leakage_report.json"
    data = json.loads(leak_json.read_text(encoding="utf-8"))
    groups = data["perceptual_leakage_groups"]

    results = []

    for idx, g in enumerate(groups):
        dh = g["dhash"]
        items = g["items"]
        splits = g["splits"]
        classes = g["classes"]

        # Check pairwise comparison across splits
        # Pick first train item and first non-train item
        train_items = [it for it in items if it["split"] == "train"]
        eval_items = [it for it in items if it["split"] in ("val", "test")]

        if not train_items or not eval_items:
            # val vs test
            p1 = ROOT / items[0]["path"]
            p2 = ROOT / items[1]["path"]
            it1 = items[0]
            it2 = items[1]
        else:
            p1 = ROOT / train_items[0]["path"]
            p2 = ROOT / eval_items[0]["path"]
            it1 = train_items[0]
            it2 = eval_items[0]

        comp = compare_two_images(p1, p2)

        # Categorize
        # 1) SAME_VEHICLE_DIFFERENT_FRAMES
        # 2) SAME_IMAGE_RESIZED_OR_COMPRESSED
        # 3) SIMILAR_VEHICLES_NOT_DUPLICATES
        # 4) FALSE_POSITIVE_HASH_COLLISION

        # If NCC and Hist correlation are very high (> 0.95 and > 0.85), same image or burst
        # If dimensions differ but NCC > 0.98 -> Resized/Compressed
        ncc = comp.get("ncc", 0.0)
        hist_corr = comp.get("hist_corr", 0.0)
        psnr = comp.get("psnr", 0.0)
        same_dims = comp.get("same_dims", False)

        if ncc > 0.98 and hist_corr > 0.95:
            if not same_dims or psnr < 30.0:
                cat = "SAME_IMAGE_RESIZED_OR_COMPRESSED"
                assessment = "Exact or near-exact image subject to re-encoding, minor cropping or resolution change across splits."
                policy = "EXCLUDE_TRAIN_INSTANCE: Leakage confirmed. Exclude train image to preserve untouched validation/test split."
            else:
                cat = "EXACT_OR_RECOMPRESSED_DUPLICATE"
                assessment = "Identical visual subject with minimal variation."
                policy = "EXCLUDE_TRAIN_INSTANCE: Definite leakage. Exclude train counterpart."
        elif ncc > 0.88 and hist_corr > 0.80:
            cat = "SAME_VEHICLE_DIFFERENT_FRAMES"
            assessment = "Same vehicle captured in rapid succession from slightly shifted camera angle / track positions."
            policy = "EXCLUDE_TRAIN_INSTANCE: Near-burst leakage. Exclude train sample to avoid artificially inflating evaluation metrics."
        elif ncc > 0.70 and hist_corr > 0.60:
            cat = "SIMILAR_VEHICLES_NOT_DUPLICATES"
            assessment = "Distinct vehicles of similar make, model, and perspective that happen to match 64-bit dHash."
            policy = "RETAIN_WITH_FLAG: Acceptable cross-split co-occurrence of similar vehicle models."
        else:
            cat = "FALSE_POSITIVE_HASH_COLLISION"
            assessment = "Coincidental hash collision between visually distinct vehicles due to flat backgrounds or simple color gradients."
            policy = "RETAIN_ALL: Hash collision; vehicles are visually distinct."

        results.append({
            "group_id": f"PERCEPT_LEAK_{idx+1:02d}",
            "dhash": dh,
            "file_1": it1["path"],
            "split_1": it1["split"],
            "class_1": it1["class"],
            "dim_1": comp.get("dim1", ""),
            "file_2": it2["path"],
            "split_2": it2["split"],
            "class_2": it2["class"],
            "dim_2": comp.get("dim2", ""),
            "hist_correlation": hist_corr,
            "normalized_cross_corr": ncc,
            "psnr": psnr,
            "classification": cat,
            "detailed_assessment": assessment,
            "remediation_policy": policy
        })

    out_csv = REPORTS_DIR / "perceptual_duplicate_review.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "group_id", "dhash", "file_1", "split_1", "class_1", "dim_1",
            "file_2", "split_2", "class_2", "dim_2", "hist_correlation",
            "normalized_cross_corr", "psnr", "classification",
            "detailed_assessment", "remediation_policy"
        ])
        writer.writeheader()
        writer.writerows(results)

    print(f"Perceptual duplicates review complete: {len(results)} cross-split groups analyzed and written to {out_csv}")
    return results


def build_clean_manifest(exact_resolutions, perceptual_resolutions):
    """Generate proposed clean manifest for all 10,373 images."""
    dim_json = REPORTS_DIR / "image_dimensions.json"
    dim_data = json.loads(dim_json.read_text(encoding="utf-8"))
    tiny_paths = set(dim_data["tiny_images_under_32px"]["paths"])

    # Build lookup of exact duplicates
    exact_excluded_paths = set()
    exact_reasons = {}
    for r in exact_resolutions:
        p = r["file_path"].replace("\\", "/")
        exact_excluded_paths.add(p)
        exact_reasons[p] = f"EXACT_DUP_CONFLICT_{r['group_id']}"

    # Build lookup of perceptual leakage exclusions (exclude train instances)
    percept_excluded_paths = set()
    percept_reasons = {}
    for r in perceptual_resolutions:
        if "EXCLUDE_TRAIN_INSTANCE" in r["remediation_policy"]:
            # Check which is train
            if r["split_1"] == "train":
                p = r["file_1"].replace("\\", "/")
                percept_excluded_paths.add(p)
                percept_reasons[p] = f"CROSS_SPLIT_LEAKAGE_{r['classification']}_{r['group_id']}"
            if r["split_2"] == "train":
                p = r["file_2"].replace("\\", "/")
                percept_excluded_paths.add(p)
                percept_reasons[p] = f"CROSS_SPLIT_LEAKAGE_{r['classification']}_{r['group_id']}"

    manifest_rows = []
    include_count = 0
    exclude_count = 0

    counts_by_split_status = defaultdict(lambda: defaultdict(int))
    counts_by_mapped_class = Counter()

    for split in ("train", "val", "test"):
        split_dir = DATA_DIR / split
        for cls_dir in sorted(split_dir.iterdir()):
            if not cls_dir.is_dir():
                continue
            orig_cls = cls_dir.name
            mapped_cls = PROVISIONAL_MAPPING.get(orig_cls, "other")

            for f in sorted(cls_dir.iterdir()):
                if not f.is_file() or f.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                    continue

                rel = str(f.relative_to(ROOT)).replace("\\", "/")
                status = "INCLUDE"
                reason = "CLEAN"

                # Check exclusion hierarchy
                if rel in exact_excluded_paths:
                    status = "EXCLUDE"
                    reason = exact_reasons[rel]
                elif rel in percept_excluded_paths:
                    status = "EXCLUDE"
                    reason = percept_reasons[rel]
                elif rel in tiny_paths:
                    status = "EXCLUDE"
                    reason = "TINY_IMAGE_SUB_32PX"

                if status == "INCLUDE":
                    include_count += 1
                    counts_by_mapped_class[mapped_cls] += 1
                else:
                    exclude_count += 1

                counts_by_split_status[split][status] += 1

                manifest_rows.append({
                    "rel_path": rel,
                    "filename": f.name,
                    "original_split": split,
                    "original_class": orig_cls,
                    "proposed_mapped_class": mapped_cls,
                    "status": status,
                    "exclusion_reason": reason
                })

    out_csv = REPORTS_DIR / "proposed_clean_manifest.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "rel_path", "filename", "original_split", "original_class",
            "proposed_mapped_class", "status", "exclusion_reason"
        ])
        writer.writeheader()
        writer.writerows(manifest_rows)

    print(f"\nProposed Clean Manifest Generated: {len(manifest_rows)} total rows written to {out_csv}")
    print(f"Total Included: {include_count} ({round(include_count/len(manifest_rows)*100, 2)}%)")
    print(f"Total Excluded: {exclude_count} ({round(exclude_count/len(manifest_rows)*100, 2)}%)")
    for s in ("train", "val", "test"):
        print(f"  {s}: {counts_by_split_status[s]['INCLUDE']} included, {counts_by_split_status[s]['EXCLUDE']} excluded (Total: {counts_by_split_status[s]['INCLUDE'] + counts_by_split_status[s]['EXCLUDE']})")
    print(f"Mapped class distribution (Included samples):")
    for mc, cnt in counts_by_mapped_class.most_common():
        print(f"  {mc}: {cnt}")

    return {
        "manifest_path": out_csv,
        "total_rows": len(manifest_rows),
        "included": include_count,
        "excluded": exclude_count,
        "by_split": dict(counts_by_split_status),
        "by_mapped_class": dict(counts_by_mapped_class)
    }


def main():
    print("=== Running Phase 2.1 Remediation Analysis ===")
    exact_res = analyze_exact_duplicates()
    percept_res = analyze_perceptual_duplicates()
    manifest_summary = build_clean_manifest(exact_res, percept_res)


if __name__ == "__main__":
    main()
