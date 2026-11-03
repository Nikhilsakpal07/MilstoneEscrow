import os
import sys
import json
from fastapi.testclient import TestClient

sys.stdout.reconfigure(encoding="utf-8")

from main import app
from database import SessionLocal
import models

client = TestClient(app)


def test_predictive_risk_evaluation():
    print("\n--- Testing Predictive Risk Scoring ---")
    response = client.post("/api/analytics/predictive-risk/evaluate")
    print(f"Risk evaluation status code: {response.status_code}")
    assert response.status_code == 200
    data = response.json()
    print(f"Evaluated count: {data.get('evaluated_count')}")
    assert "status" in data
    assert data["status"] == "success"
    assert "evaluations" in data


def test_bounty_list_has_risk_and_certificate_metadata():
    print("\n--- Testing Bounty List Serialization ---")
    response = client.get("/api/bounties")
    assert response.status_code == 200
    bounties = response.json()
    print(f"Total bounties retrieved: {len(bounties)}")
    if bounties:
        first = bounties[0]
        print(f"Bounty #{first['id']} Title: {first['title']}")
        print(f"Risk Score: {first.get('risk_score')}, Risk Percentage: {first.get('risk_percentage')}%")
        assert "risk_score" in first
        assert "risk_percentage" in first
        assert "risk_factors" in first
        if first.get("milestones"):
            m = first["milestones"][0]
            print(f"Milestone #{m['id']} has_certificate: {m.get('has_certificate')}, cert_id: {m.get('certificate_id')}")
            assert "certificate_id" in m
            assert "has_certificate" in m


def test_certificate_download_endpoint():
    print("\n--- Testing Certificate Download Endpoint ---")
    db = SessionLocal()
    try:
        # Find any completed milestone, or temporarily mock one to test PDF generator
        completed_m = db.query(models.Milestone).filter(models.Milestone.status == "COMPLETED").first()
        if completed_m:
            resp = client.get(f"/api/milestones/{completed_m.id}/certificate")
            print(f"Download response code: {resp.status_code}")
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "application/pdf"
            print(f"Received PDF certificate of size: {len(resp.content)} bytes")
        else:
            print("No completed milestone found in DB to test download.")
    finally:
        db.close()


def test_sybil_detection_and_fraud_review():
    print("\n--- Testing AI Stylometric Fingerprinting / Sybil Attack Detection ---")
    db = SessionLocal()
    try:
        # Create a test bounty for Sybil attack detection
        bounty = models.Bounty(
            title="Sybil AST Security Test Contract",
            acceptance_criteria="Implement high-performance fibonacci cache",
            amount_usd=100.0,
            remaining_amount_usd=100.0,
            freelancer_email="sybil_account_b@example.com",
            status="IN_PROGRESS",
            requires_human_approval=False,
        )
        db.add(bounty)
        db.flush()

        milestone = models.Milestone(
            bounty_id=bounty.id,
            description="Phase 1: Fibonacci AST Module",
            deadline="2026-11-20",
            percentage=100.0,
            amount_usd=100.0,
            status="LOCKED",
        )
        db.add(milestone)

        # Seed historical code fingerprint from User A
        historical_fp = models.CodeFingerprint(
            freelancer_email="freelancer_sybil_a@example.com",
            bounty_id=bounty.id,
            milestone_id=milestone.id,
            github_url="https://github.com/sybil_origin/algo",
            ast_hash="test-ast-hash-unique-sequence-4242",
            naming_style={"snake_case_count": 12, "camel_case_count": 0, "avg_identifier_length": 14.5},
            identifiers=["memoized_fib_cache_val", "compute_recursive_golden_ratio", "strict_bounds_checker"],
            code_summary="def memoized_fib_cache_val(n):\n    return n if n <= 1 else n",
        )
        db.add(historical_fp)
        db.commit()

        # Now simulate User B submitting identical AST code fingerprint
        from stylometric_fingerprint import evaluate_sybil_stylometric_fingerprint
        import unittest.mock as mock

        # Mock extract_code_stylometrics so we test the Sybil arbitration directly
        mock_curr_fp = {
            "ast_hash": "test-ast-hash-unique-sequence-4242",  # Exact AST match
            "identifiers": ["memoized_fib_cache_val", "compute_recursive_golden_ratio", "strict_bounds_checker"],
            "naming_style": {"snake_case_count": 12, "camel_case_count": 0, "avg_identifier_length": 14.5},
            "code_summary": "def memoized_fib_cache_val(n):\n    return n if n <= 1 else n",
        }

        with mock.patch("stylometric_fingerprint.extract_code_stylometrics", return_value=mock_curr_fp):
            # Test direct fingerprint evaluation
            res = evaluate_sybil_stylometric_fingerprint(
                db=db,
                github_url="https://github.com/sybil_fake_user/algo",
                freelancer_email="sybil_account_b@example.com",
                bounty_id=bounty.id,
                milestone_id=milestone.id,
            )
            print(f"Sybil evaluation result: {res}")
            assert res.get("is_sybil_match") is True
            assert res.get("matched_account") == "freelancer_sybil_a@example.com"

            # Now test full submit_work route with Sybil attack
            submit_resp = client.post(
                f"/api/bounties/{bounty.id}/milestones/{milestone.id}/submit-work",
                json={"github_url": "https://github.com/sybil_fake_user/algo"},
            )
            print(f"Submit work under Sybil attack response: {submit_resp.json()}")
            assert submit_resp.status_code == 200
            submit_data = submit_resp.json()
            assert submit_data.get("status") == "fraud_review_pending"
            assert submit_data.get("sybil_detected") is True
            assert submit_data.get("milestone_amount_paid") == 0.0

            # Verify milestone in database has fraud_review_pending
            db.refresh(milestone)
            db.refresh(bounty)
            assert milestone.status == "fraud_review_pending"
            assert bounty.status == "fraud_review_pending"
            print("Successfully verified: Sybil attack flags 'fraud_review_pending' and blocks payout!")

    finally:
        # Clean up test bounty
        try:
            db.query(models.AuditLog).filter(models.AuditLog.bounty_id == bounty.id).delete()
            db.query(models.CodeFingerprint).filter(models.CodeFingerprint.bounty_id == bounty.id).delete()
            db.query(models.Milestone).filter(models.Milestone.bounty_id == bounty.id).delete()
            db.query(models.Bounty).filter(models.Bounty.id == bounty.id).delete()
            db.commit()
        except Exception:
            pass
        db.close()


if __name__ == "__main__":
    test_predictive_risk_evaluation()
    test_bounty_list_has_risk_and_certificate_metadata()
    test_certificate_download_endpoint()
    test_sybil_detection_and_fraud_review()
    print("\nALL ENTERPRISE SECURITY & ANALYTICS TESTS PASSED!")
