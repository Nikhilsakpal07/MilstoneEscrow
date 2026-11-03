import json
import pytest
from unittest.mock import patch, MagicMock

import models
from conftest import TestingSessionLocal, client
from paypal_client import void_authorization, PayPalVoidError

SAMPLE_HEADERS = {
    "paypal-transmission-id": "transmission-12345",
    "paypal-transmission-time": "2026-11-03T12:00:00Z",
    "paypal-cert-url": "https://api.sandbox.paypal.com/v1/cert",
    "paypal-auth-algo": "SHA256withRSA",
    "paypal-transmission-sig": "mock_signature_base64",
}


def test_void_authorization_success():
    """
    Unit test: Assert void_authorization calls PayPal void endpoint with correct headers
    and returns successfully when receiving HTTP 204.
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 204

    with patch("paypal_client.get_access_token", return_value="mock_token"), \
         patch("paypal_client.requests.post", return_value=mock_resp) as mock_post:
        result = void_authorization("AUTH-12345")

        assert result == {"status": "VOIDED"}
        mock_post.assert_called_once()
        url = mock_post.call_args[0][0]
        headers = mock_post.call_args[1]["headers"]
        assert "AUTH-12345/void" in url
        assert headers["PayPal-Request-Id"] == "void_auth_AUTH-12345"
        assert headers["Authorization"] == "Bearer mock_token"


def test_void_authorization_error_handling():
    """
    Unit test: Assert void_authorization raises PayPalVoidError when PayPal returns 422 or 400.
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 422
    mock_resp.json.return_value = {
        "name": "UNPROCESSABLE_ENTITY",
        "message": "The authorization cannot be voided because it is already expired or voided.",
    }

    with patch("paypal_client.get_access_token", return_value="mock_token"), \
         patch("paypal_client.requests.post", return_value=mock_resp):
        with pytest.raises(PayPalVoidError) as exc_info:
            void_authorization("AUTH-ALREADY-VOIDED")

        assert "already expired or voided" in str(exc_info.value)
        assert exc_info.value.status_code == 422


def test_submit_work_qa_failure_triggers_void(client):
    """
    Integration test: If QA evaluation fails (passed=False),
    void_authorization is called, Bounty status becomes REJECTED,
    and Escrow status becomes VOIDED with voided_at timestamp recorded.
    """
    db = TestingSessionLocal()
    bounty = models.Bounty(
        title="Payment Gateway Task",
        acceptance_criteria="All tests pass",
        amount_usd=200.0,
        freelancer_email="freelancer@example.com",
        status="LOCKED",
    )
    db.add(bounty)
    db.flush()

    escrow = models.Escrow(
        bounty_id=bounty.id,
        paypal_order_id="ORDER-FAIL-QA",
        paypal_authorization_id="AUTH-TO-BE-VOIDED",
        status="HELD",
    )
    db.add(escrow)
    db.commit()
    bounty_id = bounty.id
    db.close()

    mock_eval = {
        "passed": False,
        "feedback": "Acceptance criteria not met. Unit tests failed.",
    }

    with patch("main.evaluate_submission", return_value=mock_eval), \
         patch("main.void_authorization") as mock_void:
        response = client.post(
            f"/api/bounties/{bounty_id}/submit-work",
            json={"github_url": "https://github.com/user/broken-project"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert response.json()["passed"] is False
    mock_void.assert_called_once_with("AUTH-TO-BE-VOIDED")

    verify_db = TestingSessionLocal()
    updated_bounty = verify_db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    updated_escrow = verify_db.query(models.Escrow).filter(models.Escrow.bounty_id == bounty_id).first()

    assert updated_bounty.status == "REJECTED"
    assert updated_escrow.status == "VOIDED"
    assert updated_escrow.voided_at is not None
    verify_db.close()


def test_cancel_bounty_triggers_void(client):
    """
    Integration test: Calling POST /api/bounties/{bounty_id}/cancel on a locked bounty
    voids the authorization and transitions Bounty to CANCELED and Escrow to VOIDED.
    """
    db = TestingSessionLocal()
    bounty = models.Bounty(
        title="Unfilled Bounty",
        acceptance_criteria="Build responsive navbar",
        amount_usd=75.0,
        freelancer_email="freelancer@example.com",
        status="LOCKED",
    )
    db.add(bounty)
    db.flush()

    escrow = models.Escrow(
        bounty_id=bounty.id,
        paypal_order_id="ORDER-CANCEL-1",
        paypal_authorization_id="AUTH-CANCEL-999",
        status="HELD",
    )
    db.add(escrow)
    db.commit()
    bounty_id = bounty.id
    db.close()

    with patch("main.void_authorization") as mock_void:
        response = client.post(f"/api/bounties/{bounty_id}/cancel")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELED"
    mock_void.assert_called_once_with("AUTH-CANCEL-999")

    verify_db = TestingSessionLocal()
    updated_bounty = verify_db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    updated_escrow = verify_db.query(models.Escrow).filter(models.Escrow.bounty_id == bounty_id).first()

    assert updated_bounty.status == "CANCELED"
    assert updated_escrow.status == "VOIDED"
    assert updated_escrow.voided_at is not None
    verify_db.close()


def test_cancel_bounty_invalid_status_rejected(client):
    """
    Integration test: Canceling a bounty that is already COMPLETED or REJECTED returns HTTP 400.
    """
    db = TestingSessionLocal()
    bounty = models.Bounty(
        title="Completed Bounty",
        acceptance_criteria="Done",
        amount_usd=100.0,
        freelancer_email="dev@example.com",
        status="COMPLETED",
    )
    db.add(bounty)
    db.commit()
    bounty_id = bounty.id
    db.close()

    response = client.post(f"/api/bounties/{bounty_id}/cancel")
    assert response.status_code == 400
    assert "cannot be canceled" in response.json()["detail"]


def test_webhook_payment_authorization_voided(client):
    """
    Integration test: Simulating incoming PAYMENT.AUTHORIZATION.VOIDED webhook event
    marks Escrow status as VOIDED and transitions Bounty status to CANCELED.
    """
    db = TestingSessionLocal()
    bounty = models.Bounty(
        title="Webhook Void Bounty",
        acceptance_criteria="Verify async void",
        amount_usd=350.0,
        freelancer_email="freelancer@example.com",
        status="LOCKED",
    )
    db.add(bounty)
    db.flush()

    escrow = models.Escrow(
        bounty_id=bounty.id,
        paypal_order_id="ORDER-ASYNC-VOID",
        paypal_authorization_id="AUTH-ASYNC-VOID-555",
        status="HELD",
    )
    db.add(escrow)
    db.commit()
    bounty_id = bounty.id
    db.close()

    payload = {
        "id": "WH-VOID-EVENT-101",
        "event_type": "PAYMENT.AUTHORIZATION.VOIDED",
        "resource": {
            "id": "AUTH-ASYNC-VOID-555",
            "supplementary_data": {
                "related_ids": {
                    "order_id": "ORDER-ASYNC-VOID",
                }
            },
        },
    }

    with patch("main.verify_webhook_signature", return_value=True):
        response = client.post(
            "/webhooks/paypal",
            headers=SAMPLE_HEADERS,
            content=json.dumps(payload),
        )

    assert response.status_code == 200
    assert response.json()["status"] == "received"

    verify_db = TestingSessionLocal()
    updated_bounty = verify_db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    updated_escrow = verify_db.query(models.Escrow).filter(models.Escrow.bounty_id == bounty_id).first()

    assert updated_escrow.status == "VOIDED"
    assert updated_escrow.voided_at is not None
    assert updated_bounty.status == "CANCELED"
    verify_db.close()
