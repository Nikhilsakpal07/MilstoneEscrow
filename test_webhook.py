import json
import pytest
from unittest.mock import patch, MagicMock

import models
from conftest import TestingSessionLocal, client
from paypal_client import verify_webhook_signature, calculate_payout_split, execute_payout

SAMPLE_HEADERS = {
    "paypal-transmission-id": "transmission-12345",
    "paypal-transmission-time": "2026-11-03T12:00:00Z",
    "paypal-cert-url": "https://api.sandbox.paypal.com/v1/cert",
    "paypal-auth-algo": "SHA256withRSA",
    "paypal-transmission-sig": "mock_signature_base64",
}


def test_webhook_unverified_signature_returns_400(client):
    """
    Asserts that unverified webhook signatures return 400 Bad Request and abort processing.
    """
    payload = {
        "id": "WH-TEST-UNVERIFIED",
        "event_type": "CHECKOUT.ORDER.APPROVED",
        "resource": {"id": "ORDER-999"},
    }

    with patch("main.verify_webhook_signature", return_value=False):
        response = client.post(
            "/webhooks/paypal",
            headers=SAMPLE_HEADERS,
            content=json.dumps(payload),
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "PayPal webhook signature verification failed"


def test_checkout_order_approved(client):
    """
    Asserts CHECKOUT.ORDER.APPROVED transitions Bounty to LOCKED and
    initiates authorize_order on the Escrow record.
    """
    db = TestingSessionLocal()
    bounty = models.Bounty(
        title="Implement Stripe Bridge",
        acceptance_criteria="Integration tests pass",
        amount_usd=250.0,
        freelancer_email="freelancer@example.com",
        status="AWAITING_FUNDS",
    )
    db.add(bounty)
    db.flush()

    escrow = models.Escrow(
        bounty_id=bounty.id,
        paypal_order_id="ORDER-APPROVED-123",
        paypal_authorization_id=None,
    )
    db.add(escrow)
    db.commit()
    bounty_id = bounty.id
    db.close()

    payload = {
        "id": "WH-CHECKOUT-APPROVED-1",
        "event_type": "CHECKOUT.ORDER.APPROVED",
        "resource": {
            "id": "ORDER-APPROVED-123",
        },
    }

    with patch("main.verify_webhook_signature", return_value=True), \
         patch("main.authorize_order", return_value="AUTH-NEW-999") as mock_auth:
        response = client.post(
            "/webhooks/paypal",
            headers=SAMPLE_HEADERS,
            content=json.dumps(payload),
        )

    assert response.status_code == 200
    assert response.json()["status"] == "received"
    mock_auth.assert_called_once_with("ORDER-APPROVED-123")

    verify_db = TestingSessionLocal()
    updated_bounty = verify_db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    updated_escrow = verify_db.query(models.Escrow).filter(models.Escrow.bounty_id == bounty_id).first()

    assert updated_bounty.status == "LOCKED"
    assert updated_escrow.paypal_authorization_id == "AUTH-NEW-999"
    verify_db.close()


def test_checkout_order_approved_idempotent_when_already_authorized(client):
    """
    Asserts CHECKOUT.ORDER.APPROVED is idempotent and does not re-authorize if already set.
    """
    db = TestingSessionLocal()
    bounty = models.Bounty(
        title="WebSockets Service",
        acceptance_criteria="Pass load test",
        amount_usd=100.0,
        freelancer_email="freelancer@example.com",
        status="AWAITING_FUNDS",
    )
    db.add(bounty)
    db.flush()

    escrow = models.Escrow(
        bounty_id=bounty.id,
        paypal_order_id="ORDER-IDEMPOTENT-456",
        paypal_authorization_id="AUTH-ALREADY-SET",
    )
    db.add(escrow)
    db.commit()
    bounty_id = bounty.id
    db.close()

    payload = {
        "id": "WH-IDEMPOTENT-2",
        "event_type": "CHECKOUT.ORDER.APPROVED",
        "resource": {"id": "ORDER-IDEMPOTENT-456"},
    }

    with patch("main.verify_webhook_signature", return_value=True), \
         patch("main.authorize_order") as mock_auth:
        response = client.post(
            "/webhooks/paypal",
            headers=SAMPLE_HEADERS,
            content=json.dumps(payload),
        )

    assert response.status_code == 200
    mock_auth.assert_not_called()

    verify_db = TestingSessionLocal()
    updated_bounty = verify_db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    assert updated_bounty.status == "LOCKED"
    verify_db.close()


def test_payment_payouts_item_succeeded_split_freelancer(client):
    """
    Asserts PAYMENT.PAYOUTS-ITEM.SUCCEEDED with sender_item_id='bounty_{id}_freelancer'
    transitions Bounty status to COMPLETED.
    """
    db = TestingSessionLocal()
    bounty = models.Bounty(
        title="Fix Concurrency Bug",
        acceptance_criteria="Zero race conditions under 100 concurrent workers",
        amount_usd=500.0,
        freelancer_email="dev@example.com",
        status="LOCKED",
    )
    db.add(bounty)
    db.commit()
    bounty_id = bounty.id
    db.close()

    payload = {
        "id": "WH-PAYOUT-SUCCEEDED-SPLIT",
        "event_type": "PAYMENT.PAYOUTS-ITEM.SUCCEEDED",
        "resource": {
            "payout_item_id": "ITEM-12345",
            "payout_item": {
                "sender_item_id": f"bounty_{bounty_id}_freelancer",
                "amount": {"value": "450.00", "currency": "USD"},
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

    verify_db = TestingSessionLocal()
    updated_bounty = verify_db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    assert updated_bounty.status == "COMPLETED"
    verify_db.close()


def test_payment_payouts_item_succeeded_split_platform_fee(client):
    """
    Asserts PAYMENT.PAYOUTS-ITEM.SUCCEEDED for platform fee processes cleanly without affecting COMPLETED state.
    """
    db = TestingSessionLocal()
    bounty = models.Bounty(
        title="Platform Fee Bounty",
        acceptance_criteria="Pass",
        amount_usd=200.0,
        freelancer_email="dev@example.com",
        status="COMPLETED",
    )
    db.add(bounty)
    db.commit()
    bounty_id = bounty.id
    db.close()

    payload = {
        "id": "WH-PAYOUT-FEE-SUCCEEDED",
        "event_type": "PAYMENT.PAYOUTS-ITEM.SUCCEEDED",
        "resource": {
            "payout_item_id": "ITEM-FEE-123",
            "payout_item": {
                "sender_item_id": f"bounty_{bounty_id}_platform_fee",
                "amount": {"value": "20.00", "currency": "USD"},
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
    verify_db = TestingSessionLocal()
    updated_bounty = verify_db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    assert updated_bounty.status == "COMPLETED"
    verify_db.close()


def test_payment_payouts_item_failed(client):
    """
    Asserts PAYMENT.PAYOUTS-ITEM.FAILED transitions Bounty status to FAILED_PAYOUT.
    """
    db = TestingSessionLocal()
    bounty = models.Bounty(
        title="Deploy Pipeline",
        acceptance_criteria="CI/CD runs green",
        amount_usd=150.0,
        freelancer_email="dev@example.com",
        status="LOCKED",
    )
    db.add(bounty)
    db.commit()
    bounty_id = bounty.id
    db.close()

    payload = {
        "id": "WH-PAYOUT-FAILED-1",
        "event_type": "PAYMENT.PAYOUTS-ITEM.FAILED",
        "resource": {
            "payout_item_id": "ITEM-FAIL-888",
            "sender_item_id": f"bounty_{bounty_id}_freelancer",
            "errors": {"name": "RECEIVER_UNREGISTERED", "message": "Recipient has no PayPal account"},
        },
    }

    with patch("main.verify_webhook_signature", return_value=True):
        response = client.post(
            "/webhooks/paypal",
            headers=SAMPLE_HEADERS,
            content=json.dumps(payload),
        )

    assert response.status_code == 200

    verify_db = TestingSessionLocal()
    updated_bounty = verify_db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    assert updated_bounty.status == "FAILED_PAYOUT"
    verify_db.close()


def test_payment_authorization_created(client):
    """
    Asserts PAYMENT.AUTHORIZATION.CREATED confirms authorization in Escrow and sets Bounty to LOCKED.
    """
    db = TestingSessionLocal()
    bounty = models.Bounty(
        title="UI Polish",
        acceptance_criteria="Responsive styles",
        amount_usd=80.0,
        freelancer_email="frontend@example.com",
        status="AWAITING_FUNDS",
    )
    db.add(bounty)
    db.flush()

    escrow = models.Escrow(
        bounty_id=bounty.id,
        paypal_order_id="ORDER-AUTH-TEST-1",
        paypal_authorization_id=None,
    )
    db.add(escrow)
    db.commit()
    bounty_id = bounty.id
    db.close()

    payload = {
        "id": "WH-AUTH-CREATED-1",
        "event_type": "PAYMENT.AUTHORIZATION.CREATED",
        "resource": {
            "id": "AUTH-CONFIRMED-321",
            "supplementary_data": {
                "related_ids": {
                    "order_id": "ORDER-AUTH-TEST-1",
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

    verify_db = TestingSessionLocal()
    updated_bounty = verify_db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    updated_escrow = verify_db.query(models.Escrow).filter(models.Escrow.bounty_id == bounty_id).first()

    assert updated_bounty.status == "LOCKED"
    assert updated_escrow.paypal_authorization_id == "AUTH-CONFIRMED-321"
    verify_db.close()


def test_payment_capture_completed(client):
    """
    Asserts PAYMENT.CAPTURE.COMPLETED updates paypal_capture_id on the Escrow record.
    """
    db = TestingSessionLocal()
    bounty = models.Bounty(
        title="API Security",
        acceptance_criteria="OWASP checks passed",
        amount_usd=300.0,
        freelancer_email="sec@example.com",
        status="LOCKED",
    )
    db.add(bounty)
    db.flush()

    escrow = models.Escrow(
        bounty_id=bounty.id,
        paypal_order_id="ORDER-CAP-TEST",
        paypal_authorization_id="AUTH-CAP-REL",
        paypal_capture_id=None,
    )
    db.add(escrow)
    db.commit()
    bounty_id = bounty.id
    db.close()

    payload = {
        "id": "WH-CAPTURE-COMPLETED-1",
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {
            "id": "CAPTURE-ABC-123",
            "supplementary_data": {
                "related_ids": {
                    "authorization_id": "AUTH-CAP-REL",
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

    verify_db = TestingSessionLocal()
    updated_escrow = verify_db.query(models.Escrow).filter(models.Escrow.bounty_id == bounty_id).first()
    assert updated_escrow.paypal_capture_id == "CAPTURE-ABC-123"
    verify_db.close()


def test_calculate_payout_split():
    """
    Asserts calculate_payout_split correctly splits amounts with a percentage fee.
    """
    freelancer, fee = calculate_payout_split(100.0, 0.10)
    assert freelancer == 90.0
    assert fee == 10.0

    freelancer, fee = calculate_payout_split(333.33, 0.10)
    assert float(freelancer) == 300.00
    assert float(fee) == 33.33
    assert float(round(freelancer + fee, 2)) == 333.33


def test_execute_payout_sends_split_payload():
    """
    Asserts execute_payout constructs two items (freelancer & treasury fee) when fee > 0.
    """
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"batch_header": {"payout_batch_id": "BATCH-123"}}
    mock_resp.status_code = 200

    with patch("paypal_client.get_access_token", return_value="mock_token"), \
         patch("paypal_client.requests.post", return_value=mock_resp) as mock_post:
        result = execute_payout(
            freelancer_email="coder@example.com",
            amount=500.0,
            bounty_id=77,
            platform_fee_percent=0.10,
            treasury_email="treasury@platform.com",
        )

        assert result.get("payout_batch_id") == "BATCH-123" or result.get("batch_header", {}).get("payout_batch_id") == "BATCH-123"
        mock_post.assert_called_once()
        sent_body = mock_post.call_args[1]["json"]
        items = sent_body["items"]
        assert len(items) == 2

        # Item 0: Freelancer ($450.00)
        assert items[0]["receiver"] == "coder@example.com"
        assert items[0]["amount"]["value"] == "450.00"
        assert items[0]["sender_item_id"] == "bounty_77_freelancer"

        # Item 1: Platform Fee ($50.00)
        assert items[1]["receiver"] == "treasury@platform.com"
        assert items[1]["amount"]["value"] == "50.00"
        assert items[1]["sender_item_id"] == "bounty_77_platform_fee"


def test_verify_webhook_signature_client_unit():
    """
    Unit tests for verify_webhook_signature in paypal_client.py:
    - Missing headers returns False
    - SUCCESS status from PayPal API returns True
    - FAILURE status from PayPal API returns False
    """
    raw_body = b'{"id": "EVENT-1", "event_type": "CHECKOUT.ORDER.APPROVED"}'

    # Missing header
    incomplete_headers = {"paypal-transmission-id": "123"}
    assert verify_webhook_signature(incomplete_headers, raw_body) is False

    # Mock PayPal SUCCESS
    mock_post_success = MagicMock()
    mock_post_success.status_code = 200
    mock_post_success.json.return_value = {"verification_status": "SUCCESS"}

    with patch("paypal_client.get_access_token", return_value="mock_token"), \
         patch("paypal_client.requests.post", return_value=mock_post_success) as mock_req, \
         patch.dict("os.environ", {"PAYPAL_WEBHOOK_ID": "WH-123-CONFIG"}):
        result = verify_webhook_signature(SAMPLE_HEADERS, raw_body)
        assert result is True
        mock_req.assert_called_once()
        sent_payload = mock_req.call_args[1]["json"]
        assert sent_payload["transmission_id"] == "transmission-12345"
        assert sent_payload["webhook_id"] == "WH-123-CONFIG"
        assert sent_payload["webhook_event"]["id"] == "EVENT-1"

    # Mock PayPal FAILURE
    mock_post_failure = MagicMock()
    mock_post_failure.status_code = 200
    mock_post_failure.json.return_value = {"verification_status": "FAILURE"}

    with patch("paypal_client.get_access_token", return_value="mock_token"), \
         patch("paypal_client.requests.post", return_value=mock_post_failure), \
         patch.dict("os.environ", {"PAYPAL_WEBHOOK_ID": "WH-123-CONFIG"}):
        result = verify_webhook_signature(SAMPLE_HEADERS, raw_body)
        assert result is False
