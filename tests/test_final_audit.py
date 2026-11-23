"""Regression tests added by the final audit (2026-11-23): enforcement workflow guards, evidence integrity, API
validation and the colour-probe loader. All state goes to tmp_path; nothing touches runs/enforcement.

Runs in UI-only mode (no model loading). Needs fastapi + httpx for the API part.
"""
import json
import os

import numpy as np
import pytest

os.environ["TRACEVISION_UI_ONLY"] = "1"
from tracevision import ROOT, colour, echallan, intel, parking  # noqa: E402

pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from tracevision import api  # noqa: E402

api.UI_ONLY = True
client = TestClient(api.app)
JSON = {"Content-Type": "application/json"}


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(parking, "PARKING_CASES_FILE", tmp_path / "parking_cases.json")
    monkeypatch.setattr(echallan, "ECHALLAN_DB", tmp_path / "echallan_cases.json")
    monkeypatch.setattr(intel, "AUDIT", tmp_path / "audit.jsonl", raising=False)


def _case(state_path=()):
    c = parking.create_parking_case("runs/clip02", "clip02", 7, "DL1CAB1234", "car", "white",
                                    {"violation_type": "no_parking", "duration_s": 300, "first_frame": 0, "last_frame": 90})
    for st, who, note in state_path:
        c = parking.transition_parking_case(c["case_id"], st, officer=who, note=note)
    return c


# ---------------------------------------------------------------- parking: analysis
ZONES = [{"name": "Kerb", "type": "no_parking", "polygon": [[0, 0], [1, 0], [1, 1], [0, 1]], "dwell_limit_s": 30},
         {"name": "Stop line", "type": "signal_queue", "polygon": [[0, 0], [0.01, 0], [0.01, 0.01], [0, 0.01]], "dwell_limit_s": 30}]


def test_vehicle_that_leaves_and_returns_is_not_stationary():
    out = [[f, 100 + 6 * f, 100, 200 + 6 * f, 200] for f in range(0, 60, 5)]
    back = [[f, 100 + 6 * (120 - f), 100, 200 + 6 * (120 - f), 200] for f in range(60, 125, 5)]
    r = parking.analyze_track_parking(out + back, ZONES[:1], fps=2.0, width=1000, height=1000)
    assert r["status"] == "in_transit"          # net displacement ~0, but it drove away and back


def test_congested_scene_is_not_parking():
    track = [[f, 100, 100, 200, 200] for f in range(0, 2000, 25)]
    r = parking.analyze_track_parking(track, ZONES[:1], fps=25.0, width=1000, height=1000, scene_stationary_share=0.8)
    assert r["status"] == "traffic_congestion"


def test_stationary_below_dwell_limit_is_reported_not_flagged():
    track = [[f, 100, 100, 200, 200] for f in range(0, 500, 25)]        # 19 s < 30 s limit
    r = parking.analyze_track_parking(track, ZONES[:1], fps=25.0, width=1000, height=1000)
    assert r["status"] == "stationary_below_limit"


def test_bad_video_metadata_returns_none_instead_of_crashing():
    track = [[f, 100, 100, 200, 200] for f in range(0, 500, 25)]
    assert parking.analyze_track_parking(track, ZONES, fps=0, width=1000, height=1000) is None
    assert parking.analyze_track_parking(track, ZONES, fps=25, width=0, height=1000) is None


def test_moving_camera_runs_are_not_assessed_for_parking():
    res = json.loads((ROOT / "runs" / "clip12" / "result.json").read_text(encoding="utf-8"))
    out = parking.scan_run(res, "cam_parking_pair1_a")
    assert out["assessed"] is False and "moving" in out["not_assessed_reason"]


# ---------------------------------------------------------------- parking: workflow guards
def test_towing_needs_named_officer_and_reason_and_follows_the_warning():
    c = _case([("pending_verification", "SGT_A", ""), ("verified_violation", "INSP_B", "")])
    with pytest.raises(ValueError, match="Invalid transition"):          # no towing before warning + recheck
        parking.transition_parking_case(c["case_id"], "towing_authorised", officer="INSP_B", note="x")
    c = parking.transition_parking_case(c["case_id"], "owner_notification_pending", officer="INSP_B")
    c = parking.transition_parking_case(c["case_id"], "warning_sent", officer="INSP_B")
    assert c["warning_sent_at"] and c["warning_notice"]
    assert "automated" not in c["warning_notice"]["warning_message"].lower()
    c = parking.transition_parking_case(c["case_id"], "violation_unresolved", officer="INSP_B", note="still there")
    assert c["recheck"]["grace_period_elapsed"] is False                # recorded honestly
    with pytest.raises(ValueError, match="human officer"):
        parking.transition_parking_case(c["case_id"], "towing_authorised", officer="SYSTEM_DETECTOR", note="x")
    with pytest.raises(ValueError, match="written reason"):
        parking.transition_parking_case(c["case_id"], "towing_authorised", officer="INSP_B", note="")
    c = parking.transition_parking_case(c["case_id"], "towing_authorised", officer="INSP_B", note="blocking fire lane")
    assert c["towing_authorized"] is True


def test_warning_works_when_dwell_was_not_measured():
    """Regression: a case opened from an officer's observation has dwell None; sending the warning used to raise."""
    c = parking.create_parking_case("runs/clip03", "clip03", 1, None, "SUV", "black",
                                    {"violation_type": "no_parking", "duration_s": None})
    for st in ("pending_verification", "verified_violation", "owner_notification_pending", "warning_sent"):
        c = parking.transition_parking_case(c["case_id"], st, officer="INSP_K")
    assert c["warning_notice"]["dwell_duration_recorded"].startswith("not measured")


def test_unknown_state_is_rejected():
    c = _case()
    with pytest.raises(ValueError, match="Unknown state"):
        parking.transition_parking_case(c["case_id"], "towing_authorized", officer="INSP_B", note="x")   # US spelling


def test_same_evidence_never_opens_two_cases():
    a = parking.create_parking_case("runs/clip02", "clip02", 9, None, "car", "white", {"violation_type": "no_parking"})
    b = parking.create_parking_case("runs/clip02", "clip02", 9, None, "car", "white", {"violation_type": "no_parking"})
    assert b["case_id"] == a["case_id"] and b.get("duplicate_of_open_case")
    assert len(parking.load_parking_cases()) == 1


# ---------------------------------------------------------------- e-challan guards
def _draft(reg="MH12AB3456"):
    return echallan.create_echallan_draft(reg, "Illegal parking", "loc", None, None, None, None, None, None, None)


def test_draft_keeps_unknown_evidence_empty():
    d = _draft()
    assert d["vehicle_attributes"]["ocr_confidence"] is None
    assert d["evidence_reference"]["frames"] is None


def test_invalid_registration_and_fine_are_rejected():
    with pytest.raises(ValueError, match="registration"):
        _draft("NOTAPLATE!!")
    with pytest.raises(ValueError, match="fine_inr"):
        echallan.create_echallan_draft("MH12AB3456", "Illegal parking", "l", None, None, None, None, None, None, None,
                                       fine_amount=-5)


def test_cancelled_or_disputed_cases_cannot_be_approved():
    d = _draft()
    echallan.cancel_echallan(d["case_id"], "INSP_C", "wrong vehicle")
    with pytest.raises(ValueError, match="cannot be approved"):
        echallan.approve_and_issue_echallan(d["case_id"], "ACP_D")


def test_full_lifecycle_verify_approve_pay():
    d = _draft()
    with pytest.raises(ValueError, match="human officer"):
        echallan.submit_for_review(d["case_id"], "SYSTEM")
    v = echallan.submit_for_review(d["case_id"], "SGT_E")
    assert v["status"] == "pending_review" and v["verified_by"] == "SGT_E"
    i = echallan.approve_and_issue_echallan(v["case_id"], "ACP_F")
    assert i["status"] == "issued"
    p = echallan.record_payment(i["case_id"])
    assert p["status"] == "paid" and p["payment_status"] == "paid_simulated"
    with pytest.raises(ValueError):
        echallan.record_payment(i["case_id"])                    # no double payment


def test_dispute_cannot_be_resolved_twice():
    d = _draft()
    echallan.approve_and_issue_echallan(d["case_id"], "ACP_F")
    echallan.file_echallan_dispute(d["case_id"], "not my car")
    echallan.resolve_echallan_dispute(d["case_id"], "MAG_G", "dismissed", "plate clear in frame 40")
    with pytest.raises(ValueError, match="No active dispute"):
        echallan.resolve_echallan_dispute(d["case_id"], "MAG_G", "upheld", "changed mind")


# ---------------------------------------------------------------- API
def test_api_echallan_cancel_route_exists_and_validates():
    d = _draft()
    r = client.post(f"/api/echallans/cases/{d['case_id']}/cancel", json={"officer": "INSP_H"})
    assert r.status_code == 400                                   # reason required
    r = client.post(f"/api/echallans/cases/{d['case_id']}/cancel", json={"officer": "INSP_H", "reason": "duplicate"})
    assert r.status_code == 200 and r.json()["status"] == "cancelled"


def test_api_rejects_malformed_case_ids():
    assert client.post("/api/echallans/cases/../../x/approve", json={"officer": "A"}).status_code == 404
    assert client.post("/api/echallans/cases/ECH-1/approve", json={"officer": "A"}).status_code == 404
    assert client.get("/api/parking/cases/nope/warning").status_code == 404


def test_api_echallan_from_stored_evidence_uses_stored_attributes():
    r = client.post("/api/echallans/cases", json={"registration_number": "DL3CCY1025", "violation_category": "Illegal parking",
                                                  "evidence_run": "runs/clip03", "track_id": 1, "officer_id": "SGT_I"})
    if r.status_code == 404:
        pytest.skip("clip03 T1 not in stored results")
    assert r.status_code == 200, r.text
    c = r.json()
    res = json.loads((ROOT / "runs/clip03/result.json").read_text(encoding="utf-8"))
    veh = next(v for v in res["vehicles"] if v["track_id"] == 1)
    assert c["vehicle_attributes"]["ocr_plate"] == veh["plate"]["fused"]
    assert c["vehicle_attributes"]["colour"] == veh["colour"]["label"]


def test_api_echallan_rejects_unknown_category_and_unknown_vehicle():
    assert client.post("/api/echallans/cases", json={"registration_number": "MH12AB3456", "violation_category": "Bogus"}).status_code == 400
    assert client.post("/api/echallans/cases", json={"registration_number": "MH12AB3456", "evidence_run": "runs/clip03",
                                                     "track_id": 99999}).status_code == 404


def test_api_parking_case_needs_stored_evidence():
    assert client.post("/api/parking/cases", json={}).status_code == 400
    assert client.post("/api/parking/cases", json={"run_id": "runs/clip02", "track_id": 99999}).status_code == 404


def test_api_parking_transition_needs_officer():
    c = _case()
    r = client.post(f"/api/parking/cases/{c['case_id']}/transition", json={"new_state": "pending_verification"})
    assert r.status_code == 400 and "officer" in r.json()["detail"]
    r = client.post(f"/api/parking/cases/{c['case_id']}/transition",
                    json={"new_state": "pending_verification", "officer": "SGT_J", "notes": "legacy key"})
    assert r.status_code == 200 and r.json()["officer_notes"][-1]["note"] == "legacy key"


def test_api_parking_scan_is_read_only():
    before = parking.load_parking_cases()
    r = client.get("/api/parking/scan/runs/clip02")
    assert r.status_code == 200 and "findings" in r.json()
    assert parking.load_parking_cases() == before


def test_api_colour_model_info_reports_config_not_a_constant():
    from tracevision import load_config
    info = client.get("/api/colour/model_info").json()
    assert info["active_method"] == load_config()["colour"]["method"]


# ---------------------------------------------------------------- colour probe loader
def test_probe_loader_prefers_v2_and_falls_back_to_v1(tmp_path):
    p = colour.default_probe_path()
    assert p is not None
    v2 = ROOT / "TRACEVISION_DATA/models/vcor_linear_probe_v2.pt"
    assert p == (v2 if v2.exists() else ROOT / "TRACEVISION_DATA/models/vcor_linear_probe.pt")
    assert colour._linear_probe_model(tmp_path / "missing.pt") is None


def test_probe_never_outputs_outside_vocabulary():
    crop = np.full((224, 224, 3), 128, dtype=np.uint8)
    res = colour.estimate_colour([crop], "car", method="linear_probe")
    assert res["label"] in colour.ALLOWED_COLOURS
