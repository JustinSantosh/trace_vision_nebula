"""Illegal Parking Detection and Owner Warning Workflow for TRACEVISION AI (Part 5).

Implements an evidence-based parking violation system:
- Distinguishes legal parking, temporary stopping, signal waiting, traffic congestion,
  illegal parking, and emergency access obstruction.
- Camera-specific zone polygons (no_parking, tow_away, emergency_access, legal_parking).
- Track continuity validation: never assumes unbroken dwell across observation gaps.
- Full State Machine:
  Detected -> Pending Verification -> Verified Violation -> Owner Notification Pending ->
  Warning Sent -> Vehicle Moved / Violation Unresolved -> E-Challan Pending ->
  E-Challan Issued / Towing Authorised -> Closed / Disputed / Towed.
- Owner Warning System before towing: generates auditable warning notices with
  time limits, evidence frames, RTO details, and appeal procedures.
"""

from __future__ import annotations

import csv
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime
from math import hypot
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from . import ROOT

PARKING_RULES_FILE = ROOT / "TRACEVISION_DATA" / "cameras" / "parking_rules.json"
PARKING_CASES_FILE = ROOT / "runs" / "enforcement" / "parking_cases.json"
_lock = threading.Lock()

# State Machine Constants
STATE_DETECTED = "detected"
STATE_PENDING_VERIFICATION = "pending_verification"
STATE_VERIFIED = "verified_violation"
STATE_WARNING_PENDING = "owner_notification_pending"
STATE_WARNING_SENT = "warning_sent"
STATE_VEHICLE_MOVED = "vehicle_moved"
STATE_UNRESOLVED = "violation_unresolved"
STATE_ECHALLAN_PENDING = "echallan_pending"
STATE_ECHALLAN_ISSUED = "echallan_issued"
STATE_TOWING_AUTHORISED = "towing_authorised"
STATE_CLOSED = "closed"
STATE_DISPUTED = "disputed"
STATE_TOWED = "towed"

VALID_TRANSITIONS = {
    STATE_DETECTED: {STATE_PENDING_VERIFICATION, STATE_CLOSED},
    STATE_PENDING_VERIFICATION: {STATE_VERIFIED, STATE_CLOSED},
    STATE_VERIFIED: {STATE_WARNING_PENDING, STATE_ECHALLAN_PENDING, STATE_CLOSED},
    STATE_WARNING_PENDING: {STATE_WARNING_SENT, STATE_CLOSED},
    STATE_WARNING_SENT: {STATE_VEHICLE_MOVED, STATE_UNRESOLVED, STATE_DISPUTED},
    STATE_VEHICLE_MOVED: {STATE_CLOSED},
    STATE_UNRESOLVED: {STATE_ECHALLAN_PENDING, STATE_TOWING_AUTHORISED, STATE_DISPUTED, STATE_CLOSED},
    STATE_ECHALLAN_PENDING: {STATE_ECHALLAN_ISSUED, STATE_CLOSED, STATE_DISPUTED},
    STATE_ECHALLAN_ISSUED: {STATE_CLOSED, STATE_DISPUTED},
    STATE_TOWING_AUTHORISED: {STATE_TOWED, STATE_VEHICLE_MOVED, STATE_CLOSED, STATE_DISPUTED},
    STATE_DISPUTED: {STATE_CLOSED, STATE_UNRESOLVED, STATE_ECHALLAN_PENDING},
    STATE_CLOSED: set(),
    STATE_TOWED: {STATE_CLOSED},
}

# Standard official fine schedules (Motor Vehicles Act sections)
PARKING_VIOLATIONS = {
    "no_parking": {
        "title": "Illegal Parking in Designated No-Parking Zone",
        "section": "Section 122/177 Motor Vehicles Act 1988",
        "fine_inr": 500,
        "default_grace_minutes": 10,
        "towing_eligible": True,
    },
    "tow_away": {
        "title": "Obstruction in Declared Tow-Away Zone",
        "section": "Section 127/177 Motor Vehicles Act 1988",
        "fine_inr": 1000,
        "default_grace_minutes": 5,
        "towing_eligible": True,
    },
    "emergency_access": {
        "title": "Obstruction of Emergency Access / Fire Route",
        "section": "Section 122/177/179 Motor Vehicles Act 1988",
        "fine_inr": 2000,
        "default_grace_minutes": 3,
        "towing_eligible": True,
    },
}

DEFAULT_OFFICIAL_CONTACTS = {
    "control_room": "Traffic Police Control Room: 1095 / 011-2584-4444",
    "helpline": "Emergency Highway Helpline: 1033",
    "appeal_portal": "https://echallan.parivahan.gov.in/gstn/dispute",
}


def inside_polygon(pt: Tuple[float, float], poly: List[List[float]]) -> bool:
    """Ray casting algorithm for point in polygon."""
    x, y, hit = pt[0], pt[1], False
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[i - 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def load_parking_rules() -> Dict[str, Any]:
    if not PARKING_RULES_FILE.exists():
        # Default camera parking rules template
        return {
            "cameras": {
                "cam_parking_pair1_a": {
                    "description": "Commercial parking bay with clearway lane",
                    "zones": [
                        {
                            "name": "Designated Parking Bay 1",
                            "type": "legal_parking",
                            "polygon": [[0.15, 0.20], [0.85, 0.20], [0.85, 0.95], [0.15, 0.95]],
                            "dwell_limit_s": 7200
                        }
                    ]
                },
                "cam_fixed_overpass_01": {
                    "description": "Highway overpass with emergency shoulder",
                    "zones": [
                        {
                            "name": "Overpass Emergency Shoulder",
                            "type": "emergency_access",
                            "polygon": [[0.0, 0.60], [0.25, 0.60], [0.25, 1.0], [0.0, 1.0]],
                            "dwell_limit_s": 30
                        },
                        {
                            "name": "Overpass Kerbside No Parking",
                            "type": "no_parking",
                            "polygon": [[0.75, 0.45], [1.0, 0.45], [1.0, 1.0], [0.75, 1.0]],
                            "dwell_limit_s": 60
                        }
                    ]
                }
            }
        }
    try:
        return json.loads(PARKING_RULES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"cameras": {}}


def load_parking_cases() -> List[Dict[str, Any]]:
    if not PARKING_CASES_FILE.exists():
        return []
    try:
        data = json.loads(PARKING_CASES_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_parking_cases(cases: List[Dict[str, Any]]) -> None:
    """Atomic write: a crash mid-write must not truncate the case ledger."""
    PARKING_CASES_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = PARKING_CASES_FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=2)
    os.replace(tmp, PARKING_CASES_FILE)


# Transitions that act on a person's property or liability: they need a named human officer and a written reason.
HUMAN_ONLY_STATES = {"towing_authorised", "towed", "echallan_issued", "verified_violation", "violation_unresolved"}
SYSTEM_ACTORS = ("SYSTEM", "AUTO", "")


def _is_human(officer: str) -> bool:
    o = (officer or "").strip().upper()
    return bool(o) and not any(o.startswith(s) for s in SYSTEM_ACTORS if s)


def analyze_track_parking(
    track: List[List[float]],
    zones: List[Dict[str, Any]],
    fps: float,
    width: int,
    height: int,
    congestion_threshold: float = 0.05,
    scene_stationary_share: Optional[float] = None,
    congestion_share: float = 0.6,
) -> Optional[Dict[str, Any]]:
    """Analyzes a vehicle track for parking violation, legal parking, or congestion.

    scene_stationary_share: optional share of the OTHER tracked vehicles in the scene that are stationary over the
    same interval. When most of the scene is stopped (>= congestion_share), a stationary vehicle is classified as
    traffic congestion / signal queue, never as illegal parking.
    """
    if not track or len(track) < 5 or not fps or fps <= 0 or not width or not height:
        return None

    # Track format: [[frame, x1, y1, x2, y2], ...]
    first_frame = int(track[0][0])
    last_frame = int(track[-1][0])
    duration_s = (last_frame - first_frame) / fps if fps > 0 else 0.0

    # Calculate net displacement and velocity
    bottom_centers = [((p[1] + p[3]) / (2 * width), p[4] / height) for p in track]
    x_coords = [p[0] for p in bottom_centers]
    y_coords = [p[1] for p in bottom_centers]

    bbox_w = (track[0][3] - track[0][1]) / width
    bbox_h = (track[0][4] - track[0][2]) / height
    bbox_diag = hypot(bbox_w, bbox_h)

    # Net movement relative to vehicle bounding box size
    net_disp = hypot(x_coords[-1] - x_coords[0], y_coords[-1] - y_coords[0])
    # Net displacement alone misses a vehicle that drives off and comes back: also bound the largest excursion
    # from the median position (same tolerance), so "stationary" means stationary throughout.
    mx, my = sorted(x_coords)[len(x_coords) // 2], sorted(y_coords)[len(y_coords) // 2]
    max_excursion = max(hypot(x - mx, y - my) for x, y in zip(x_coords, y_coords))
    tol = max(0.04, 0.5 * bbox_diag)
    is_stationary = net_disp < tol and max_excursion < tol

    # Check track continuity: detect observation gaps > 3 seconds
    gaps = []
    for i in range(len(track) - 1):
        f_diff = track[i + 1][0] - track[i][0]
        if f_diff > 3 * fps:
            gaps.append({"gap_frames": f_diff, "gap_s": round(f_diff / fps, 2)})

    continuity_intact = len(gaps) == 0

    # Check which zone vehicle is inside (evaluate median position)
    med_pos = (sorted(x_coords)[len(x_coords) // 2], sorted(y_coords)[len(y_coords) // 2])
    
    matched_zone = None
    for zone in zones:
        if inside_polygon(med_pos, zone["polygon"]):
            matched_zone = zone
            break

    if not matched_zone:
        return None

    zone_type = matched_zone.get("type", "no_parking")
    dwell_limit_s = matched_zone.get("dwell_limit_s", 60)

    # Determine classification
    if zone_type == "legal_parking":
        return {
            "status": "legal_parking",
            "zone_name": matched_zone["name"],
            "zone_type": zone_type,
            "duration_s": round(duration_s, 2),
            "is_stationary": is_stationary,
            "notes": "Vehicle situated within designated legal parking bay."
        }

    if not is_stationary:
        return {
            "status": "in_transit",
            "zone_name": matched_zone["name"],
            "zone_type": zone_type,
            "net_displacement": round(net_disp, 3),
            "notes": "Vehicle moving through zone."
        }

    # Stationary in restricted zone
    if duration_s < 15:
        return {
            "status": "temporary_stopping",
            "zone_name": matched_zone["name"],
            "zone_type": zone_type,
            "duration_s": round(duration_s, 2),
            "notes": "Brief pause below violation threshold (e.g., passenger drop-off)."
        }

    if zone_type == "signal_queue":
        return {
            "status": "signal_waiting",
            "zone_name": matched_zone["name"],
            "zone_type": zone_type,
            "duration_s": round(duration_s, 2),
            "notes": "Stationary in a signal stop-line queue zone: waiting at a signal is not parking."
        }

    if scene_stationary_share is not None and scene_stationary_share >= congestion_share:
        return {
            "status": "traffic_congestion",
            "zone_name": matched_zone["name"],
            "zone_type": zone_type,
            "duration_s": round(duration_s, 2),
            "scene_stationary_share": round(scene_stationary_share, 2),
            "notes": "Most other vehicles in view are also stopped: treated as congestion, not parking."
        }

    if not continuity_intact:
        return {
            "status": "uncertain_gap",
            "zone_name": matched_zone["name"],
            "zone_type": zone_type,
            "duration_s": round(duration_s, 2),
            "gaps": gaps,
            "notes": "Observation interrupted by tracking gaps; continuous dwell cannot be proven."
        }

    if duration_s >= dwell_limit_s:
        v_info = PARKING_VIOLATIONS.get(zone_type, PARKING_VIOLATIONS["no_parking"])
        return {
            "status": "violation",
            "violation_type": zone_type,
            "violation_title": v_info["title"],
            "legal_section": v_info["section"],
            "fine_inr": v_info["fine_inr"],
            "grace_minutes": v_info["default_grace_minutes"],
            "zone_name": matched_zone["name"],
            "zone_type": zone_type,
            "duration_s": round(duration_s, 2),
            "first_frame": first_frame,
            "last_frame": last_frame,
            "median_position": [round(med_pos[0], 3), round(med_pos[1], 3)],
            "continuity_verified": True,
            "requires_human_verification": True,
        }

    return {
        "status": "stationary_below_limit",
        "zone_name": matched_zone["name"],
        "zone_type": zone_type,
        "duration_s": round(duration_s, 2),
        "dwell_limit_s": dwell_limit_s,
        "notes": "Stationary in a restricted zone, but not yet for the zone's dwell limit."
    }


def scan_run(result: Dict[str, Any], camera_id: Optional[str]) -> Dict[str, Any]:
    """Classify every tracked vehicle of one stored result against the camera's parking zones.

    Read-only: proposes findings, never creates a case (an officer does that). Moving / handheld cameras are not
    assessed: image position is relative to the camera there, so 'stationary in the image' proves nothing.
    """
    out = {"camera_id": camera_id, "assessed": False, "findings": [], "zones": []}
    if (result.get("camera_type") or "") != "fixed_cctv_style" and not (camera_id and "fixed" in camera_id):
        out["not_assessed_reason"] = "moving or handheld camera: dwell cannot be measured from image position"
        return out
    cam = (load_parking_rules().get("cameras") or {}).get(camera_id or "")
    if not cam or not cam.get("zones"):
        out["not_assessed_reason"] = "no parking zones are configured for this camera"
        return out
    v = result.get("video") or {}
    fps, W, H = v.get("fps") or 0, v.get("width") or 0, v.get("height") or 0
    out.update(assessed=True, zones=[{"name": z["name"], "type": z.get("type"), "dwell_limit_s": z.get("dwell_limit_s")}
                                     for z in cam["zones"]])
    vehicles = [x for x in result.get("vehicles", []) if x.get("track")]
    first = {x["track_id"]: analyze_track_parking(x["track"], cam["zones"], fps, W, H) for x in vehicles}
    stationary = {k for k, r in first.items() if r and r.get("status") not in (None, "in_transit")}
    for x in vehicles:
        others = [k for k in first if k != x["track_id"]]
        share = (sum(k in stationary for k in others) / len(others)) if len(others) >= 3 else None
        r = analyze_track_parking(x["track"], cam["zones"], fps, W, H, scene_stationary_share=share)
        if r:
            cands = x.get("candidates") or []
            out["findings"].append(r | {"track_id": x["track_id"],
                                        "registration_number": cands[0]["registration_number"]
                                        if x.get("decision") == "match" and cands else None,
                                        "plate": (x.get("plate") or {}).get("fused"),
                                        "vehicle_type": (x.get("type") or {}).get("label"),
                                        "colour": (x.get("colour") or {}).get("label")})
    return out


def create_parking_case(
    run_id: str,
    clip_id: str,
    track_id: int,
    registration: Optional[str],
    vehicle_type: str,
    colour: str,
    analysis_result: Dict[str, Any],
    location: str = "Surveillance Zone",
    evidence_frames: Optional[List[int]] = None
) -> Dict[str, Any]:
    """Creates a new auditable parking violation case under the state machine."""
    case_id = f"PRK-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    v_type = analysis_result.get("violation_type", "no_parking")
    v_spec = PARKING_VIOLATIONS.get(v_type, PARKING_VIOLATIONS["no_parking"])
    grace_m = analysis_result.get("grace_minutes", v_spec["default_grace_minutes"])

    now_iso = datetime.now().isoformat(timespec="seconds")

    case = {
        "case_id": case_id,
        "run_id": run_id,
        "clip_id": clip_id,
        "track_id": track_id,
        "registration_number": registration,
        "vehicle_type": vehicle_type,
        "colour": colour,
        "violation_type": v_type,
        "violation_title": v_spec["title"],
        "legal_section": v_spec["section"],
        "fine_inr": v_spec["fine_inr"],
        "location": location,
        "zone_name": analysis_result.get("zone_name", "Restricted Zone"),
        "dwell_duration_s": analysis_result.get("duration_s", 0),
        "state": STATE_DETECTED,
        "evidence_frames": evidence_frames or [analysis_result.get("first_frame", 0), analysis_result.get("last_frame", 0)],
        "created_at": now_iso,
        "updated_at": now_iso,
        "grace_period_minutes": grace_m,
        "warning_notice": None,
        "towing_authorized": False,
        "officer_notes": [],
        "audit_trail": [
            {
                "timestamp": now_iso,
                "from_state": None,
                "to_state": STATE_DETECTED,
                "action": "Case created by automated detection",
                "officer": "SYSTEM_DETECTOR"
            }
        ]
    }

    with _lock:
        cases = load_parking_cases()
        # Duplicate protection: one open case per vehicle. A vehicle is identified by its registration when there is
        # one, else by the evidence (run + track), so repeated scans of the same clip never stack cases.
        open_ = [c for c in cases if c.get("state") not in (STATE_CLOSED, STATE_VEHICLE_MOVED, STATE_TOWED)]
        existing = [c for c in open_ if (registration and c.get("registration_number") == registration)
                    or (c.get("run_id") == run_id and c.get("track_id") == track_id)]
        if existing:
            return existing[0] | {"duplicate_of_open_case": True}
        cases.append(case)
        save_parking_cases(cases)

    return case


def transition_parking_case(
    case_id: str,
    new_state: str,
    officer: str = "OFFICER_REVIEW",
    note: str = ""
) -> Dict[str, Any]:
    """Applies an auditable state transition with safety checks."""
    with _lock:
        cases = load_parking_cases()
        case = next((c for c in cases if c["case_id"] == case_id), None)
        if not case:
            raise ValueError(f"Parking case '{case_id}' not found.")

        current_state = case["state"]
        if new_state not in VALID_TRANSITIONS:
            raise ValueError(f"Unknown state '{new_state}'.")
        if new_state not in VALID_TRANSITIONS.get(current_state, set()):
            allowed = ", ".join(sorted(VALID_TRANSITIONS.get(current_state, set()))) or "none (case is final)"
            raise ValueError(f"Invalid transition from '{current_state}' to '{new_state}'. Allowed: {allowed}")
        if new_state in HUMAN_ONLY_STATES and not _is_human(officer):
            raise ValueError(f"'{new_state}' needs a named human officer, not '{officer or 'unnamed'}'.")
        if new_state in (STATE_TOWING_AUTHORISED, STATE_TOWED, STATE_ECHALLAN_ISSUED) and not (note or "").strip():
            raise ValueError(f"'{new_state}' needs a written reason from the authorising officer.")

        now_iso = datetime.now().isoformat(timespec="seconds")
        # Recheck after the owner warning: record whether the grace period had actually run out.
        if new_state in (STATE_UNRESOLVED, STATE_VEHICLE_MOVED) and case.get("warning_sent_at"):
            try:
                waited = (datetime.fromisoformat(now_iso) - datetime.fromisoformat(case["warning_sent_at"])).total_seconds()
                case["recheck"] = {"at": now_iso, "seconds_after_warning": int(waited),
                                   "grace_period_elapsed": waited >= 60 * float(case.get("grace_period_minutes") or 0),
                                   "outcome": new_state, "officer": officer}
            except (TypeError, ValueError):
                pass
        if new_state == STATE_WARNING_SENT:
            case["warning_sent_at"] = now_iso
        case["state"] = new_state
        case["updated_at"] = now_iso

        # Special state actions
        if new_state == STATE_WARNING_SENT and not case.get("warning_notice"):
            case["warning_notice"] = generate_owner_warning_notice(case)

        if new_state == STATE_TOWING_AUTHORISED:
            case["towing_authorized"] = True

        if note:
            case["officer_notes"].append({"timestamp": now_iso, "officer": officer, "note": note})

        case["audit_trail"].append({
            "timestamp": now_iso,
            "from_state": current_state,
            "to_state": new_state,
            "action": note or f"Status changed to {new_state}",
            "officer": officer
        })

        save_parking_cases(cases)
        return case


def generate_owner_warning_notice(case: Dict[str, Any]) -> Dict[str, Any]:
    """Generates an official owner pre-towing warning notification (Part 5 requirement)."""
    reg = case.get("registration_number") or "UNREGISTERED / UNREAD"
    grace_min = case.get("grace_period_minutes", 10)
    
    return {
        "notice_id": f"WRN-{case['case_id']}",
        "registration_number": reg,
        "vehicle_description": f"{case.get('colour', '')} {case.get('vehicle_type', 'vehicle')}".strip().title(),
        "violation_title": case.get("violation_title"),
        "legal_rule": case.get("legal_section"),
        "location": case.get("location"),
        "timestamp_observed": case.get("created_at"),
        "dwell_duration_recorded": (f"{round(float(case['dwell_duration_s']) / 60, 1)} minutes"
                                    if isinstance(case.get("dwell_duration_s"), (int, float)) and case["dwell_duration_s"] > 0
                                    else "not measured (officer observation)"),
        "response_period_minutes": grace_min,
        "warning_message": (
            f"NOTICE: Vehicle {reg} has been observed stationary in a restricted zone ({case.get('violation_title')}). "
            f"Please move the vehicle within {grace_min} minutes. If it is still there at the recheck, a traffic "
            f"officer will review the evidence and may raise an e-challan or authorise towing under "
            f"{case.get('legal_section')}. No action is taken automatically."
        ),
        "official_contacts": DEFAULT_OFFICIAL_CONTACTS,
        "status": "SENT_SIMULATED",
        "disclaimer": "DEMO / SIMULATED SYSTEM: Notification recorded locally for testing and audit purposes."
    }

