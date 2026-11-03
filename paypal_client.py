import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

PAYPAL_BASE_URL = "https://api-m.sandbox.paypal.com"


def get_access_token() -> str:
    """
    Fetches an OAuth2 token using client_credentials grant type from PayPal Sandbox.
    """
    client_id = os.getenv("PAYPAL_CLIENT_ID")
    client_secret = os.getenv("PAYPAL_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise ValueError("PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET must be set in environment variables.")

    url = f"{PAYPAL_BASE_URL}/v1/oauth2/token"
    headers = {
        "Accept": "application/json",
        "Accept-Language": "en_US",
    }
    data = {
        "grant_type": "client_credentials",
    }

    response = requests.post(
        url,
        auth=(client_id, client_secret),
        headers=headers,
        data=data,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def authorize_order(order_id: str) -> str:
    """
    Calls POST /v2/checkout/orders/{order_id}/authorize to lock the funds.
    Parses the response to return the authorization_id from
    purchase_units[0].payments.authorizations[0].id.
    """
    token = get_access_token()
    url = f"{PAYPAL_BASE_URL}/v2/checkout/orders/{order_id}/authorize"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    response = requests.post(url, headers=headers, json={})
    response.raise_for_status()
    data = response.json()
    return data["purchase_units"][0]["payments"]["authorizations"][0]["id"]


def capture_authorization(
    authorization_id: str,
    amount: float | None = None,
    is_final_capture: bool = True,
) -> dict:
    """
    Calls POST /v2/payments/authorizations/{authorization_id}/capture to pull the funds.
    Supports full or partial captures.
    """
    token = get_access_token()
    url = f"{PAYPAL_BASE_URL}/v2/payments/authorizations/{authorization_id}/capture"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    payload: dict = {
        "final_capture": is_final_capture,
    }
    if amount is not None:
        payload["amount"] = {
            "value": f"{amount:.2f}",
            "currency_code": "USD",
        }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()


def execute_payout(
    freelancer_email: str,
    amount: float,
    bounty_id: int,
    milestone_id: int | None = None,
) -> dict:
    """
    Calls POST /v1/payments/payouts to send the specific amount to the freelancer_email.
    Generates a unique sender_batch_id using timestamp, bounty_id, and milestone_id.
    """
    token = get_access_token()
    url = f"{PAYPAL_BASE_URL}/v1/payments/payouts"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    # PayPal sender_batch_id has a max length limit of 30 characters
    if milestone_id is not None:
        sender_batch_id = f"b_{bounty_id}_m_{milestone_id}_{int(time.time())}"
        email_subject = f"Milestone #{milestone_id} Escrow Payout (Bounty #{bounty_id})"
        email_message = f"You received a payout of ${amount:.2f} USD for Milestone #{milestone_id} on Bounty #{bounty_id}."
        note = f"Milestone #{milestone_id} payout for Bounty #{bounty_id}"
        sender_item_id = f"item_{bounty_id}_m_{milestone_id}"
    else:
        sender_batch_id = f"bounty_{bounty_id}_{int(time.time())}"
        email_subject = f"Payout for Bounty #{bounty_id}"
        email_message = f"You have received a payout of ${amount:.2f} USD for completing bounty #{bounty_id}."
        note = f"Payout for bounty #{bounty_id}"
        sender_item_id = f"bounty_item_{bounty_id}"

    payload = {
        "sender_batch_header": {
            "sender_batch_id": sender_batch_id,
            "email_subject": email_subject,
            "email_message": email_message,
        },
        "items": [
            {
                "recipient_type": "EMAIL",
                "amount": {
                    "value": f"{amount:.2f}",
                    "currency": "USD",
                },
                "receiver": freelancer_email,
                "note": note,
                "sender_item_id": sender_item_id,
            }
        ],
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()
