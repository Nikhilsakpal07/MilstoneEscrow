import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import models
from conftest import TestingSessionLocal, client
from paypal_client import reauthorize_payment, PayPalReauthorizationError


def test_reauthorize_payment_client_success():
    """
    Unit test: Assert reauthorize_payment builds proper URL, headers, and decimal-formatted payload.
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "AUTH-NEW-777",
        "status": "CREATED",
        "expiration_time": "2026-12-01T12:00:00Z",
    }

    with patch("paypal_client.get_access_token", return_value="mock_token"), \
         patch("paypal_client.requests.post", return_value=mock_resp) as mock_post:
        result = reauthorize_payment("AUTH-OLD-111", 150.5, currency="USD")

        assert result["id"] == "AUTH-NEW-777"
        mock_post.assert_called_once()
        url = mock_post.call_args[0][0]
        headers = mock_post.call_args[1]["headers"]
        payload = mock_post.call_args[1]["json"]

        assert "AUTH-OLD-111/reauthorize" in url
        assert headers["Authorization"] == "Bearer mock_token"
        assert "reauth_AUTH-OLD-111_" in headers["PayPal-Request-Id"]
        assert payload == {"amount": {"currency_code": "USD", "value": "150.50"}}


def test_submission_minor_failure_triggers_needs_revision(client):
    """
    Integration test: If QA returns passed=False but allow_revision=True and revision_count < MAX_REVISIONS,
    Bounty transitions to NEEDS_REVISION, revision_count increments, deadline is ~48h out,
    payment is reauthorized, and authorization is NOT voided.
    """
    db = TestingSessionLocal()
    bounty = models.Bounty(
        title="Widget Component",
        acceptance_criteria="Pass 5 integration tests",
        amount_usd=300.0,
        freelancer_email="freelancer@example.com",
        status="LOCKED",
        revision_count=0,
    )
    db.add(bounty)
    db.flush()

    escrow = models.Escrow(
        bounty_id=bounty.id,
        paypal_order_id="ORDER-REV-1",
        paypal_authorization_id="AUTH-ORIGINAL-1",
        status="HELD",
    )
    db.add(escrow)
    db.commit()
    bounty_id = bounty.id
    db.close()

    mock_eval = {
        "passed": False,
        "allow_revision": True,
        "feedback": "4 of 5 tests passed. Route /health failed due to missing body.",
    }

    reauth_mock_return = {
        "id": "AUTH-EXTENDED-2",
        "status": "CREATED",
    }

    with patch("main.evaluate_submission", return_value=mock_eval), \
         patch("main.reauthorize_payment", return_value=reauth_mock_return) as mock_reauth, \
         patch("main.void_authorization") as mock_void:
        response = client.post(
            f"/api/bounties/{bounty_id}/submit-work",
            json={"github_url": "https://github.com/user/minor-fix-needed"},
        )

    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "NEEDS_REVISION"
    assert res_data["allow_revision"] is True
    assert res_data["revision_count"] == 1
    assert res_data["revision_deadline"] is not None

    mock_void.assert_not_called()
    mock_reauth.assert_called_once_with(
        authorization_id="AUTH-ORIGINAL-1",
        amount=300.0,
    )

    verify_db = TestingSessionLocal()
    updated_bounty = verify_db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    updated_escrow = verify_db.query(models.Escrow).filter(models.Escrow.bounty_id == bounty_id).first()

    assert updated_bounty.status == "NEEDS_REVISION"
    assert updated_bounty.revision_count == 1
    assert updated_escrow.paypal_authorization_id == "AUTH-EXTENDED-2"
    assert updated_escrow.status == "HELD"
    assert updated_escrow.last_reauthorized_at is not None
    verify_db.close()


def test_submission_exceeding_max_revisions_triggers_void(client):
    """
    Integration test: If revision_count >= MAX_REVISIONS, subsequent failure triggers hard void
    and marks Bounty REJECTED even if allow_revision is True.
    """
    db = TestingSessionLocal()
    bounty = models.Bounty(
        title="Complex Backend Refactor",
        acceptance_criteria="Pass benchmark",
        amount_usd=500.0,
        freelancer_email="freelancer@example.com",
        status="NEEDS_REVISION",
        revision_count=2, # Max reached
    )
    db.add(bounty)
    db.flush()

    escrow = models.Escrow(
        bounty_id=bounty.id,
        paypal_order_id="ORDER-MAX-REVS",
        paypal_authorization_id="AUTH-MAX-EXHAUSTED",
        status="HELD",
    )
    db.add(escrow)
    db.commit()
    bounty_id = bounty.id
    db.close()

    mock_eval = {
        "passed": False,
        "allow_revision": True,
        "feedback": "Still failing benchmarks on third attempt.",
    }

    with patch("main.evaluate_submission", return_value=mock_eval), \
         patch("main.void_authorization") as mock_void:
        response = client.post(
            f"/api/bounties/{bounty_id}/submit-work",
            json={"github_url": "https://github.com/user/refactor"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    mock_void.assert_called_once_with("AUTH-MAX-EXHAUSTED")

    verify_db = TestingSessionLocal()
    updated_bounty = verify_db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    updated_escrow = verify_db.query(models.Escrow).filter(models.Escrow.bounty_id == bounty_id).first()

    assert updated_bounty.status == "REJECTED"
    assert updated_escrow.status == "VOIDED"
    assert updated_escrow.voided_at is not None
    verify_db.close()


def test_expired_revision_triggers_void(client):
    """
    Integration test: If revision_deadline is in the past, POST /api/bounties/{id}/expire-revision
    voids the authorization and marks the bounty REJECTED.
    """
    db = TestingSessionLocal()
    past_deadline = datetime.now(timezone.utc) - timedelta(hours=2)
    bounty = models.Bounty(
        title="Timed Out Revision",
        acceptance_criteria="Pass tests",
        amount_usd=120.0,
        freelancer_email="dev@example.com",
        status="NEEDS_REVISION",
        revision_count=1,
        revision_deadline=past_deadline,
    )
    db.add(bounty)
    db.flush()

    escrow = models.Escrow(
        bounty_id=bounty.id,
        paypal_order_id="ORDER-EXPIRED-REV",
        paypal_authorization_id="AUTH-EXPIRE-TARGET",
        status="HELD",
    )
    db.add(escrow)
    db.commit()
    bounty_id = bounty.id
    db.close()

    with patch("main.void_authorization") as mock_void:
        response = client.post(f"/api/bounties/{bounty_id}/expire-revision")

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    mock_void.assert_called_once_with("AUTH-EXPIRE-TARGET")

    verify_db = TestingSessionLocal()
    updated_bounty = verify_db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    updated_escrow = verify_db.query(models.Escrow).filter(models.Escrow.bounty_id == bounty_id).first()

    assert updated_bounty.status == "REJECTED"
    assert updated_escrow.status == "VOIDED"
    assert updated_escrow.voided_at is not None
    verify_db.close()


def test_unexpired_revision_cannot_be_expired(client):
    """
    Integration test: Calling expire-revision when deadline is in the future returns HTTP 400.
    """
    db = TestingSessionLocal()
    future_deadline = datetime.now(timezone.utc) + timedelta(hours=24)
    bounty = models.Bounty(
        title="Active Revision",
        acceptance_criteria="In progress",
        amount_usd=80.0,
        freelancer_email="dev@example.com",
        status="NEEDS_REVISION",
        revision_count=1,
        revision_deadline=future_deadline,
    )
    db.add(bounty)
    db.commit()
    bounty_id = bounty.id
    db.close()

    response = client.post(f"/api/bounties/{bounty_id}/expire-revision")
    assert response.status_code == 400
    assert "not yet expired" in response.json()["detail"]

