#!/usr/bin/env python
"""Seeded, reproducible SYNTHETIC owner records and e-challan history for every synthetic registry vehicle.

Demo data only (DECISIONS E17). Nothing here comes from VAHAN, the e-Challan portal or any government system, and
the app never queries one. Every name is invented, every challan ID starts with "SYN-", and every row carries
synthetic = true. Fine amounts are illustrative. The records are keyed by synthetic_vehicle_id, so the registry
used for matching (and its evaluation) is untouched.

Vehicles seeded from the evaluation clips (source = evaluation_seed: the ones the demo can match) always get 2-4
challans, one of them recent and pending, so every matched vehicle has something to show.

Inputs   registry/synthetic_vehicle_registry.csv
Outputs  registry/synthetic_owner_records.csv   one row per registry vehicle
         registry/synthetic_echallans.csv       0-4 challans per vehicle

Deps   standard library only
Usage  python TRACEVISION_DATA/scripts/generate_vehicle_intel.py [--seed 2026]
"""
from __future__ import annotations

import argparse
import csv
import random
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path

DATA = Path(__file__).resolve().parents[1]
REGISTRY = DATA / "registry" / "synthetic_vehicle_registry.csv"
OWNERS = DATA / "registry" / "synthetic_owner_records.csv"
CHALLANS = DATA / "registry" / "synthetic_echallans.csv"
REFERENCE_DAY = date(2026, 11, 23)        # data is generated relative to this day so re-runs are identical

STATES = {"CG": ("Chhattisgarh", "Raipur"), "MP": ("Madhya Pradesh", "Bhopal"), "MH": ("Maharashtra", "Mumbai"),
          "OD": ("Odisha", "Bhubaneswar"), "JH": ("Jharkhand", "Ranchi"), "UP": ("Uttar Pradesh", "Lucknow"),
          "TG": ("Telangana", "Hyderabad"), "AP": ("Andhra Pradesh", "Vijayawada"), "DL": ("Delhi", "New Delhi"),
          "KA": ("Karnataka", "Bengaluru"), "TN": ("Tamil Nadu", "Chennai"), "KL": ("Kerala", "Kochi"),
          "HR": ("Haryana", "Gurugram"), "RJ": ("Rajasthan", "Jaipur"), "GJ": ("Gujarat", "Ahmedabad"),
          "WB": ("West Bengal", "Kolkata"), "BR": ("Bihar", "Patna"), "PB": ("Punjab", "Ludhiana"),
          "AS": ("Assam", "Guwahati"), "UK": ("Uttarakhand", "Dehradun"), "HP": ("Himachal Pradesh", "Shimla"),
          "GA": ("Goa", "Panaji")}
CG_RTO = {"04": "Raipur", "07": "Durg", "10": "Bilaspur", "13": "Raigarh", "08": "Rajnandgaon", "06": "Mahasamund"}
JUNCTIONS = ["Main Chowk", "Railway Station Road", "Bus Stand Square", "Ring Road Junction", "Collectorate Square",
             "Civil Lines Crossing", "Market Road", "Expressway Toll Plaza", "University Road", "Highway Bypass"]
CG_JUNCTIONS = ["Telibandha Chowk, Raipur", "Jaistambh Chowk, Raipur", "Pachpedi Naka, Raipur", "Shastri Chowk, Raipur",
                "Fafadih Chowk, Raipur", "Mowa Overbridge, Raipur", "Pulgaon Chowk, Durg", "Nehru Chowk, Bilaspur"]
FIRST = ["Aarav", "Vivaan", "Aditya", "Ishaan", "Kabir", "Arjun", "Rohan", "Karan", "Siddharth", "Nikhil", "Pranav",
         "Rahul", "Ananya", "Diya", "Ishita", "Kavya", "Meera", "Nisha", "Pooja", "Riya", "Sneha", "Tanvi", "Aditi",
         "Farhan", "Imran", "Ayesha", "Zoya", "Gurpreet", "Harleen", "Joseph", "Maria", "Suresh", "Lakshmi", "Venkat",
         "Deepa", "Tushar", "Bhavna", "Manish", "Shalini", "Abhishek", "Neha", "Yash", "Payal", "Devansh", "Sunita"]
LAST = ["Sharma", "Verma", "Gupta", "Agrawal", "Sahu", "Patel", "Yadav", "Singh", "Mishra", "Tiwari", "Dewangan",
        "Chandrakar", "Reddy", "Nair", "Iyer", "Das", "Banerjee", "Khan", "Qureshi", "Fernandes", "Gill", "Joshi",
        "Kulkarni", "Deshmukh", "Naidu", "Pillai", "Saxena", "Thakur", "Baghel", "Sinha"]
FIRMS = ["Mahanadi Logistics", "Indravati Transport Co.", "Shivnath Roadways", "Arpa Freight Carriers",
         "Kharun City Travels", "Hasdeo Goods Movers", "Sabri Passenger Services"]
COMMERCIAL = {"truck", "bus"}
VEHICLE_CLASS = {"car": "LMV (Motor Car)", "SUV": "LMV (Motor Car)", "van": "LMV (Motor Car / Omni)",
                 "motorcycle": "MCWG (Motorcycle with gear)", "scooter": "MCWOG (Scooter, without gear)",
                 "auto_rickshaw": "LMV 3-Wheeler (Passenger, Transport)", "truck": "HGV (Heavy Goods Vehicle)",
                 "bus": "HPV (Heavy Passenger Vehicle)"}
TRANSPORT = {"auto_rickshaw", "truck", "bus"}
FUEL = {"car": [("Petrol", 55), ("Diesel", 20), ("CNG", 15), ("Electric", 10)],
        "SUV": [("Diesel", 55), ("Petrol", 38), ("Electric", 7)],
        "van": [("Petrol", 50), ("CNG", 40), ("Diesel", 10)],
        "motorcycle": [("Petrol", 94), ("Electric", 6)], "scooter": [("Petrol", 75), ("Electric", 25)],
        "auto_rickshaw": [("CNG", 55), ("LPG", 15), ("Electric", 30)],
        "truck": [("Diesel", 100)], "bus": [("Diesel", 85), ("CNG", 10), ("Electric", 5)]}
# Illustrative fine amounts (INR), demo only.
VIOLATIONS = {
    "Riding without helmet": (1000, {"motorcycle", "scooter"}),
    "Triple riding": (1000, {"motorcycle", "scooter"}),
    "Driving without seatbelt": (1000, {"car", "SUV", "van", "truck", "bus"}),
    "Red light violation": (1000, None),
    "Over-speeding": (2000, None),
    "Wrong-side driving": (1000, None),
    "Stop-line violation": (500, None),
    "No parking / illegal parking": (500, None),
    "Using mobile phone while driving": (5000, None),
    "Driving without valid PUC": (10000, None),
    "Overloading": (20000, {"truck"}),
    "Carrying passengers beyond capacity": (2000, {"auto_rickshaw", "bus"}),
}
STATUS = [("Paid", 55), ("Pending", 35), ("Sent to virtual court", 10)]


def pick(rng, weighted):
    return rng.choices([v for v, _ in weighted], weights=[w for _, w in weighted])[0]


def rto_of(reg: str):
    m = re.match(r"^([A-Z]{2})(\d{1,2})", reg)
    if m and m.group(1) in STATES:
        st, num = m.group(1), m.group(2).zfill(2)
        place = CG_RTO.get(num) if st == "CG" else None
        return st, f"{st}-{num}", f"RTO {st}-{num}" + (f", {place}" if place else f", {STATES[st][0]}")
    m = re.match(r"^(\d{2})BH", reg)
    if m:
        return "BH", "BH", "Bharat series (BH) registration"
    return "", "", "Unknown RTO"


def location(rng, state):
    if state == "CG" or state in ("", "BH"):
        return rng.choice(CG_JUNCTIONS)
    return f"{rng.choice(JUNCTIONS)}, {STATES[state][1]}"


def owner_name(rng, vtype):
    if vtype in COMMERCIAL and rng.random() < 0.8:
        return rng.choice(FIRMS), "Firm"
    return f"{rng.choice(FIRST)} {rng.choice(LAST)}", "Individual"


def mask_name(name: str) -> str:
    return " ".join(w[0] + "•" * max(2, len(w) - 1) for w in name.split())


def days(rng, lo, hi):
    return REFERENCE_DAY + timedelta(days=rng.randint(lo, hi))


def build(seed: int, registry=None):
    """`registry` = rows to build for (default: the main registry plus the committed demo layer, DECISIONS M21)."""
    if registry is None:
        registry = list(csv.DictReader(open(REGISTRY, encoding="utf-8")))
        demo = DATA / "registry" / "synthetic_demo_registry.csv"
        if demo.exists():
            registry += list(csv.DictReader(open(demo, encoding="utf-8")))
    owners, challans = [], []
    for row in registry:
        rid, reg, vtype = row["synthetic_vehicle_id"], row["registration_number"], row["vehicle_type"]
        rng = random.Random(f"{seed}:{rid}")           # per-vehicle stream: adding vehicles never reshuffles others
        state, rto_code, rto_name = rto_of(reg)
        year = int(row["model_year"] or 2018)
        reg_date = date(year, rng.randint(1, 12), rng.randint(1, 28))
        reg_date = min(reg_date, REFERENCE_DAY - timedelta(days=30))
        valid_years = 2 if vtype in TRANSPORT else 15  # transport: fitness renewal; private: 15-year registration
        valid_until = reg_date.replace(year=reg_date.year + valid_years)
        while vtype in TRANSPORT and valid_until < REFERENCE_DAY - timedelta(days=200):
            valid_until = valid_until.replace(year=valid_until.year + valid_years)   # renewed on time, mostly
        name, kind = owner_name(rng, vtype)
        owners.append({
            "synthetic_vehicle_id": rid, "registration_number": reg, "owner_name": name, "owner_type": kind,
            "owner_name_masked": mask_name(name), "owner_serial": rng.choices([1, 2, 3], weights=[70, 24, 6])[0],
            "vehicle_class": VEHICLE_CLASS.get(vtype, "LMV"), "fuel_type": pick(rng, FUEL.get(vtype, [("Petrol", 1)])),
            "rto_code": rto_code, "rto_name": rto_name, "registration_date": reg_date.isoformat(),
            "registration_valid_until": valid_until.isoformat(),
            "insurance_valid_until": (days(rng, 15, 340) if rng.random() < 0.8 else days(rng, -400, -5)).isoformat(),
            "puc_valid_until": (days(rng, 10, 180) if rng.random() < 0.75 else days(rng, -300, -3)).isoformat(),
            "synthetic": "true",
        })
        n = rng.choices([0, 1, 2, 3, 4], weights=[38, 26, 18, 11, 7])[0]
        # Vehicles the system can actually match in the demo clips always get a history with something pending.
        seed_row = row.get("source") in ("evaluation_seed", "demo_seed")
        if seed_row:
            n = max(n, rng.choice([2, 3, 4]))
        allowed = [v for v, (_, types) in VIOLATIONS.items() if types is None or vtype in types]
        earliest = max(reg_date, REFERENCE_DAY - timedelta(days=3 * 365))
        span = max(1, (REFERENCE_DAY - earliest).days - 1)
        for k in range(n):
            vio = rng.choice(allowed)
            when = datetime.combine(earliest, time(0)) + timedelta(days=rng.randint(0, span), minutes=rng.randint(7 * 60, 22 * 60))
            status = pick(rng, STATUS)
            if seed_row and k == 0:                     # one recent, unpaid challan
                when = datetime.combine(REFERENCE_DAY, time(0)) - timedelta(days=rng.randint(10, 120), minutes=-rng.randint(7 * 60, 22 * 60))
                status = "Pending"
            if (REFERENCE_DAY - when.date()).days > 400 and status == "Pending":
                status = "Paid"                         # very old challans are mostly settled
            challans.append({
                "challan_id": f"SYN-{state or 'XX'}-{when.year}-{rng.randint(100000, 999999)}",
                "synthetic_vehicle_id": rid, "registration_number": reg, "violation": vio,
                "date": when.isoformat(timespec="minutes"), "location": location(rng, state),
                "fine_inr": VIOLATIONS[vio][0], "status": status,
                "issuing_authority": f"{STATES.get(state, ('Chhattisgarh',))[0]} Traffic Police (synthetic)",
                "source": "synthetic_history", "synthetic": "true",
            })
    challans.sort(key=lambda c: (c["registration_number"], c["date"]))
    return owners, challans


def write(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=2026)
    a = ap.parse_args()
    owners, challans = build(a.seed)
    write(OWNERS, owners)
    write(CHALLANS, challans)
    pending = sum(1 for c in challans if c["status"] == "Pending")
    print(f"{len(owners)} owner records -> {OWNERS.relative_to(DATA.parent)}")
    print(f"{len(challans)} challans ({pending} pending) -> {CHALLANS.relative_to(DATA.parent)}")


if __name__ == "__main__":
    main()
