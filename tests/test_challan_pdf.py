"""Challan notice PDF: builds for a synthetic-history challan, and fine amounts use Indian digit grouping."""
import pytest

from tracevision import challan, intel


def test_inr_grouping():
    assert challan._inr(500) == "₹500"
    assert challan._inr(1000) == "₹1,000"
    assert challan._inr(120000) == "₹1,20,000"
    assert challan._inr(10000000) == "₹1,00,00,000"


def test_history_challan_pdf_builds():
    if not intel.available():
        pytest.skip("synthetic registry not present")
    first = next(iter(intel._tables()["challans"].values()))[0]
    c = intel.find_challan(first["challan_id"])
    assert c and c["registration_number"] == first["registration_number"]
    pdf = challan.build_pdf(c)
    assert pdf.startswith(b"%PDF") and len(pdf) > 5000


def test_unknown_challan():
    assert intel.find_challan("NOT-A-CHALLAN") is None
