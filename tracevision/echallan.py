"""E-Challan Case Management Workflow for TRACEVISION AI (Part 6).

Implements an auditable, legal-standard case management system for traffic enforcement:
- Distinct lifecycle: Draft -> Pending Review -> Approved -> Issued -> Paid / Disputed / Cancelled.
- Duplicate-event prevention (time-window & location consolidation).
- Human officer approval gate: no automatic issuance without authorized review.
- Support for correction, cancellation, dispute filing, and appeal resolution.
- Exportable digital draft and formal case ledger.
- Clear DEMO / SIMULATED marking complying with safety guidelines.
"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from . import ROOT

ECHALLAN_DB = ROOT / "runs" / "enforcement" / "echallan_cases.json"
_lock = threading.Lock()

# Status Enums
STATUS_DRAFT = "draft"
STATUS_PENDING_REVIEW = "pending_review"
STATUS_APPROVED = "approved"
STATUS_ISSUED = "issued"
STATUS_PAID = "paid"
STATUS_DISPUTED = "disputed"
STATUS_CANCELLED = "cancelled"

LEGAL_PROVISIONS = {
    "Wrong-side driving": {
        "rule": "Section 184 (Dangerous Driving) & Section 177 Motor Vehicles Act 1988",
        "standard_fine_inr": 1000,
        "court_appearance_required": False
    },
    "Illegal parking": {
        "rule": "Section 122/177 Motor Vehicles Act 1988",
        "standard_fine_inr": 500,
        "court_appearance_required": False
    },
    "Tow-away obstruction": {
        "rule": "Section 127/177 Motor Vehicles Act 1988",
        "standard_fine_inr": 1000,
        "court_appearance_required": False
    },
    "Emergency route obstruction": {
        "rule": "Section 179 Motor Vehicles Act 1988 (Disobedience of orders)",
        "standard_fine_inr": 2000,
        "court_appearance_required": False
    },
    "Red light violation": {
        "rule": "Section 184(c) Motor Vehicles Act 1988",
        "standard_fine_inr": 1000,
        "court_appearance_required": False
    },
    "Over-speeding": {
        "rule": "Section 112/183 Motor Vehicles Act 1988",
        "standard_fine_inr": 2000,
        "court_appearance_required": False
    },
    "Riding without helmet": {
        "rule": "Section 129/194D Motor Vehicles Act 1988",
        "standard_fine_inr": 1000,
        "court_appearance_required": False
    },
    "Using mobile phone while driving": {
        "rule": "Section 184 Motor Vehicles Act 1988",
        "standard_fine_inr": 5000,
        "court_appearance_required": True
    }
}


DUPLICATE_WINDOW_MINUTES = 30
REG_RE = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{0,3}[0-9]{1,4}$|^[0-9]{2}BH[0-9]{4}[A-Z]{1,2}$")
MAX_FINE_INR = 100000


def load_cases() -> List[Dict[str, Any]]:
    if not ECHALLAN_DB.exists():
        return []
    try:
        data = json.loads(ECHALLAN_DB.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_cases(cases: List[Dict[str, Any]]) -> None:
    """Atomic write: a crash mid-write must not truncate the case ledger."""
    ECHALLAN_DB.parent.mkdir(parents=True, exist_ok=True)
    tmp = ECHALLAN_DB.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=2)
    os.replace(tmp, ECHALLAN_DB)


def _require_officer(officer: str, action: str) -> str:
    o = (officer or "").strip()
    if not o or o.upper().startswith(("SYSTEM", "AUTO")):
        raise ValueError(f"{action} needs a named human officer.")
    return o[:60]


def _find(cases, case_id):
    case = next((c for c in cases if c.get("case_id") == case_id), None)
    if not case:
        raise ValueError(f"Case '{case_id}' not found.")
    return case


def is_duplicate_violation(
    registration: str,
    violation_category: str,
    location: str,
    timestamp_str: str,
    window_minutes: int = DUPLICATE_WINDOW_MINUTES,
    cases: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Checks if a similar violation for the same vehicle was recorded within the duplicate prevention window."""
    cases = load_cases() if cases is None else cases
    try:
        current_dt = datetime.fromisoformat(timestamp_str)
    except Exception:
        current_dt = datetime.now()

    for c in cases:
        if c.get("registration_number") == registration and c.get("violation_category") == violation_category:
            if c.get("status") not in (STATUS_CANCELLED,):
                try:
                    c_dt = datetime.fromisoformat(c.get("timestamp"))
                    if abs((current_dt - c_dt).total_seconds()) < window_minutes * 60:
                        return c
                except Exception:
                    continue
    return None


def create_echallan_draft(
    registration: str,
    violation_category: str,
    location: str,
    evidence_run: str,
    track_id: int,
    ocr_plate: Optional[str],
    ocr_confidence: Optional[float],
    vehicle_type: Optional[str],
    vehicle_colour: Optional[str],
    evidence_frames: Optional[List[int]],
    fine_amount: Optional[int] = None,
    officer_id: str = "OFFICER_FIELD_AI",
    notes: str = ""
) -> Dict[str, Any]:
    """Creates a new draft e-challan with duplicate prevention and legal grounding.

    Evidence fields that are not known stay None: a draft never carries an invented OCR confidence or frame list.
    """
    now_iso = datetime.now().isoformat(timespec="seconds")
    registration = re.sub(r"[^A-Z0-9]", "", str(registration or "").upper())
    if not REG_RE.match(registration):
        raise ValueError(f"'{registration or '(empty)'}' is not a valid Indian registration number.")
    if fine_amount is not None:
        try:
            fine_amount = int(fine_amount)
        except (TypeError, ValueError):
            raise ValueError("fine_inr must be a whole number of rupees.")
        if not 0 < fine_amount <= MAX_FINE_INR:
            raise ValueError(f"fine_inr must be between 1 and {MAX_FINE_INR}.")
    if ocr_confidence is not None:
        ocr_confidence = float(ocr_confidence)
        if not 0.0 <= ocr_confidence <= 1.0:
            raise ValueError("ocr_confidence must be between 0 and 1.")
    if evidence_frames is not None:
        evidence_frames = [int(f) for f in evidence_frames][:50]

    legal_info = LEGAL_PROVISIONS.get(violation_category, {
        "rule": "Section 177 Motor Vehicles Act 1988 (General offences)",
        "standard_fine_inr": 500,
        "court_appearance_required": False
    })

    case_id = f"ECH-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    final_fine = fine_amount if fine_amount is not None else legal_info["standard_fine_inr"]

    new_case = {
        "case_id": case_id,
        "status": STATUS_DRAFT,
        "verification_status": "unverified",
        "registration_number": registration,
        "violation_category": violation_category,
        "legal_provision": legal_info["rule"],
        "court_appearance_required": legal_info["court_appearance_required"],
        "location": location,
        "timestamp": now_iso,
        "fine_inr": final_fine,
        "payment_status": "unpaid",
        "reviewing_officer": officer_id,
        "vehicle_attributes": {
            "type": vehicle_type,
            "colour": vehicle_colour,
            "ocr_plate": ocr_plate,
            "ocr_confidence": round(ocr_confidence, 3) if ocr_confidence is not None else None
        },
        "evidence_reference": {
            "run_id": evidence_run,
            "track_id": track_id,
            "frames": evidence_frames,
            "viewer_link": f"/viewer/{evidence_run}" if evidence_run else None
        },
        "notes": notes,
        "dispute_record": None,
        "audit_history": [
            {
                "timestamp": now_iso,
                "action": "DRAFT_CREATED",
                "officer": officer_id,
                "details": f"Created automated draft for {violation_category}"
            }
        ],
        "is_simulated": True,
        "legal_notice": "DEMO / SIMULATED E-CHALLAN: Created within Hackathon evaluation environment. Not a real government summons."
    }

    with _lock:   # check and insert under one lock: two simultaneous requests cannot both pass the duplicate check
        cases = load_cases()
        dup = is_duplicate_violation(registration, violation_category, location, now_iso, cases=cases)
        if dup:
            raise ValueError(
                f"DUPLICATE VIOLATION REJECTED: Vehicle {registration} already has an active case "
                f"({dup['case_id']}) for '{violation_category}' within the {DUPLICATE_WINDOW_MINUTES}-minute window."
            )
        cases.append(new_case)
        save_cases(cases)

    return new_case


def submit_for_review(case_id: str, officer: str, notes: str = "") -> Dict[str, Any]:
    """Draft -> pending_review: a field officer has checked that the evidence shows the vehicle and the violation."""
    officer = _require_officer(officer, "Evidence verification")
    with _lock:
        cases = load_cases()
        case = _find(cases, case_id)
        if case["status"] != STATUS_DRAFT:
            raise ValueError(f"Only drafts can be sent for review (this case is '{case['status']}').")
        now_iso = datetime.now().isoformat(timespec="seconds")
        case["status"] = STATUS_PENDING_REVIEW
        case["verification_status"] = "evidence_verified"
        case["verified_by"] = officer
        case["verified_at"] = now_iso
        case["audit_history"].append({"timestamp": now_iso, "action": "EVIDENCE_VERIFIED", "officer": officer,
                                      "details": notes or "Evidence frames reviewed; sent for authorised approval."})
        save_cases(cases)
        return case


def record_payment(case_id: str, reference: str = "", officer: str = "PAYMENT_DESK") -> Dict[str, Any]:
    """Issued -> paid (SIMULATED: no payment gateway is connected)."""
    with _lock:
        cases = load_cases()
        case = _find(cases, case_id)
        if case["status"] != STATUS_ISSUED:
            raise ValueError(f"Only issued challans can be paid (this case is '{case['status']}').")
        now_iso = datetime.now().isoformat(timespec="seconds")
        case["status"] = STATUS_PAID
        case["payment_status"] = "paid_simulated"
        case["paid_at"] = now_iso
        case["payment_reference"] = (reference or f"SIM-{uuid.uuid4().hex[:8].upper()}")[:40]
        case["audit_history"].append({"timestamp": now_iso, "action": "PAYMENT_RECORDED_SIMULATED", "officer": officer,
                                      "details": f"Simulated payment {case['payment_reference']} (no gateway connected)."})
        save_cases(cases)
        return case


def approve_and_issue_echallan(
    case_id: str,
    approving_officer: str,
    approval_notes: str = ""
) -> Dict[str, Any]:
    """Human officer approves and formally issues the e-challan (SIMULATED issuance: nothing leaves this machine).

    Allowed from 'draft' (the approving officer then also attests the evidence check, logged as such) or from
    'pending_review'. Never from cancelled / disputed / paid / issued cases."""
    approving_officer = _require_officer(approving_officer, "Approval")
    with _lock:
        cases = load_cases()
        case = _find(cases, case_id)

        if case["status"] in (STATUS_ISSUED, STATUS_PAID):
            raise ValueError(f"Case '{case_id}' is already issued.")
        if case["status"] not in (STATUS_DRAFT, STATUS_PENDING_REVIEW, STATUS_APPROVED):
            raise ValueError(f"Case '{case_id}' is '{case['status']}' and cannot be approved.")

        now_iso = datetime.now().isoformat(timespec="seconds")
        if case["status"] == STATUS_DRAFT:
            case["verified_by"] = approving_officer
            case["verified_at"] = now_iso
            case["audit_history"].append({"timestamp": now_iso, "action": "EVIDENCE_VERIFIED", "officer": approving_officer,
                                          "details": "Evidence verified by the approving officer at approval."})
        case["status"] = STATUS_ISSUED
        case["verification_status"] = "verified_human"
        case["approved_by"] = approving_officer
        case["issued_at"] = now_iso

        case["audit_history"].append({
            "timestamp": now_iso,
            "action": "HUMAN_APPROVAL_AND_ISSUANCE",
            "officer": approving_officer,
            "details": approval_notes or f"Approved by officer {approving_officer} after reviewing visual evidence."
        })

        save_cases(cases)
        return case


def cancel_echallan(
    case_id: str,
    officer: str,
    cancellation_reason: str
) -> Dict[str, Any]:
    """Cancels an e-challan with mandatory cancellation reasoning."""
    if not (cancellation_reason or "").strip():
        raise ValueError("Cancellation reason is mandatory.")
    officer = _require_officer(officer, "Cancellation")

    with _lock:
        cases = load_cases()
        case = _find(cases, case_id)
        if case["status"] in (STATUS_CANCELLED, STATUS_PAID):
            raise ValueError(f"Case '{case_id}' is '{case['status']}' and cannot be cancelled.")

        now_iso = datetime.now().isoformat(timespec="seconds")
        case["status"] = STATUS_CANCELLED
        case["cancellation_reason"] = cancellation_reason
        case["cancelled_by"] = officer
        case["cancelled_at"] = now_iso

        case["audit_history"].append({
            "timestamp": now_iso,
            "action": "CASE_CANCELLED",
            "officer": officer,
            "details": f"Cancelled: {cancellation_reason}"
        })

        save_cases(cases)
        return case


def file_echallan_dispute(
    case_id: str,
    citizen_reason: str,
    evidence_url: Optional[str] = None
) -> Dict[str, Any]:
    """Files a formal dispute / contest against an issued e-challan."""
    with _lock:
        cases = load_cases()
        case = next((c for c in cases if c["case_id"] == case_id), None)
        if not case:
            raise ValueError(f"Case '{case_id}' not found.")

        if case["status"] != STATUS_ISSUED:
            raise ValueError("Only issued challans can be disputed.")
        if not (citizen_reason or "").strip():
            raise ValueError("A dispute needs a reason.")
        citizen_reason = citizen_reason.strip()[:500]

        now_iso = datetime.now().isoformat(timespec="seconds")
        case["status"] = STATUS_DISPUTED
        case["dispute_record"] = {
            "dispute_id": f"DSP-{uuid.uuid4().hex[:6].upper()}",
            "filed_at": now_iso,
            "reason": citizen_reason,
            "evidence_attachment": evidence_url,
            "status": "under_investigation"
        }

        case["audit_history"].append({
            "timestamp": now_iso,
            "action": "DISPUTE_FILED",
            "officer": "CITIZEN_DISPUTE_PORTAL",
            "details": f"Dispute submitted: {citizen_reason}"
        })

        save_cases(cases)
        return case


def resolve_echallan_dispute(
    case_id: str,
    officer: str,
    resolution: str,  # 'upheld' (challan cancelled) or 'dismissed' (challan stands)
    officer_findings: str
) -> Dict[str, Any]:
    """Adjudicates a citizen dispute with full audit trail."""
    if resolution not in ("upheld", "dismissed"):
        raise ValueError("resolution must be 'upheld' or 'dismissed'.")
    officer = _require_officer(officer, "Dispute adjudication")
    with _lock:
        cases = load_cases()
        case = next((c for c in cases if c.get("case_id") == case_id), None)
        if not case or not case.get("dispute_record") or case.get("status") != STATUS_DISPUTED:
            raise ValueError(f"No active dispute found for case '{case_id}'.")

        now_iso = datetime.now().isoformat(timespec="seconds")
        case["dispute_record"]["adjudicated_at"] = now_iso
        case["dispute_record"]["adjudicated_by"] = officer
        case["dispute_record"]["resolution"] = resolution
        case["dispute_record"]["findings"] = officer_findings

        case["dispute_record"]["status"] = "resolved"
        if resolution == "upheld":
            case["status"] = STATUS_CANCELLED
            case["cancellation_reason"] = f"Dispute upheld by officer: {officer_findings}"
        else:
            case["status"] = STATUS_ISSUED

        case["audit_history"].append({
            "timestamp": now_iso,
            "action": f"DISPUTE_{resolution.upper()}",
            "officer": officer,
            "details": f"Findings: {officer_findings}"
        })

        save_cases(cases)
        return case

