from decimal import Decimal
from unittest.mock import patch, MagicMock

import models
from conftest import TestingSessionLocal, client
from paypal_client import calculate_payout_split, execute_payout


def test_fee_calculation_rounding():
    """
    Unit test: Verifies accurate decimal calculations on odd amounts
    using ROUND_HALF_UP (e.g., $99.99 split 90/10).
    """
    # $99.99 split with 10% platform fee
    freelancer, fee = calculate_payout_split(99.99, 0.10)
    assert fee == Decimal("10.00")
    assert freelancer == Decimal("89.99")
    assert freelancer + fee == Decimal("99.99")

    # $100.00 standard split
    freelancer, fee = calculate_payout_split(100.00, 0.10)
    assert fee == Decimal("10.00")
    assert freelancer == Decimal("90.00")
    assert freelancer + fee == Decimal("100.00")

    # $333.33 odd split
    freelancer, fee = calculate_payout_split(333.33, 0.10)
    assert fee == Decimal("33.33")
    assert freelancer == Decimal("300.00")
    assert freelancer + fee == Decimal("333.33")


def test_execute_batch_payout_payload():
    """
    Unit test: Mocks the PayPal API call and asserts that the request payload contains
    exactly 2 items with correct emails, notes, sender_item_ids, and amounts.
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "batch_header": {
            "payout_batch_id": "BATCH-PAYOUT-999",
            "batch_status": "PENDING",
        }
    }

    with patch("paypal_client.get_access_token", return_value="mock_token"), \
         patch("paypal_client.requests.post", return_value=mock_resp) as mock_post:
        res = execute_payout(
            freelancer_email="freelancer@example.com",
            amount=99.99,
            bounty_id=42,
            platform_fee_percent=0.10,
            treasury_email="treasury@platform.com",
        )

        assert res["payout_batch_id"] == "BATCH-PAYOUT-999"
        mock_post.assert_called_once()
        url = mock_post.call_args[0][0]
        headers = mock_post.call_args[1]["headers"]
        payload = mock_post.call_args[1]["json"]

        assert "/v1/payments/payouts" in url
        assert headers["Authorization"] == "Bearer mock_token"
        assert "bounty_42_" in headers["PayPal-Request-Id"]

        items = payload["items"]
        assert len(items) == 2

        # Item 1: Freelancer Net Amount (90%)
        assert items[0]["recipient_type"] == "EMAIL"
        assert items[0]["receiver"] == "freelancer@example.com"
        assert items[0]["amount"] == {"value": "89.99", "currency": "USD"}
        assert items[0]["note"] == "Escrow payout for Bounty #42"
        assert items[0]["sender_item_id"] == "bounty_42_freelancer"

        # Item 2: Platform Fee (10%)
        assert items[1]["recipient_type"] == "EMAIL"
        assert items[1]["receiver"] == "treasury@platform.com"
        assert items[1]["amount"] == {"value": "10.00", "currency": "USD"}
        assert items[1]["note"] == "Platform commission for Bounty #42"
        assert items[1]["sender_item_id"] == "bounty_42_platform_fee"


def test_submit_work_success_records_fee_in_db(client):
    """
    Integration test: Asserts that platform_fee_usd, freelancer_payout_usd,
    and payout_batch_id are correctly committed to the DB on a successful review.
    """
    db = TestingSessionLocal()
    bounty = models.Bounty(
        title="Implement Fee Deduction",
        acceptance_criteria="All tests pass",
        amount_usd=99.99,
        freelancer_email="freelancer@example.com",
        status="LOCKED",
    )
    db.add(bounty)
    db.flush()

    escrow = models.Escrow(
        bounty_id=bounty.id,
        paypal_order_id="ORDER-FEE-TEST",
        paypal_authorization_id="AUTH-FEE-TEST",
        status="HELD",
    )
    db.add(escrow)
    db.commit()
    bounty_id = bounty.id
    db.close()

    mock_eval = {"passed": True, "feedback": "Code approved."}
    mock_capture = {"id": "CAPTURE-FEE-123"}
    mock_payout = {
        "batch_header": {"payout_batch_id": "BATCH-FEE-RECORD"},
        "payout_batch_id": "BATCH-FEE-RECORD",
    }

    with patch("main.evaluate_submission", return_value=mock_eval), \
         patch("main.capture_authorization", return_value=mock_capture), \
         patch("main.execute_payout", return_value=mock_payout):
        response = client.post(
            f"/api/bounties/{bounty_id}/submit-work",
            json={"github_url": "https://github.com/user/project"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "COMPLETED"
    assert data["platform_fee_usd"] == 10.00
    assert data["freelancer_payout_usd"] == 89.99
    assert data["payout_batch_id"] == "BATCH-FEE-RECORD"

    verify_db = TestingSessionLocal()
    updated_bounty = verify_db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    updated_escrow = verify_db.query(models.Escrow).filter(models.Escrow.bounty_id == bounty_id).first()

    assert updated_bounty.platform_fee_usd == 10.00
    assert updated_bounty.freelancer_payout_usd == 89.99
    assert updated_bounty.payout_batch_id == "BATCH-FEE-RECORD"
    assert updated_bounty.status == "COMPLETED"

    assert updated_escrow.platform_fee_usd == 10.00
    assert updated_escrow.freelancer_payout_usd == 89.99
    assert updated_escrow.payout_batch_id == "BATCH-FEE-RECORD"
    assert updated_escrow.status == "CAPTURED"
    verify_db.close()

