import csv
import json
from collections import Counter

manifest_path = "TRACEVISION_DATA/reports/vcor_audit/proposed_clean_manifest.csv"
exclusion_path = "TRACEVISION_DATA/reports/vcor_audit/exclusion_accounting.csv"
micro_path = "TRACEVISION_DATA/reports/vcor_audit/micro_resolution_disposition.csv"
validation_path = "TRACEVISION_DATA/reports/vcor_audit/manifest_validation.json"

with open(manifest_path, mode="r", encoding="utf-8") as f:
    manifest_rows = list(csv.DictReader(f))

with open(exclusion_path, mode="r", encoding="utf-8") as f:
    exclusion_rows = list(csv.DictReader(f))

with open(micro_path, mode="r", encoding="utf-8") as f:
    micro_rows = list(csv.DictReader(f))

with open(validation_path, mode="r", encoding="utf-8") as f:
    validation_data = json.load(f)

print(f"Total manifest rows: {len(manifest_rows)}")
manifest_paths = [r["rel_path"] for r in manifest_rows]
unique_manifest_paths = set(manifest_paths)
print(f"Unique manifest paths: {len(unique_manifest_paths)}")

included_paths = {r["rel_path"] for r in manifest_rows if r["status"] == "INCLUDE"}
excluded_paths = {r["rel_path"] for r in manifest_rows if r["status"] == "EXCLUDE"}

print(f"Included paths: {len(included_paths)}")
print(f"Excluded paths: {len(excluded_paths)}")
print(f"Included + Excluded: {len(included_paths) + len(excluded_paths)}")

# Reasons in manifest
reasons = Counter(r["exclusion_reason"] for r in manifest_rows)
print("\nExclusion reason breakdown in proposed_clean_manifest.csv:")
for r, c in sorted(reasons.items(), key=lambda x: -x[1]):
    print(f"  {r}: {c}")

# Categorized by exclusion category in manifest
exact_manifest = {r["rel_path"] for r in manifest_rows if "EXACT_DUP" in r["exclusion_reason"]}
perceptual_manifest = {r["rel_path"] for r in manifest_rows if "CROSS_SPLIT_LEAKAGE" in r["exclusion_reason"] or "PERCEPT_LEAK" in r["exclusion_reason"]}
micro_manifest = {r["rel_path"] for r in manifest_rows if "TINY_IMAGE" in r["exclusion_reason"]}

print("\n--- Manifest-derived primary sets ---")
print(f"Exact duplicate primary exclusions: {len(exact_manifest)}")
print(f"Perceptual leakage primary exclusions: {len(perceptual_manifest)}")
print(f"Micro-resolution primary exclusions: {len(micro_manifest)}")

print(f"Exact & Perceptual intersection: {len(exact_manifest & perceptual_manifest)}")
print(f"Exact & Micro intersection: {len(exact_manifest & micro_manifest)}")
print(f"Perceptual & Micro intersection: {len(perceptual_manifest & micro_manifest)}")

manifest_union = exact_manifest | perceptual_manifest | micro_manifest
print(f"Union of primary exclusion sets: {len(manifest_union)}")
print(f"Does primary union equal excluded_paths? {manifest_union == excluded_paths}")

# Now let's check multi-label / overlapping sets using exclusion_accounting.csv
print("\n--- All-applicable reasons from exclusion_accounting.csv ---")
acc_all_paths = {r["path"] for r in exclusion_rows}
print(f"Exclusion accounting total rows: {len(exclusion_rows)}, unique paths: {len(acc_all_paths)}")
print(f"acc_all_paths == excluded_paths: {acc_all_paths == excluded_paths}")

exact_all = {r["path"] for r in exclusion_rows if r["exact_dup_group"] != "NONE"}
perceptual_all = {r["path"] for r in exclusion_rows if r["perceptual_dup_group"] != "NONE"}
micro_all = {r["path"] for r in exclusion_rows if r["is_micro_resolution"] == "True"}

print(f"Paths with Exact Duplicate membership: {len(exact_all)}")
print(f"Paths with Perceptual Duplicate membership: {len(perceptual_all)}")
print(f"Paths with Micro Resolution (< 32px): {len(micro_all)}")

print(f"Exact & Perceptual all-applicable intersection: {len(exact_all & perceptual_all)}")
print(f"Exact & Micro all-applicable intersection: {len(exact_all & micro_all)}")
print(f"Perceptual & Micro all-applicable intersection: {len(perceptual_all & micro_all)}")
print(f"Exact & Perceptual & Micro 3-way intersection: {len(exact_all & perceptual_all & micro_all)}")

all_applicable_union = exact_all | perceptual_all | micro_all
print(f"Union of all-applicable sets: {len(all_applicable_union)}")
print(f"Does all-applicable union equal excluded_paths? {all_applicable_union == excluded_paths}")

print("\nListing overlapping paths:")
for p in sorted(all_applicable_union):
    r_list = [r for r in exclusion_rows if r["path"] == p]
    if r_list and r_list[0]["has_overlapping_reasons"] == "True":
        r = r_list[0]
        print(f"  {p} | exact={r['exact_dup_group']} | percept={r['perceptual_dup_group']} | micro={r['is_micro_resolution']} | primary={r['final_manifest_reason']}")

# Check micro disposition
print(f"\nMicro disposition total rows: {len(micro_rows)}")
micro_disp_paths = {r["path"] for r in micro_rows}
print(f"Micro disposition paths == micro_all: {micro_disp_paths == micro_all}")
print(f"Micro disposition dispositions: {Counter(r['manifest_status'] for r in micro_rows)}")

# Reconcile counts by split and class
split_totals = Counter(r["original_split"] for r in manifest_rows)
split_inc = Counter(r["original_split"] for r in manifest_rows if r["status"] == "INCLUDE")
split_exc = Counter(r["original_split"] for r in manifest_rows if r["status"] == "EXCLUDE")

print("\n--- Split Reconciliation ---")
for s in ["train", "val", "test"]:
    print(f"  {s}: total={split_totals[s]}, included={split_inc[s]}, excluded={split_exc[s]} (sum: {split_inc[s] + split_exc[s]})")

print("\n--- Class and Split Clean Distribution ---")
classes = sorted(list({r["original_class"] for r in manifest_rows}))
print(f"{'Class':<10} | {'Train Inc':<10} | {'Train Exc':<10} | {'Val Inc':<10} | {'Val Exc':<10} | {'Test Inc':<10} | {'Test Exc':<10} | {'Total Clean':<12}")
print("-" * 85)
for c in classes:
    tr_inc = sum(1 for r in manifest_rows if r["original_class"] == c and r["original_split"] == "train" and r["status"] == "INCLUDE")
    tr_exc = sum(1 for r in manifest_rows if r["original_class"] == c and r["original_split"] == "train" and r["status"] == "EXCLUDE")
    val_inc = sum(1 for r in manifest_rows if r["original_class"] == c and r["original_split"] == "val" and r["status"] == "INCLUDE")
    val_exc = sum(1 for r in manifest_rows if r["original_class"] == c and r["original_split"] == "val" and r["status"] == "EXCLUDE")
    tst_inc = sum(1 for r in manifest_rows if r["original_class"] == c and r["original_split"] == "test" and r["status"] == "INCLUDE")
    tst_exc = sum(1 for r in manifest_rows if r["original_class"] == c and r["original_split"] == "test" and r["status"] == "EXCLUDE")
    tot_clean = tr_inc + val_inc + tst_inc
    print(f"{c:<10} | {tr_inc:<10} | {tr_exc:<10} | {val_inc:<10} | {val_exc:<10} | {tst_inc:<10} | {tst_exc:<10} | {tot_clean:<12}")

print("-" * 85)
tot_tr_inc = sum(1 for r in manifest_rows if r["original_split"] == "train" and r["status"] == "INCLUDE")
tot_tr_exc = sum(1 for r in manifest_rows if r["original_split"] == "train" and r["status"] == "EXCLUDE")
tot_val_inc = sum(1 for r in manifest_rows if r["original_split"] == "val" and r["status"] == "INCLUDE")
tot_val_exc = sum(1 for r in manifest_rows if r["original_split"] == "val" and r["status"] == "EXCLUDE")
tot_tst_inc = sum(1 for r in manifest_rows if r["original_split"] == "test" and r["status"] == "INCLUDE")
tot_tst_exc = sum(1 for r in manifest_rows if r["original_split"] == "test" and r["status"] == "EXCLUDE")
tot_all_clean = tot_tr_inc + tot_val_inc + tot_tst_inc
print(f"{'TOTAL':<10} | {tot_tr_inc:<10} | {tot_tr_exc:<10} | {tot_val_inc:<10} | {tot_val_exc:<10} | {tot_tst_inc:<10} | {tot_tst_exc:<10} | {tot_all_clean:<12}")
