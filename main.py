import logging
import json
import re
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db, engine
import models
import config
from paypal_client import (
    authorize_order,
    capture_authorization,
    void_authorization,
    reauthorize_payment,
    execute_payout,
    verify_webhook_signature,
    calculate_payout_split,
    PayPalVoidError,
    PayPalReauthorizationError,
)
from qa_agent import evaluate_submission

# Ensure database tables are created on startup
models.Base.metadata.create_all(bind=engine)

# Validate application configuration on boot
config.validate_config()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("milestone_escrow")

# Max allowable revisions before permanent rejection
MAX_REVISIONS = 2

app = FastAPI(title="MilestoneEscrow API")

# Configure CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class BountyCreate(BaseModel):
    title: str
    acceptance_criteria: str
    amount_usd: float
    freelancer_email: str
    paypal_order_id: str


class WorkSubmission(BaseModel):
    github_url: str


def _extract_bounty_metadata_from_payout_resource(resource: dict) -> tuple[int | None, str]:
    """
    Extracts the integer bounty ID and role ('freelancer', 'platform_fee', or 'general')
    from payout item metadata, sender_item_id, note, or batch ID.
    """
    sender_item_id = (
        resource.get("sender_item_id")
        or resource.get("payout_item", {}).get("sender_item_id")
    )
    if sender_item_id:
        sender_str = str(sender_item_id)
        role = "general"
        if "freelancer" in sender_str:
            role = "freelancer"
        elif "platform_fee" in sender_str or "fee" in sender_str:
            role = "platform_fee"

        match_named = re.search(r"bounty_(\d+)(?:_(?:freelancer|platform_fee))?", sender_str)
        if match_named:
            return int(match_named.group(1)), role

        if sender_str.startswith("bounty_item_"):
            val = sender_str[len("bounty_item_"):]
            if val.isdigit():
                return int(val), role

        if sender_str.isdigit():
            return int(sender_str), role

        match = re.search(r"\d+", sender_str)
        if match:
            return int(match.group(0)), role

    note = (
        resource.get("payout_item", {}).get("note")
        or resource.get("note", "")
    )
    if note:
        role = "platform_fee" if "platform fee" in str(note).lower() else "freelancer"
        match = re.search(r"#(\d+)", str(note))
        if match:
            return int(match.group(1)), role

    sender_batch_id = (
        resource.get("sender_batch_id")
        or resource.get("sender_batch_header", {}).get("sender_batch_id")
    )
    if sender_batch_id and str(sender_batch_id).startswith("bounty_"):
        parts = str(sender_batch_id).split("_")
        if len(parts) >= 2 and parts[1].isdigit():
            return int(parts[1]), "general"

    return None, "unknown"


@app.get("/")
def read_root():
    return {"message": "MilestoneEscrow Backend is running."}


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    return {"status": "ok", "db_connected": True}


@app.get("/api/bounties")
def list_bounties(db: Session = Depends(get_db)):
    """
    Returns a list of all bounties.
    """
    bounties = db.query(models.Bounty).order_by(models.Bounty.id.desc()).all()
    return [
        {
            "id": b.id,
            "title": b.title,
            "acceptance_criteria": b.acceptance_criteria,
            "amount_usd": b.amount_usd,
            "freelancer_email": b.freelancer_email,
            "status": b.status,
            "revision_count": b.revision_count,
            "revision_deadline": b.revision_deadline.isoformat() if b.revision_deadline else None,
            "platform_fee_usd": b.platform_fee_usd,
            "freelancer_payout_usd": b.freelancer_payout_usd,
            "payout_batch_id": b.payout_batch_id,
        }
        for b in bounties
    ]


@app.post("/api/bounties", status_code=status.HTTP_201_CREATED)
def create_bounty(
    bounty_in: BountyCreate,
    db: Session = Depends(get_db),
):
    """
    Creates a new Bounty with 'LOCKED' status and links an Escrow record
    storing the provided PayPal order ID and authorization ID.
    """
    logger.debug("Incoming Bounty Creation Payload: %s", bounty_in.model_dump())

    new_bounty = models.Bounty(
        title=bounty_in.title,
        acceptance_criteria=bounty_in.acceptance_criteria,
        amount_usd=bounty_in.amount_usd,
        freelancer_email=bounty_in.freelancer_email,
        status="LOCKED",
        revision_count=0,
    )
    db.add(new_bounty)
    db.flush()

    authorization_id = None
    try:
        authorization_id = authorize_order(bounty_in.paypal_order_id)
        logger.info("PayPal Authorized Successfully! Authorization ID: %s", authorization_id)
    except Exception as e:
        logger.warning("Could not authorize order via PayPal API synchronously: %s", e)

    new_escrow = models.Escrow(
        bounty_id=new_bounty.id,
        paypal_order_id=bounty_in.paypal_order_id,
        paypal_authorization_id=authorization_id,
        status="HELD",
    )
    db.add(new_escrow)

    db.commit()
    db.refresh(new_bounty)

    return {"bounty_id": new_bounty.id, "id": new_bounty.id}


@app.post("/api/bounties/{bounty_id}/cancel", status_code=status.HTTP_200_OK)
def cancel_bounty(bounty_id: int, db: Session = Depends(get_db)):
    """
    Employer cancels an unfilled or pending bounty:
    1. Validates that the bounty is in a cancelable state (e.g. LOCKED, AWAITING_FUNDS, NEEDS_REVISION).
    2. Voids the PayPal authorization to immediately release held funds.
    3. Updates Escrow.status to 'VOIDED' and Bounty.status to 'CANCELED'.
    """
    bounty = db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    if not bounty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bounty with ID {bounty_id} not found.",
        )

    if bounty.status not in ("LOCKED", "AWAITING_FUNDS", "NEEDS_REVISION"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Bounty cannot be canceled in its current status: '{bounty.status}'.",
        )

    escrow = bounty.escrow or db.query(models.Escrow).filter(models.Escrow.bounty_id == bounty_id).first()

    if escrow:
        if escrow.paypal_authorization_id and escrow.status != "VOIDED":
            try:
                void_authorization(escrow.paypal_authorization_id)
            except PayPalVoidError as pve:
                logger.error("PayPalVoidError during bounty cancellation: %s", pve)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to void PayPal authorization: {pve}",
                )
            except Exception as e:
                logger.error("Unexpected error during bounty cancellation void: %s", e)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to release escrow funds: {e}",
                )

        escrow.status = "VOIDED"
        escrow.voided_at = datetime.now(timezone.utc)

    bounty.status = "CANCELED"
    db.commit()
    db.refresh(bounty)

    return {
        "status": "CANCELED",
        "bounty_id": bounty.id,
        "detail": "Bounty canceled and escrow authorization voided.",
    }


@app.post("/api/bounties/{bounty_id}/expire-revision", status_code=status.HTTP_200_OK)
def expire_revision(bounty_id: int, db: Session = Depends(get_db)):
    """
    Checks if a revision deadline has passed for a bounty in NEEDS_REVISION.
    If expired: voids authorization, sets Bounty.status = REJECTED, and logs to AuditLog.
    """
    bounty = db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    if not bounty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bounty with ID {bounty_id} not found.",
        )

    if bounty.status != "NEEDS_REVISION":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Bounty is not currently in NEEDS_REVISION status (current: '{bounty.status}').",
        )

    now = datetime.now(timezone.utc)
    deadline = bounty.revision_deadline
    if deadline:
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)

        if now <= deadline:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Revision deadline has not yet expired.",
            )

    escrow = bounty.escrow or db.query(models.Escrow).filter(models.Escrow.bounty_id == bounty_id).first()
    if escrow and escrow.paypal_authorization_id and escrow.status not in ("VOIDED", "CAPTURED"):
        try:
            void_authorization(escrow.paypal_authorization_id)
        except Exception as e:
            logger.error("Failed to void authorization on revision expiration: %s", e)
        escrow.status = "VOIDED"
        escrow.voided_at = now

    bounty.status = "REJECTED"

    audit_log = models.AuditLog(
        bounty_id=bounty.id,
        trajectory_id=f"bounty_{bounty.id}_expired",
        passed=False,
        ai_feedback="Revision deadline expired without a passing submission. Escrow authorization voided.",
    )
    db.add(audit_log)

    db.commit()
    db.refresh(bounty)

    return {
        "status": "REJECTED",
        "bounty_id": bounty.id,
        "detail": "Revision window expired. Escrow authorization voided.",
    }


@app.post("/api/bounties/{bounty_id}/submit-work", status_code=status.HTTP_200_OK)
async def submit_work(
    bounty_id: int,
    submission: WorkSubmission,
    db: Session = Depends(get_db),
):
    """
    Submits freelancer work for a bounty:
    1. Fetches the Bounty and associated Escrow from the database.
    2. Runs automated AI QA evaluation on the submitted GitHub repository.
    3. Persists evaluation outcome to the AuditLog table.
    4. Handles state transitions:
       - Case 1: passed == True -> capture authorization, calculate fee split,
                 save figures in DB, trigger execute_payout, persist payout_batch_id, mark COMPLETED.
       - Case 2: passed == False and allow_revision == True and revision_count < MAX_REVISIONS ->
                 set NEEDS_REVISION, reauthorize_payment, set 48h deadline, DO NOT void.
       - Case 3: passed == False and (not allow_revision or revision_count >= MAX_REVISIONS) ->
                 void authorization, mark REJECTED and Escrow VOIDED.
    """
    bounty = db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    if not bounty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bounty with ID {bounty_id} not found.",
        )

    escrow = bounty.escrow or db.query(models.Escrow).filter(models.Escrow.bounty_id == bounty_id).first()

    eval_result = await evaluate_submission(
        github_url=submission.github_url,
        acceptance_criteria=bounty.acceptance_criteria,
        bounty_id=bounty_id,
    )

    passed = eval_result.get("passed", False)
    allow_revision = eval_result.get("allow_revision", False)
    feedback = eval_result.get("feedback", "")

    audit_log = models.AuditLog(
        bounty_id=bounty.id,
        trajectory_id=f"bounty_{bounty_id}",
        passed=passed,
        ai_feedback=feedback,
    )
    db.add(audit_log)
    db.commit()

    # Case 1: All criteria passed successfully
    if passed:
        if not escrow or not escrow.paypal_authorization_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Escrow record with a valid PayPal authorization ID is missing.",
            )

        capture_response = capture_authorization(escrow.paypal_authorization_id)
        if isinstance(capture_response, dict) and "id" in capture_response:
            escrow.paypal_capture_id = capture_response["id"]
        escrow.status = "CAPTURED"

        # 1. Compute platform fee and freelancer net payout
        freelancer_amt, fee_amt = calculate_payout_split(bounty.amount_usd)
        bounty.platform_fee_usd = float(fee_amt)
        bounty.freelancer_payout_usd = float(freelancer_amt)
        if escrow:
            escrow.platform_fee_usd = float(fee_amt)
            escrow.freelancer_payout_usd = float(freelancer_amt)

        # 2. Trigger multi-item batch payout
        payout_response = execute_payout(
            freelancer_email=bounty.freelancer_email,
            amount=bounty.amount_usd,
            bounty_id=bounty_id,
        )

        # 3. Persist payout_batch_id
        batch_id = (
            payout_response.get("payout_batch_id")
            or payout_response.get("batch_header", {}).get("payout_batch_id")
        )
        if batch_id:
            bounty.payout_batch_id = batch_id
            if escrow:
                escrow.payout_batch_id = batch_id

        bounty.status = "COMPLETED"

    # Case 2: Minor failure eligible for revision loop
    elif allow_revision and (bounty.revision_count or 0) < MAX_REVISIONS:
        bounty.status = "NEEDS_REVISION"
        bounty.revision_count = (bounty.revision_count or 0) + 1
        bounty.revision_deadline = datetime.now(timezone.utc) + timedelta(hours=48)

        # Reauthorize payment to refresh fund hold guarantee
        if escrow and escrow.paypal_authorization_id:
            try:
                reauth_result = reauthorize_payment(
                    authorization_id=escrow.paypal_authorization_id,
                    amount=bounty.amount_usd,
                )
                if isinstance(reauth_result, dict) and "id" in reauth_result:
                    escrow.paypal_authorization_id = reauth_result["id"]
                escrow.last_reauthorized_at = datetime.now(timezone.utc)
                logger.info(
                    "Reauthorized PayPal payment for bounty %s, new auth_id: %s",
                    bounty_id,
                    escrow.paypal_authorization_id,
                )
            except Exception as reauth_err:
                logger.warning(
                    "Could not reauthorize PayPal payment during revision grant for bounty %s: %s",
                    bounty_id,
                    reauth_err,
                )

        logger.info(
            "Bounty %s transitioned to NEEDS_REVISION (revision %s/%s). Deadline: %s",
            bounty_id,
            bounty.revision_count,
            MAX_REVISIONS,
            bounty.revision_deadline,
        )

    # Case 3: Complete failure or max revisions exhausted -> Hard rejection
    else:
        if escrow and escrow.paypal_authorization_id and escrow.status not in ("VOIDED", "CAPTURED"):
            try:
                void_authorization(escrow.paypal_authorization_id)
                logger.info("Voided authorization %s after hard rejection on bounty %s", escrow.paypal_authorization_id, bounty_id)
            except Exception as e:
                logger.error("Error voiding authorization %s on hard rejection: %s", escrow.paypal_authorization_id, e)
            escrow.status = "VOIDED"
            escrow.voided_at = datetime.now(timezone.utc)
        elif escrow:
            escrow.status = "VOIDED"
            escrow.voided_at = datetime.now(timezone.utc)

        bounty.status = "REJECTED"

    db.commit()
    db.refresh(bounty)

    return {
        "status": bounty.status,
        "feedback": feedback,
        "passed": passed,
        "allow_revision": allow_revision if not passed else False,
        "revision_count": bounty.revision_count,
        "revision_deadline": bounty.revision_deadline.isoformat() if bounty.revision_deadline else None,
        "platform_fee_usd": bounty.platform_fee_usd,
        "freelancer_payout_usd": bounty.freelancer_payout_usd,
        "payout_batch_id": bounty.payout_batch_id,
    }


@app.post("/webhooks/paypal", status_code=status.HTTP_200_OK)
async def paypal_webhook(request: Request, db: Session = Depends(get_db)):
    """
    PayPal Webhook Endpoint:
    1. Cryptographically verifies incoming webhook signature.
    2. Dispatches events idempotently to update Bounty and Escrow states.
    3. Traps exceptions during processing to prevent webhook retry storms.
    """
    raw_body = await request.body()
    headers = dict(request.headers)

    # 1. Cryptographic Signature Verification
    if not verify_webhook_signature(headers=headers, raw_body=raw_body):
        logger.warning(
            "SECURITY ALERT: PayPal webhook signature verification failed. Rejecting incoming request."
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PayPal webhook signature verification failed",
        )

    # 2. Parse JSON body
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as e:
        logger.error("Malformed JSON in PayPal webhook payload: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    event_id = payload.get("id")
    event_type = payload.get("event_type")
    resource = payload.get("resource", {})

    logger.info("Received PayPal webhook event: id=%s, event_type=%s", event_id, event_type)

    # 3. Robust Event Dispatching
    try:
        if event_type == "CHECKOUT.ORDER.APPROVED":
            order_id = resource.get("id")
            if not order_id:
                logger.warning("CHECKOUT.ORDER.APPROVED event missing order id: %s", payload)
            else:
                escrow = db.query(models.Escrow).filter(models.Escrow.paypal_order_id == order_id).first()
                if escrow:
                    bounty = escrow.bounty or db.query(models.Bounty).filter(models.Bounty.id == escrow.bounty_id).first()
                    if bounty and bounty.status != "LOCKED":
                        bounty.status = "LOCKED"
                        logger.info("Bounty id=%s status transitioned to LOCKED for order=%s", bounty.id, order_id)

                    # Initiate authorize_order if not already handled
                    if not escrow.paypal_authorization_id:
                        try:
                            auth_id = authorize_order(order_id)
                            escrow.paypal_authorization_id = auth_id
                            escrow.status = "HELD"
                            logger.info("Order %s authorized via webhook with authorization_id=%s", order_id, auth_id)
                        except Exception as auth_err:
                            logger.error("Failed to authorize order %s in webhook: %s", order_id, auth_err)
                    db.commit()
                else:
                    logger.warning("No Escrow record found for approved order_id: %s", order_id)

        elif event_type == "PAYMENT.AUTHORIZATION.CREATED":
            auth_id = resource.get("id")
            order_id = (
                resource.get("supplementary_data", {}).get("related_ids", {}).get("order_id")
                or resource.get("parent_payment")
            )

            escrow = None
            if auth_id:
                escrow = db.query(models.Escrow).filter(models.Escrow.paypal_authorization_id == auth_id).first()
            if not escrow and order_id:
                escrow = db.query(models.Escrow).filter(models.Escrow.paypal_order_id == order_id).first()

            if escrow:
                if auth_id and escrow.paypal_authorization_id != auth_id:
                    escrow.paypal_authorization_id = auth_id
                escrow.status = "HELD"
                bounty = escrow.bounty or db.query(models.Bounty).filter(models.Bounty.id == escrow.bounty_id).first()
                if bounty and bounty.status != "LOCKED":
                    bounty.status = "LOCKED"
                    logger.info("Bounty id=%s status set to LOCKED via authorization=%s", bounty.id, auth_id)
                db.commit()
                logger.info("Confirmed authorization record in Escrow id=%s (auth_id=%s)", escrow.id, auth_id)
            else:
                logger.warning("No Escrow found for authorization_id=%s, order_id=%s", auth_id, order_id)

        elif event_type == "PAYMENT.AUTHORIZATION.VOIDED":
            auth_id = resource.get("id")
            order_id = (
                resource.get("supplementary_data", {}).get("related_ids", {}).get("order_id")
                or resource.get("parent_payment")
            )

            escrow = None
            if auth_id:
                escrow = db.query(models.Escrow).filter(models.Escrow.paypal_authorization_id == auth_id).first()
            if not escrow and order_id:
                escrow = db.query(models.Escrow).filter(models.Escrow.paypal_order_id == order_id).first()

            if escrow:
                escrow.status = "VOIDED"
                escrow.voided_at = datetime.now(timezone.utc)
                bounty = escrow.bounty or db.query(models.Bounty).filter(models.Bounty.id == escrow.bounty_id).first()
                if bounty and bounty.status not in ("REJECTED", "CANCELED"):
                    bounty.status = "CANCELED"
                    logger.info("Bounty id=%s transitioned to CANCELED via PAYMENT.AUTHORIZATION.VOIDED", bounty.id)
                db.commit()
                logger.info("Confirmed void of authorization %s in Escrow id=%s", auth_id, escrow.id)
            else:
                logger.warning("No matching Escrow found for voided authorization_id=%s", auth_id)

        elif event_type == "PAYMENT.CAPTURE.COMPLETED":
            capture_id = resource.get("id")
            auth_id = (
                resource.get("supplementary_data", {}).get("related_ids", {}).get("authorization_id")
                or resource.get("parent_payment")
            )
            order_id = resource.get("supplementary_data", {}).get("related_ids", {}).get("order_id")

            escrow = None
            if capture_id:
                escrow = db.query(models.Escrow).filter(models.Escrow.paypal_capture_id == capture_id).first()
            if not escrow and auth_id:
                escrow = db.query(models.Escrow).filter(models.Escrow.paypal_authorization_id == auth_id).first()
            if not escrow and order_id:
                escrow = db.query(models.Escrow).filter(models.Escrow.paypal_order_id == order_id).first()

            if escrow:
                if capture_id and escrow.paypal_capture_id != capture_id:
                    escrow.paypal_capture_id = capture_id
                escrow.status = "CAPTURED"
                db.commit()
                logger.info("Confirmed capture details against Escrow id=%s (capture_id=%s)", escrow.id, capture_id)
            else:
                logger.warning("No matching Escrow found for capture_id=%s", capture_id)

        elif event_type == "PAYMENT.PAYOUTS-ITEM.SUCCEEDED":
            bounty_id, role = _extract_bounty_metadata_from_payout_resource(resource)
            payout_item_id = (
                resource.get("payout_item_id")
                or resource.get("payout_item", {}).get("payout_item_id")
                or resource.get("id")
            )
            if bounty_id:
                bounty = db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
                if bounty:
                    if role in ("freelancer", "general"):
                        if bounty.status != "COMPLETED":
                            bounty.status = "COMPLETED"
                            db.commit()
                            logger.info("Bounty id=%s transitioned to COMPLETED (payout_item_id=%s, role=%s)", bounty_id, payout_item_id, role)
                        else:
                            logger.info("Bounty id=%s already COMPLETED", bounty_id)
                    else:
                        logger.info("Platform treasury fee payout succeeded for Bounty id=%s (payout_item_id=%s)", bounty_id, payout_item_id)
                else:
                    logger.warning("Bounty id=%s not found for payout_item_id=%s", bounty_id, payout_item_id)
            else:
                logger.warning("Could not match Bounty from payout resource: %s", resource)

        elif event_type in ("PAYMENT.PAYOUTS-ITEM.FAILED", "PAYMENT.PAYOUTS-ITEM.UNCLAIMED", "PAYMENT.PAYOUTS-ITEM.CANCELED", "PAYMENT.PAYOUTS-ITEM.BLOCKED", "PAYMENT.PAYOUTS-ITEM.DENIED"):
            bounty_id, role = _extract_bounty_metadata_from_payout_resource(resource)
            error_reason = (
                resource.get("errors")
                or resource.get("payout_item", {}).get("errors")
                or resource.get("error")
                or resource.get("transaction_status")
                or f"Payout status: {resource.get('transaction_status', 'FAILED')}"
            )
            logger.error(
                "ADMIN REVIEW / ALERT: PayPal payout failure! Event=%s, bounty_id=%s, role=%s, reason=%s",
                event_type,
                bounty_id,
                role,
                error_reason,
            )
            if bounty_id:
                bounty = db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
                if bounty:
                    if role in ("freelancer", "general"):
                        bounty.status = "FAILED_PAYOUT"
                        db.commit()
                        logger.info("Bounty id=%s transitioned to FAILED_PAYOUT", bounty_id)
                    else:
                        logger.warning("Platform fee payout failed for Bounty id=%s. Freelancer unaffected. Error: %s", bounty_id, error_reason)
                else:
                    logger.warning("Bounty id=%s not found for failed payout event", bounty_id)
            else:
                logger.warning("Could not extract bounty_id for failed payout event: %s", resource)

        else:
            logger.info("Received unhandled PayPal webhook event_type: %s", event_type)

    except Exception as exc:
        db.rollback()
        logger.error(
            "Error handling PayPal webhook event_id=%s event_type=%s: %s",
            event_id,
            event_type,
            exc,
            exc_info=True,
        )

    return {"status": "received", "event_id": event_id, "event_type": event_type}
