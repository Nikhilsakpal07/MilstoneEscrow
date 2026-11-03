import os
import time
import json
import logging
from decimal import Decimal, ROUND_HALF_UP
import requests
from dotenv import load_dotenv

from config import PLATFORM_FEE_PERCENT, PLATFORM_TREASURY_EMAIL

load_dotenv()

logger = logging.getLogger("milestone_escrow.paypal")

PAYPAL_BASE_URL = os.getenv("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")
PAYPAL_WEBHOOK_ID = os.getenv("PAYPAL_WEBHOOK_ID")


class PayPalVoidError(Exception):
    """Exception raised when a PayPal authorization cannot be voided."""
    def __init__(self, message: str, status_code: int | None = None, details: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


class PayPalReauthorizationError(Exception):
    """Exception raised when a PayPal authorization cannot be reauthorized."""
    def __init__(self, message: str, status_code: int | None = None, details: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


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


def verify_webhook_signature(headers: dict, raw_body: bytes) -> bool:
    """
    Verifies incoming webhook signature with PayPal API.
    Calls POST /v1/notifications/verify-webhook-signature.
    Returns True if verification_status is SUCCESS, False otherwise.
    """
    normalized_headers = {str(k).lower(): v for k, v in headers.items()}

    transmission_id = normalized_headers.get("paypal-transmission-id")
    transmission_time = normalized_headers.get("paypal-transmission-time")
    cert_url = normalized_headers.get("paypal-cert-url")
    auth_algo = normalized_headers.get("paypal-auth-algo")
    transmission_sig = normalized_headers.get("paypal-transmission-sig")
    webhook_id = os.getenv("PAYPAL_WEBHOOK_ID") or PAYPAL_WEBHOOK_ID

    if not all([transmission_id, transmission_time, cert_url, auth_algo, transmission_sig, webhook_id]):
        logger.warning(
            "Missing required PayPal webhook headers or PAYPAL_WEBHOOK_ID: "
            f"transmission_id={transmission_id}, transmission_time={transmission_time}, "
            f"cert_url={cert_url}, auth_algo={auth_algo}, transmission_sig={transmission_sig}, "
            f"webhook_id={webhook_id}"
        )
        return False

    try:
        if isinstance(raw_body, bytes):
            webhook_event = json.loads(raw_body.decode("utf-8"))
        elif isinstance(raw_body, str):
            webhook_event = json.loads(raw_body)
        elif isinstance(raw_body, dict):
            webhook_event = raw_body
        else:
            logger.warning(f"Unexpected raw_body type: {type(raw_body)}")
            return False
    except Exception as e:
        logger.warning(f"Failed to parse raw_body as JSON for webhook verification: {e}")
        return False

    try:
        token = get_access_token()
    except Exception as e:
        logger.error(f"Failed to obtain PayPal access token for webhook verification: {e}")
        return False

    url = f"{PAYPAL_BASE_URL}/v1/notifications/verify-webhook-signature"
    req_headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    payload = {
        "transmission_id": transmission_id,
        "transmission_time": transmission_time,
        "cert_url": cert_url,
        "auth_algo": auth_algo,
        "transmission_sig": transmission_sig,
        "webhook_id": webhook_id,
        "webhook_event": webhook_event,
    }

    try:
        response = requests.post(url, headers=req_headers, json=payload, timeout=10)
        if response.status_code == 200:
            data = response.json()
            status_val = data.get("verification_status")
            return status_val == "SUCCESS"
        else:
            logger.warning(
                f"PayPal verify-webhook-signature responded with status {response.status_code}: {response.text}"
            )
            return False
    except Exception as e:
        logger.error(f"Error calling PayPal verify-webhook-signature: {e}")
        return False


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


def void_authorization(authorization_id: str) -> dict | None:
    """
    Calls POST /v2/payments/authorizations/{authorization_id}/void to release held funds.
    Raises PayPalVoidError on failure.
    """
    token = get_access_token()
    url = f"{PAYPAL_BASE_URL}/v2/payments/authorizations/{authorization_id}/void"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "PayPal-Request-Id": f"void_auth_{authorization_id}",
    }

    try:
        response = requests.post(url, headers=headers, json={}, timeout=10)
        if response.status_code == 204:
            logger.info("Successfully voided PayPal authorization: %s", authorization_id)
            return {"status": "VOIDED"}
        elif response.status_code == 200:
            logger.info("PayPal void returned 200 for authorization: %s", authorization_id)
            try:
                return response.json()
            except Exception:
                return {"status": "VOIDED"}
        else:
            try:
                err_data = response.json()
                msg = err_data.get("message") or err_data.get("details", [{}])[0].get("description") or response.text
            except Exception:
                err_data = {}
                msg = response.text

            logger.error(
                "PayPal void_authorization failed for %s (status %s): %s",
                authorization_id,
                response.status_code,
                msg,
            )
            raise PayPalVoidError(
                message=f"Failed to void authorization {authorization_id}: {msg}",
                status_code=response.status_code,
                details=err_data,
            )
    except PayPalVoidError:
        raise
    except Exception as e:
        logger.error("Unexpected error during PayPal void_authorization for %s: %s", authorization_id, e)
        raise PayPalVoidError(f"Unexpected error voiding authorization {authorization_id}: {e}")


def reauthorize_payment(authorization_id: str, amount: float | Decimal, currency: str = "USD") -> dict:
    """
    Calls POST /v2/payments/authorizations/{authorization_id}/reauthorize to refresh fund guarantees.
    Raises PayPalReauthorizationError on 400/422 or unexpected failure.
    """
    token = get_access_token()
    url = f"{PAYPAL_BASE_URL}/v2/payments/authorizations/{authorization_id}/reauthorize"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "PayPal-Request-Id": f"reauth_{authorization_id}_{int(time.time())}",
    }

    amount_val = f"{Decimal(str(amount)):.2f}"
    payload = {
        "amount": {
            "currency_code": currency,
            "value": amount_val,
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code in (200, 201):
            data = response.json()
            logger.info("Successfully reauthorized payment for authorization_id=%s: %s", authorization_id, data)
            return data
        else:
            try:
                err_data = response.json()
                msg = err_data.get("message") or err_data.get("details", [{}])[0].get("description") or response.text
            except Exception:
                err_data = {}
                msg = response.text

            logger.error(
                "PayPal reauthorize_payment failed for %s (status %s): %s",
                authorization_id,
                response.status_code,
                msg,
            )
            raise PayPalReauthorizationError(
                message=f"Failed to reauthorize payment {authorization_id}: {msg}",
                status_code=response.status_code,
                details=err_data,
            )
    except PayPalReauthorizationError:
        raise
    except Exception as e:
        logger.error("Unexpected error during PayPal reauthorize_payment for %s: %s", authorization_id, e)
        raise PayPalReauthorizationError(f"Unexpected error reauthorizing payment {authorization_id}: {e}")


def calculate_payout_split(
    amount: float | Decimal,
    platform_fee_percent: float | Decimal = 0.10,
) -> tuple[Decimal, Decimal]:
    """
    Calculates the freelancer net amount and platform fee split rounded strictly
    to 2 decimal places using Decimal and ROUND_HALF_UP.
    Returns (freelancer_amount, platform_fee).
    """
    amt = Decimal(str(amount))
    pct = Decimal(str(platform_fee_percent))
    two_places = Decimal("0.01")
    fee = (amt * pct).quantize(two_places, rounding=ROUND_HALF_UP)
    freelancer = (amt - fee).quantize(two_places, rounding=ROUND_HALF_UP)
    return freelancer, fee


def execute_payout(
    freelancer_email: str,
    amount: float | Decimal,
    bounty_id: int,
    platform_fee_percent: float | Decimal | None = None,
    treasury_email: str | None = None,
) -> dict:
    """
    Executes an atomic PayPal batch payout splitting the captured funds between
    the freelancer (net payout) and platform treasury (commission).
    Returns response JSON containing payout_batch_id.
    """
    token = get_access_token()
    url = f"{PAYPAL_BASE_URL}/v1/payments/payouts"

    if platform_fee_percent is None:
        platform_fee_percent = PLATFORM_FEE_PERCENT

    if treasury_email is None:
        treasury_email = PLATFORM_TREASURY_EMAIL

    sender_batch_id = f"bounty_{bounty_id}_{int(time.time())}"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "PayPal-Request-Id": sender_batch_id,
    }

    freelancer_amount, platform_fee = calculate_payout_split(amount, platform_fee_percent)

    items = [
        {
            "recipient_type": "EMAIL",
            "amount": {"value": f"{freelancer_amount:.2f}", "currency": "USD"},
            "receiver": freelancer_email,
            "note": f"Escrow payout for Bounty #{bounty_id}",
            "sender_item_id": f"bounty_{bounty_id}_freelancer",
        },
        {
            "recipient_type": "EMAIL",
            "amount": {"value": f"{platform_fee:.2f}", "currency": "USD"},
            "receiver": treasury_email,
            "note": f"Platform commission for Bounty #{bounty_id}",
            "sender_item_id": f"bounty_{bounty_id}_platform_fee",
        },
    ]

    payload = {
        "sender_batch_header": {
            "sender_batch_id": sender_batch_id,
            "email_subject": f"Payout for Bounty #{bounty_id}",
        },
        "items": items,
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    data = response.json()

    # Ensure payout_batch_id is accessible at the top level
    batch_id = data.get("batch_header", {}).get("payout_batch_id") or data.get("payout_batch_id")
    if batch_id and "payout_batch_id" not in data:
        data["payout_batch_id"] = batch_id

    return data
