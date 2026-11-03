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


def capture_authorization(authorization_id: str) -> dict:
    """
    Calls POST /v2/payments/authorizations/{authorization_id}/capture with
    {"final_capture": True} to pull the funds.
    """
    token = get_access_token()
    url = f"{PAYPAL_BASE_URL}/v2/payments/authorizations/{authorization_id}/capture"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    payload = {
        "final_capture": True,
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()


def execute_payout(freelancer_email: str, amount: float, bounty_id: int) -> dict:
    """
    Calls POST /v1/payments/payouts to send the amount to the freelancer_email.
    Generates a unique sender_batch_id using the current timestamp and bounty_id.
    """
    token = get_access_token()
    url = f"{PAYPAL_BASE_URL}/v1/payments/payouts"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    sender_batch_id = f"bounty_{bounty_id}_{int(time.time())}"

    payload = {
        "sender_batch_header": {
            "sender_batch_id": sender_batch_id,
            "email_subject": f"Payout for Bounty #{bounty_id}",
            "email_message": f"You have received a payout of ${amount:.2f} USD for completing bounty #{bounty_id}.",
        },
        "items": [
            {
                "recipient_type": "EMAIL",
                "amount": {
                    "value": f"{amount:.2f}",
                    "currency": "USD",
                },
                "receiver": freelancer_email,
                "note": f"Payout for bounty #{bounty_id}",
                "sender_item_id": f"bounty_item_{bounty_id}",
            }
        ],
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()

