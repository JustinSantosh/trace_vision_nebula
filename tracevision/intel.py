"""Vehicle intelligence: registered-owner record + e-challan history, simulated challan issuing, audit log.

SYNTHETIC DEMO DATA ONLY (DECISIONS E17). The records come from registry/synthetic_owner_records.csv and
registry/synthetic_echallans.csv (TRACEVISION_DATA/scripts/generate_vehicle_intel.py). No VAHAN / e-Challan
service is queried, and an issued challan is only written to runs/enforcement/issued_challans.json.

A lookup returns everything on record for the registration. Every lookup, issue and cancellation is appended to
runs/audit/lookups.jsonl.
"""
from __future__ import annotations

import csv
import json
import re
import threading
import uuid
from datetime import date, datetime

from . import ROOT

REG_DIR = ROOT / "TRACEVISION_DATA" / "registry"
AUDIT = ROOT / "runs" / "audit" / "lookups.jsonl"
ISSUED = ROOT / "runs" / "enforcement" / "issued_challans.json"
REASONS = ["Active investigation", "Violation review", "Stolen vehicle check", "Court / legal request", "Training / demo"]
# Illustrative fine amounts (INR) for issuing, demo only (same table as generate_vehicle_intel.py).
VIOLATION_FINES = {
    "Wrong-side driving": 1000, "Riding without helmet": 1000, "Triple riding": 1000, "Driving without seatbelt": 1000,
    "Red light violation": 1000, "Over-speeding": 2000, "Stop-line violation": 500, "No parking / illegal parking": 500,
    "Using mobile phone while driving": 5000, "Driving without valid PUC": 10000, "Driving without insurance": 2000,
    "Overloading": 20000, "Carrying passengers beyond capacity": 2000,
}
_lock = threading.Lock()
_cache: dict = {}


class Refused(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def norm_reg(raw: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (raw or "").upper())


def clean(raw, n: int) -> str:
    return re.sub(r"[\x00-\x1f]", " ", str(raw or "")).strip()[:n]


def _tables():
    paths = [REG_DIR / n for n in ("synthetic_vehicle_registry.csv", "synthetic_owner_records.csv", "synthetic_echallans.csv")]
    stamp = tuple(p.stat().st_mtime if p.exists() else 0 for p in paths)
    if _cache.get("stamp") != stamp:
        def rows(p):
            return list(csv.DictReader(open(p, encoding="utf-8"))) if p.exists() else []
        reg, own, ch = (rows(p) for p in paths)
        challans: dict[str, list] = {}
        for c in ch:
            challans.setdefault(c["registration_number"], []).append(c)
        _cache.update(stamp=stamp, by_reg={r["registration_number"]: r for r in reg},
                      owners={r["synthetic_vehicle_id"]: r for r in own}, challans=challans)
    return _cache


def available() -> bool:
    return bool(_tables()["owners"])


def in_registry(reg: str) -> bool:
    return norm_reg(reg) in _tables()["by_reg"]


# ---------------------------------------------------------------- simulated (issued) challans
def issued_challans() -> list:
    try:
        return json.loads(ISSUED.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save_issued(items):
    ISSUED.parent.mkdir(parents=True, exist_ok=True)
    ISSUED.write_text(json.dumps(items, indent=1), encoding="utf-8")


def issue_challan(registration: str, violation: str, fine_inr=None, location: str = "", note: str = "",
                  context: str = "", violation_id: str | None = None) -> dict:
    """Raise a SIMULATED challan for a registry vehicle. Stored locally; never sent anywhere."""
    reg = norm_reg(registration)
    if not in_registry(reg):
        raise Refused(404, f"{reg} is not in the synthetic registry")
    violation = clean(violation, 80)
    if not violation:
        raise Refused(400, "choose a violation")
    try:
        fine = int(fine_inr) if fine_inr not in (None, "") else VIOLATION_FINES.get(violation, 500)
    except (TypeError, ValueError):
        raise Refused(400, "fine must be a whole number of rupees")
    if not 0 < fine <= 100000:
        raise Refused(400, "fine must be between ₹1 and ₹1,00,000")
    c = {"challan_id": f"SYN-SIM-{uuid.uuid4().hex[:8].upper()}", "registration_number": reg, "violation": violation,
         "date": datetime.now().isoformat(timespec="minutes"), "location": clean(location, 120) or "Not stated",
         "fine_inr": fine, "status": "Pending", "note": clean(note, 300) or None, "context": clean(context, 80) or None,
         "violation_id": violation_id, "source": "simulated_issued",
         "issuing_authority": "TraceVision demo (simulated, not sent anywhere)"}
    with _lock:
        items = issued_challans()
        if violation_id:
            items = [x for x in items if x.get("violation_id") != violation_id]
        items.append(c)
        _save_issued(items)
    audit({"action": "issue challan", "registration": reg, "outcome": c["challan_id"], "note": c["note"],
           "context": c["context"] or violation_id, "violation": violation, "fine_inr": fine})
    return c


def cancel_challan(challan_id: str) -> dict:
    with _lock:
        items = issued_challans()
        hit = next((x for x in items if x["challan_id"] == challan_id), None)
        if not hit:
            raise Refused(404, "only simulated challans raised here can be cancelled")
        _save_issued([x for x in items if x["challan_id"] != challan_id])
    audit({"action": "cancel challan", "registration": hit["registration_number"], "outcome": challan_id})
    return hit


def cancel_for_violation(violation_id: str):
    with _lock:
        items = issued_challans()
        keep = [x for x in items if x.get("violation_id") != violation_id]
        if len(keep) != len(items):
            _save_issued(keep)


# ---------------------------------------------------------------- audit
def audit(event: dict):
    event = {"at": datetime.now().isoformat(timespec="seconds"), **event}
    with _lock:
        AUDIT.parent.mkdir(parents=True, exist_ok=True)
        with open(AUDIT, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")


def audit_log(limit: int = 200) -> list:
    try:
        lines = AUDIT.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in reversed(lines[-limit:]):
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


# ---------------------------------------------------------------- lookup
def _status(day: str, today: date) -> dict:
    try:
        d = date.fromisoformat(day)
    except (TypeError, ValueError):
        return {"until": day, "state": "unknown", "days_left": None}
    left = (d - today).days
    return {"until": day, "state": "valid" if left >= 30 else "expiring" if left >= 0 else "expired", "days_left": left}


def lookup(registration: str, reason: str = "", context: str = "", today: date | None = None) -> dict:
    """Everything on record for a registration: vehicle, owner, compliance, e-challans (incl. simulated ones)."""
    reg = norm_reg(registration)
    base = {"registration": reg, "reason": reason or None, "context": context or None, "action": "lookup"}
    t = _tables()
    veh = t["by_reg"].get(reg)
    if veh is None:
        audit({**base, "outcome": "not found"})
        raise Refused(404, f"{reg} is not in the synthetic registry")
    own = t["owners"].get(veh["synthetic_vehicle_id"], {})
    today = today or date.today()
    history = sorted(t["challans"].get(reg, []), key=lambda c: c["date"], reverse=True)
    issued = sorted((c for c in issued_challans() if c.get("registration_number") == reg), key=lambda c: c["date"], reverse=True)
    keys = ("challan_id", "violation", "date", "location", "status", "issuing_authority", "source", "note")
    challans = [{k: c.get(k) for k in keys} | {"fine_inr": int(c["fine_inr"])} for c in issued + history]
    pending = [c for c in challans if c["status"] != "Paid"]
    rec = {
        "synthetic": True,
        "notice": "Synthetic demo data. Not a VAHAN or e-Challan lookup.",
        "vehicle": {
            "registration_number": reg, "synthetic_vehicle_id": veh["synthetic_vehicle_id"],
            "manufacturer": veh.get("manufacturer"), "model": veh.get("model"), "model_year": veh.get("model_year"),
            "vehicle_type": veh.get("vehicle_type"), "colour": veh.get("vehicle_colour"),
            "vehicle_class": own.get("vehicle_class"), "fuel_type": own.get("fuel_type"),
            "rto": own.get("rto_name"), "registration_date": own.get("registration_date"),
        },
        "compliance": {
            "registration": _status(own.get("registration_valid_until"), today),
            "insurance": _status(own.get("insurance_valid_until"), today),
            "puc": _status(own.get("puc_valid_until"), today),
        },
        "owner": {"name": own.get("owner_name"), "type": own.get("owner_type"), "serial": int(own.get("owner_serial") or 1)},
        "challan_summary": {"total": len(challans), "pending": len(pending),
                            "pending_amount_inr": sum(c["fine_inr"] for c in pending)},
        "challans": challans,
    }
    audit({**base, "outcome": "ok"})
    return rec
