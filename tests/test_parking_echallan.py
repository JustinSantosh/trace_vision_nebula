"""Unit and integration tests for Illegal Parking and E-Challan workflows (Parts 5 & 6)."""

import pytest
from tracevision import parking, echallan


@pytest.fixture(autouse=True)
def _isolated_case_files(tmp_path, monkeypatch):
    """Tests must never write into the real runs/enforcement ledgers that the app shows."""
    monkeypatch.setattr(parking, "PARKING_CASES_FILE", tmp_path / "parking_cases.json")
    monkeypatch.setattr(echallan, "ECHALLAN_DB", tmp_path / "echallan_cases.json")


def test_parking_zone_classification():
    # Define test zones
    zones = [
        {
            "name": "Bus Stop Clearway",
            "type": "no_parking",
            "polygon": [[0.0, 0.0], [0.5, 0.0], [0.5, 0.5], [0.0, 0.5]],
            "dwell_limit_s": 30
        },
        {
            "name": "Designated Parking Bay",
            "type": "legal_parking",
            "polygon": [[0.5, 0.5], [1.0, 0.5], [1.0, 1.0], [0.5, 1.0]],
            "dwell_limit_s": 3600
        }
    ]

    # 1. Stationary vehicle in legal parking
    legal_track = [[f, 550, 550, 650, 650] for f in range(0, 100, 5)] # within [0.5, 1.0]
    res_legal = parking.analyze_track_parking(legal_track, zones, fps=25.0, width=1000, height=1000)
    assert res_legal is not None
    assert res_legal["status"] == "legal_parking"

    # 2. Stationary vehicle in no_parking for > dwell_limit (1000 frames at 25 fps = 40s > 30s)
    illegal_track = [[f, 100, 100, 200, 200] for f in range(0, 1000, 25)]
    res_illegal = parking.analyze_track_parking(illegal_track, zones, fps=25.0, width=1000, height=1000)
    assert res_illegal is not None
    assert res_illegal["status"] == "violation"
    assert res_illegal["violation_type"] == "no_parking"

    # 3. Moving vehicle in no_parking zone
    moving_track = [[f, f * 5, f * 5, f * 5 + 100, f * 5 + 100] for f in range(0, 50, 5)]
    res_moving = parking.analyze_track_parking(moving_track, zones, fps=25.0, width=1000, height=1000)
    assert res_moving is not None
    assert res_moving["status"] == "in_transit"

    # 4. Brief stopping (< 15s)
    brief_track = [[f, 100, 100, 200, 200] for f in range(0, 101, 20)] # 4 seconds, 6 points
    res_brief = parking.analyze_track_parking(brief_track, zones, fps=25.0, width=1000, height=1000)
    assert res_brief is not None
    assert res_brief["status"] == "temporary_stopping"

    # 5. Interrupted tracking gap (> 3s gap, duration > 15s)
    gap_track = [
        [0, 100, 100, 200, 200],
        [25, 100, 100, 200, 200],
        [50, 100, 100, 200, 200],
        [800, 100, 100, 200, 200], # gap of 750 frames = 30s
        [1000, 100, 100, 200, 200] # total duration = 40s
    ]
    res_gap = parking.analyze_track_parking(gap_track, zones, fps=25.0, width=1000, height=1000)
    assert res_gap is not None
    assert res_gap["status"] == "uncertain_gap"


def test_parking_state_machine_and_warning_generation():
    # Create case
    analysis = {
        "violation_type": "tow_away",
        "duration_s": 180,
        "first_frame": 0,
        "last_frame": 100,
        "zone_name": "Clearway",
        "grace_minutes": 5
    }
    case = parking.create_parking_case(
        run_id="runs/test_run",
        clip_id="clip_test",
        track_id=42,
        registration="DL3CCK9999",
        vehicle_type="car",
        colour="white",
        analysis_result=analysis,
        location="Connaught Place Outer Circle"
    )
    assert case["state"] == parking.STATE_DETECTED

    # Advance state to pending verification
    case = parking.transition_parking_case(case["case_id"], parking.STATE_PENDING_VERIFICATION, officer="SGT_SINGH")
    assert case["state"] == parking.STATE_PENDING_VERIFICATION

    # Advance state to verified
    case = parking.transition_parking_case(case["case_id"], parking.STATE_VERIFIED, officer="INSPECTOR_SHARMA")
    assert case["state"] == parking.STATE_VERIFIED

    # Advance state to notification pending -> warning sent
    case = parking.transition_parking_case(case["case_id"], parking.STATE_WARNING_PENDING)
    case = parking.transition_parking_case(case["case_id"], parking.STATE_WARNING_SENT)
    assert case["state"] == parking.STATE_WARNING_SENT
    assert case["warning_notice"] is not None
    assert case["warning_notice"]["response_period_minutes"] == 5
    assert "DL3CCK9999" in case["warning_notice"]["warning_message"]

    # Recheck: vehicle moves -> closed
    case = parking.transition_parking_case(case["case_id"], parking.STATE_VEHICLE_MOVED, note="Vehicle vacated spot")
    case = parking.transition_parking_case(case["case_id"], parking.STATE_CLOSED, note="Closed with no penalty")
    assert case["state"] == parking.STATE_CLOSED


def test_echallan_lifecycle_and_duplicate_prevention():
    reg = "HR26DK8888"
    draft = echallan.create_echallan_draft(
        registration=reg,
        violation_category="Illegal parking",
        location="Sector 29 Market",
        evidence_run="runs/clip04",
        track_id=10,
        ocr_plate="HR26DK8888",
        ocr_confidence=0.98,
        vehicle_type="SUV",
        vehicle_colour="black",
        evidence_frames=[10, 50, 90]
    )
    assert draft["status"] == echallan.STATUS_DRAFT
    assert draft["fine_inr"] == 500
    assert "Section 122/177" in draft["legal_provision"]

    # Test duplicate prevention: attempting to create identical draft within window must raise ValueError
    with pytest.raises(ValueError, match="DUPLICATE VIOLATION REJECTED"):
        echallan.create_echallan_draft(
            registration=reg,
            violation_category="Illegal parking",
            location="Sector 29 Market",
            evidence_run="runs/clip04",
            track_id=11,
            ocr_plate="HR26DK8888",
            ocr_confidence=0.97,
            vehicle_type="SUV",
            vehicle_colour="black",
            evidence_frames=[100, 150]
        )

    # Approve and issue
    issued = echallan.approve_and_issue_echallan(draft["case_id"], approving_officer="ACP_VERMA", approval_notes="Evidence checked")
    assert issued["status"] == echallan.STATUS_ISSUED
    assert issued["approved_by"] == "ACP_VERMA"

    # Dispute workflow
    disputed = echallan.file_echallan_dispute(draft["case_id"], citizen_reason="Vehicle was broken down waiting for tow truck")
    assert disputed["status"] == echallan.STATUS_DISPUTED
    assert disputed["dispute_record"]["reason"] == "Vehicle was broken down waiting for tow truck"

    # Resolve dispute (upheld -> cancelled)
    resolved = echallan.resolve_echallan_dispute(
        draft["case_id"],
        officer="CHIEF_MAGISTRATE",
        resolution="upheld",
        officer_findings="Emergency hazard lights verified on CCTV; mechanical breakdown receipt provided."
    )
    assert resolved["status"] == echallan.STATUS_CANCELLED
    assert "Dispute upheld" in resolved["cancellation_reason"]
