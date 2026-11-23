"""Vehicle intelligence (synthetic owner + e-challan records, roles, audit log) and the wrong-side driving check.

UI-only mode: no model is loaded. Audit / review / challan files are redirected to a temp folder.
"""
import json
import os

import pytest

os.environ["TRACEVISION_UI_ONLY"] = "1"
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from tracevision import ROOT, api, intel, violations  # noqa: E402

api.UI_ONLY = True
client = TestClient(api.app)
VIDEO = ROOT / "TRACEVISION_DATA/raw/test_videos/clip02.mp4"


@pytest.fixture(autouse=True)
def _tmp_state(tmp_path, monkeypatch):
    monkeypatch.setattr(intel, "AUDIT", tmp_path / "lookups.jsonl")
    monkeypatch.setattr(intel, "ISSUED", tmp_path / "issued.json")
    monkeypatch.setattr(violations, "REVIEWS", tmp_path / "reviews.json")


def matched_vehicle():
    for p in sorted((ROOT / "runs").glob("clip*/result.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        for v in r["vehicles"]:
            if v["decision"] == "match":
                return f"runs/{p.parent.name}", v
    pytest.skip("no stored run has a confident match")


def unmatched_vehicle():
    for p in sorted((ROOT / "runs").glob("clip*/result.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        for v in r["vehicles"]:
            if v["decision"] != "match" and v.get("candidates"):
                return f"runs/{p.parent.name}", v
    pytest.skip("no stored unmatched vehicle with candidates")


# ---------------------------------------------------------------- data
def test_every_registry_vehicle_has_a_synthetic_record():
    t = intel._tables()
    assert t["owners"] and set(t["owners"]) == {r["synthetic_vehicle_id"] for r in t["by_reg"].values()}
    assert all(o["synthetic"] == "true" for o in t["owners"].values())
    assert all(c["challan_id"].startswith("SYN-") for cs in t["challans"].values() for c in cs)


# ---------------------------------------------------------------- lookup + issuing
def test_lookup_returns_everything_and_is_logged():
    run, v = matched_vehicle()
    reg, ctx = v["candidates"][0]["registration_number"], f"{run}:T{v['track_id']}"
    r = client.get(f"/api/intel/{reg}", params={"context": ctx})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["synthetic"] and d["vehicle"]["registration_number"] == reg
    assert d["owner"]["name"] and "•" not in d["owner"]["name"] and isinstance(d["challans"], list)
    log = [json.loads(x) for x in intel.AUDIT.read_text(encoding="utf-8").splitlines()]
    assert log[-1]["outcome"] == "ok" and log[-1]["context"] == ctx


def test_no_record_is_attached_to_a_vehicle_without_a_confident_match():
    run, v = unmatched_vehicle()
    reg, ctx = v["candidates"][0]["registration_number"], f"{run}:T{v['track_id']}"
    assert client.get(f"/api/intel/{reg}", params={"context": ctx}).status_code == 409
    r = client.post("/api/challans", json={"registration_number": reg, "violation": "Over-speeding", "context": ctx})
    assert r.status_code == 409 and intel.issued_challans() == []


def test_issue_and_cancel_a_simulated_challan():
    run, v = matched_vehicle()
    reg, ctx = v["candidates"][0]["registration_number"], f"{run}:T{v['track_id']}"
    before = client.get(f"/api/intel/{reg}").json()["challan_summary"]
    r = client.post("/api/challans", json={"registration_number": reg, "violation": "Over-speeding", "location": "clip", "context": ctx})
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["challan_id"].startswith("SYN-SIM-") and c["fine_inr"] == intel.VIOLATION_FINES["Over-speeding"]
    after = client.get(f"/api/intel/{reg}").json()
    assert after["challans"][0]["challan_id"] == c["challan_id"]
    assert after["challan_summary"]["pending"] == before["pending"] + 1
    assert client.post("/api/challans", json={"registration_number": reg, "violation": ""}).status_code == 400
    assert client.post("/api/challans", json={"registration_number": "ZZ00ZZ0000", "violation": "Over-speeding"}).status_code == 404
    assert client.post("/api/challans/cancel", json={"challan_id": c["challan_id"]}).status_code == 200
    assert client.post("/api/challans/cancel", json={"challan_id": "SYN-CG-2024-123456"}).status_code == 404
    assert intel.issued_challans() == []
    actions = [e["action"] for e in client.get("/api/audit").json()]
    assert "issue challan" in actions and "cancel challan" in actions


def test_meta_lists_violations_and_fines():
    m = client.get("/api/intel/meta").json()
    assert m["available"] is True and m["violations"]["Wrong-side driving"] > 0


# ---------------------------------------------------------------- wrong-side driving
def test_inside_polygon():
    sq = [[0, 0], [1, 0], [1, 1], [0, 1]]
    assert violations.inside((0.5, 0.5), sq) and not violations.inside((1.5, 0.5), sq)


def test_moving_camera_clips_are_not_assessed():
    r = client.get("/data/runs/clip03/violations").json()
    assert r["assessed"] is False and "moving" in r["not_assessed_reason"]


@pytest.mark.skipif(not VIDEO.exists(), reason="clip02 video not on this machine")
def test_real_fixed_clip_has_no_false_alarm_but_a_reversed_track_is_flagged():
    res = json.loads((ROOT / "runs/clip02/result.json").read_text(encoding="utf-8"))
    d = violations.detect(res, "runs/clip02")
    assert d["assessed"] and d["checked_vehicles"] >= 10 and d["violations"] == []
    # Same geometry, played backwards: a vehicle driving TOWARDS the camera on the one-way road must be flagged.
    zone = violations.rule_for("clip02")[1]["zones"][0]
    motion = json.loads((ROOT / "runs/clip02/camera_motion.json").read_text(encoding="utf-8"))
    W, H_ = res["video"]["width"], res["video"]["height"]
    hits = 0
    for v in res["vehicles"]:
        fwd = violations.check_track(v["track"], zone, W, H_, motion)
        if not fwd:
            continue
        rev = [[p[0]] + q[1:] for p, q in zip(v["track"], reversed(v["track"]))]
        back = violations.check_track(rev, zone, W, H_, motion)
        assert not fwd["wrong_side"]
        hits += bool(back and back["wrong_side"])
    assert hits >= 5


def test_confirming_a_violation_on_a_matched_vehicle_raises_a_simulated_challan(monkeypatch):
    run, v = matched_vehicle()
    vid = f"{run}:T{v['track_id']}:wrong_side"
    fake = {"violation_id": vid, "label": "Wrong-side driving", "clip_id": run.split("/")[1],
            "registration_number": v["candidates"][0]["registration_number"]}
    monkeypatch.setattr(violations, "detect", lambda res, run_id: {"violations": [fake]})
    body = {"violation_id": vid, "decision": "confirmed"}
    r = client.post("/api/violations/review", json=body)
    assert r.status_code == 200 and r.json()["challan"]["challan_id"].startswith("SYN-SIM-")
    rec = client.get(f"/api/intel/{fake['registration_number']}").json()
    assert rec["challans"][0]["source"] == "simulated_issued"
    client.post("/api/violations/review", json={**body, "decision": "rejected"})
    assert intel.issued_challans() == []
