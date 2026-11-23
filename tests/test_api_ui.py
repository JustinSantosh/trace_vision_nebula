"""Contract tests for the investigator app's HTTP surface (tracevision/api.py) against the stored results.

Runs in UI-only mode: no model is imported or loaded and no clip is analysed. Needs fastapi + httpx (TestClient);
skipped otherwise. The TestClient is not used as a context manager, so the startup hook (model loading) never runs.
"""
import json
import os
from pathlib import Path

import pytest

os.environ["TRACEVISION_UI_ONLY"] = "1"
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from tracevision import ROOT, api  # noqa: E402

api.UI_ONLY = True
client = TestClient(api.app)
RUN_CLIPS = sorted(p.parent.name for p in (ROOT / "runs").glob("clip*/result.json"))
BASELINE = ROOT / "TRACEVISION_DATA/reports/p6_evaluation_baseline.json"


def test_frontend_shell_and_assets_are_served():
    page = client.get("/")
    assert page.status_code == 200
    for asset in ("/frontend/styles.css", "/frontend/explain.js", "/frontend/app.js"):
        assert asset in page.text
        assert client.get(asset).status_code == 200


def test_overview_reports_ui_only_mode_honestly():
    engine = client.get("/api/overview").json()["engine"]
    assert engine["status"] == "disabled"
    assert "disabled" in engine["message"].lower()


def test_overview_lists_every_stored_result_with_the_frontend_contract():
    clips = client.get("/api/overview").json()["clips"]
    assert [c["clip_id"] for c in clips] == sorted(RUN_CLIPS, key=lambda c: int(c[4:]))
    keys = {"clip_id", "camera_type", "vehicle_count", "match_count", "no_match_count", "ambiguous_count", "plates_read",
            "processed_at", "has_video", "has_report", "has_report_pdf"}
    for clip in clips:
        assert keys <= clip.keys()
        result = json.loads((ROOT / "runs" / clip["clip_id"] / "result.json").read_text(encoding="utf-8"))
        assert clip["vehicle_count"] == len(result["vehicles"])
        assert clip["match_count"] == result["summary"]["decisions"].get("match", 0)


@pytest.mark.skipif(not BASELINE.exists(), reason="no evaluation JSON")
def test_headline_metrics_are_read_from_the_evaluation_json_unchanged():
    evaluation = client.get("/api/overview").json()["evaluation"]
    summary = json.loads(BASELINE.read_text(encoding="utf-8"))["summary"]["all"]
    assert evaluation["source"] == BASELINE.name
    shown = {m["key"]: m["value"] for m in evaluation["metrics"]}
    assert shown["registered_matches"] == summary["registered_vehicles_matched_correctly"].split(" ")[0]
    assert shown["false_confident_matches"] == summary["unregistered_with_false_confident_match"].split(" ")[0]
    assert shown["wrong_plate_characters"] == summary["plate_chars_WRONG"].split(" ")[0]
    assert shown["detected_and_tracked"] == summary["detected_and_tracked"].split(" ")[0]


def test_headline_metrics_fall_back_to_the_markdown_report(monkeypatch):
    monkeypatch.setattr(api, "_evaluation_headlines_json", lambda: {"source": "x", "clip_count": None, "metrics": []})
    evaluation = api._evaluation_headlines()
    assert evaluation["source"] == "p6_evaluation.md"


def test_upload_is_refused_in_ui_only_mode_and_nothing_is_stored():
    jobs_dir = ROOT / "runs" / "jobs"
    before = set(jobs_dir.iterdir()) if jobs_dir.exists() else set()
    response = client.post("/jobs", files={"video": ("clip.mp4", b"not a real video", "video/mp4")})
    assert response.status_code == 503
    after = set(jobs_dir.iterdir()) if jobs_dir.exists() else set()
    assert after == before


def test_review_payload_shape():
    review = client.get("/api/review").json()
    assert {"crosscam_pairs", "crosscam_evaluation", "robustness"} <= review.keys()
    for pair in review["crosscam_pairs"]:
        assert pair["clip_a"] != pair["clip_b"]
        for direction in pair["directions"]:
            assert {direction["source_clip"], direction["target_clip"]} == {pair["clip_a"], pair["clip_b"]}
            assert isinstance(direction["links"], list)


@pytest.mark.parametrize("path", ["/viewer/runs/{c}", "/data/runs/{c}/result.json", "/data/runs/{c}/files",
                                  "/runs/{c}/report", "/runs/{c}/report.pdf"])
def test_existing_stored_result_routes_still_work(path):
    clip = "clip03" if "clip03" in RUN_CLIPS else RUN_CLIPS[0]
    assert client.get(path.format(c=clip)).status_code == 200


@pytest.mark.parametrize("path", ["/runs/..%2F..%2FREADME.md/report", "/data/runs/clip03/vehicles/..%2F..%2FREADME.md",
                                  "/viewer/runs/clip03x", "/data/jobs/notajob/result.json"])
def test_path_traversal_and_unknown_runs_are_rejected(path):
    assert client.get(path).status_code == 404
