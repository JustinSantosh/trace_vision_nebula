"""Vehicle intelligence (registered-owner record + e-challan history) behind role checks and an audit log.

SYNTHETIC DEMO DATA ONLY (DECISIONS E17). The records come from registry/synthetic_owner_records.csv and
registry/synthetic_echallans.csv (TRACEVISION_DATA/scripts/generate_vehicle_intel.py). No VAHAN / e-Challan
service is queried.

Roles (what a lookup returns)
  analyst       vehicle particulars and compliance status; owner name masked; challan totals only
  investigator  + owner name and the full challan list; a stated reason is required
  officer       same as investigator, plus reviewing violations and reading the audit log

Every lookup, allowed or refused, is appended to runs/audit/lookups.jsonl.

The role arrives in a request header and is NOT authenticated: this shows the access model, it is not access control.
A deployment would take the role from the identity provider instead.
"""
from __future__ import annotations

import csv
import json
import re
import threading
from datetime import date, datetime
from pathlib import Path

from . import ROOT

REG_DIR = ROOT / "TRACEVISION_DATA" / "registry"
AUDIT = ROOT / "runs" / "audit" / "lookups.jsonl"
ISSUED = ROOT / "runs" / "enforcement" / "issued_challans.json"
ROLES = {
    "analyst": {"label": "Analyst", "owner": False, "challans": False, "review": False, "audit": False},
    "investigator": {"label": "Investigator", "owner": True, "challans": True, "review": False, "audit": False},
    "officer": {"label": "Traffic officer", "owner": True, "challans": True, "review": True, "audit": True},
}
REASONS = ["Active investigation", "Violation review", "Stolen vehicle check", "Court / legal request", "Training / demo"]
_lock = threading.Lock()
_cache: dict = {}


class Refused(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def role_of(raw: str | None) -> str:
    r = (raw or "analyst").strip().lower()
    if r not in ROLES:
        raise Refused(400, f"unknown role {raw!r}; use one of {sorted(ROLES)}")
    return r


def clean_user(raw: str | None) -> str:
    u = re.sub(r"[^\w .@-]", "", (raw or "").strip())[:40]
    return u or "anonymous"


def _tables():
    paths = [REG_DIR / n for n in ("synthetic_vehicle_registry.csv", "synthetic_owner_records.csv", "synthetic_echallans.csv")]
    stamp = tuple(p.stat().st_mtime if p.exists() else 0 for p in paths)
    if _cache.get("stamp") != stamp:
        def rows(p):
            return list(csv.DictReader(open(p, encoding="utf-8"))) if p.exists() else []
        reg, own, ch = (rows(p) for p in paths)
        by_reg = {r["registration_number"]: r for r in reg}
        owners = {r["synthetic_vehicle_id"]: r for r in own}
        challans: dict[str, list] = {}
        for c in ch:
            challans.setdefault(c["registration_number"], []).append(c)
        _cache.update(stamp=stamp, by_reg=by_reg, owners=owners, challans=challans)
    return _cache


def available() -> bool:
    return bool(_tables()["owners"])


def issued_challans() -> list:
    try:
        return json.loads(ISSUED.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def add_issued_challan(entry: dict):
    with _lock:
        items = issued_challans()
        items = [c for c in items if c.get("violation_id") != entry.get("violation_id")]
        items.append(entry)
        ISSUED.parent.mkdir(parents=True, exist_ok=True)
        ISSUED.write_text(json.dumps(items, indent=1), encoding="utf-8")


def remove_issued_challan(violation_id: str):
    with _lock:
        items = [c for c in issued_challans() if c.get("violation_id") != violation_id]
        ISSUED.parent.mkdir(parents=True, exist_ok=True)
        ISSUED.write_text(json.dumps(items, indent=1), encoding="utf-8")


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


def _status(day: str, today: date) -> dict:
    try:
        d = date.fromisoformat(day)
    except (TypeError, ValueError):
        return {"until": day, "state": "unknown", "days_left": None}
    left = (d - today).days
    return {"until": day, "state": "valid" if left >= 30 else "expiring" if left >= 0 else "expired", "days_left": left}


def lookup(registration: str, role: str, user: str, reason: str = "", context: str = "", today: date | None = None) -> dict:
    """Role-filtered vehicle record. Raises Refused (and audits the refusal) when the request is not allowed."""
    reg = re.sub(r"[^A-Z0-9]", "", (registration or "").upper())
    perms = ROLES[role]
    base = {"user": user, "role": role, "registration": reg, "reason": reason or None, "context": context or None}
    if perms["owner"] and not reason.strip():
        audit({**base, "action": "lookup", "outcome": "refused: no reason given"})
        raise Refused(400, "a reason is required for an owner / challan lookup")
    t = _tables()
    veh = t["by_reg"].get(reg)
    if veh is None:
        audit({**base, "action": "lookup", "outcome": "not found"})
        raise Refused(404, f"{reg} is not in the synthetic registry")
    own = t["owners"].get(veh["synthetic_vehicle_id"], {})
    today = today or date.today()
    history = sorted(t["challans"].get(reg, []), key=lambda c: c["date"], reverse=True)
    issued = [c for c in issued_challans() if c.get("registration_number") == reg]
    challans = [{k: c[k] for k in ("challan_id", "violation", "date", "location", "status", "issuing_authority", "source")}
                | {"fine_inr": int(c["fine_inr"])} for c in issued + history]
    pending = [c for c in challans if c["status"] != "Paid"]
    rec = {
        "synthetic": True,
        "notice": "Synthetic demo data. Not a VAHAN or e-Challan lookup.",
        "role": role,
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
        "owner": ({"name": own.get("owner_name"), "type": own.get("owner_type"), "serial": int(own.get("owner_serial") or 1)}
                  if perms["owner"] else {"name": own.get("owner_name_masked"), "masked": True}),
        "challan_summary": {"total": len(challans), "pending": len(pending),
                            "pending_amount_inr": sum(c["fine_inr"] for c in pending)},
        "challans": challans if perms["challans"] else None,
    }
    audit({**base, "action": "lookup", "outcome": "ok",
           "fields": "vehicle+owner+challans" if perms["owner"] else "vehicle (owner masked)"})
    return rec
