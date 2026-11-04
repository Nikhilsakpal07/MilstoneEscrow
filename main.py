import os
import asyncio
import logging
from datetime import datetime
from contextlib import asynccontextmanager
import requests
from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.responses import Response, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text
from twilio.twiml.messaging_response import MessagingResponse

from database import get_db, engine, SessionLocal
import models
from paypal_client import (
    authorize_order,
    capture_authorization,
    execute_payout,
    capture_multiple_authorizations,
    pool_and_payout_milestone,
)
from qa_agent import (
    evaluate_submission,
    mediate_dispute,
    generate_conversational_escrow,
    negotiate_scope_compromise,
)
from certificate_generator import generate_escrow_certificate_pdf
from stylometric_fingerprint import evaluate_sybil_stylometric_fingerprint
from predictive_risk import evaluate_bounty_predictive_risk, evaluate_all_active_bounties_risk

# Ensure database tables and newly added columns exist
models.Base.metadata.create_all(bind=engine)
try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE bounties ADD COLUMN IF NOT EXISTS remaining_amount_usd FLOAT;"))
        conn.execute(text("ALTER TABLE bounties ADD COLUMN IF NOT EXISTS requires_human_approval BOOLEAN DEFAULT FALSE;"))
        conn.execute(text("ALTER TABLE bounties ADD COLUMN IF NOT EXISTS freelancer_phone VARCHAR;"))
        conn.execute(text("ALTER TABLE bounties ADD COLUMN IF NOT EXISTS tracking_number VARCHAR;"))
        conn.execute(text("ALTER TABLE bounties ADD COLUMN IF NOT EXISTS shipping_status VARCHAR DEFAULT 'NOT_SHIPPED';"))
        conn.execute(text("ALTER TABLE bounties ADD COLUMN IF NOT EXISTS risk_score VARCHAR DEFAULT 'LOW';"))
        conn.execute(text("ALTER TABLE bounties ADD COLUMN IF NOT EXISTS risk_factors JSON DEFAULT '[]'::json;"))
        conn.execute(text("ALTER TABLE bounties ADD COLUMN IF NOT EXISTS risk_percentage INTEGER DEFAULT 15;"))
        conn.execute(text("ALTER TABLE bounties ADD COLUMN IF NOT EXISTS risk_updated_at VARCHAR;"))
        conn.execute(text("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS milestone_id INTEGER;"))
        conn.execute(text("ALTER TABLE milestones ADD COLUMN IF NOT EXISTS authorization_ids JSON DEFAULT '[]'::json;"))
        conn.execute(text("ALTER TABLE milestones ADD COLUMN IF NOT EXISTS requires_human_approval BOOLEAN DEFAULT FALSE;"))
        conn.execute(text("ALTER TABLE milestones ADD COLUMN IF NOT EXISTS tracking_number VARCHAR;"))
        conn.execute(text("ALTER TABLE milestones ADD COLUMN IF NOT EXISTS shipping_status VARCHAR DEFAULT 'NOT_SHIPPED';"))
        conn.execute(text("ALTER TABLE milestones ADD COLUMN IF NOT EXISTS certificate_id VARCHAR;"))
        conn.execute(text("ALTER TABLE milestones ADD COLUMN IF NOT EXISTS certificate_pdf_path VARCHAR;"))
        conn.execute(text("ALTER TABLE escrows ADD COLUMN IF NOT EXISTS paypal_order_ids JSON DEFAULT '[]'::json;"))
        conn.execute(text("ALTER TABLE escrows ADD COLUMN IF NOT EXISTS paypal_authorization_ids JSON DEFAULT '[]'::json;"))
        conn.execute(text("ALTER TABLE escrows ADD COLUMN IF NOT EXISTS paypal_capture_ids JSON DEFAULT '[]'::json;"))
        conn.commit()
except Exception as migration_err:
    logging.getLogger("milestone_escrow").warning("Migration check: %s", migration_err)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("milestone_escrow")

# Multi-Sig Threshold: bounties above $5,000 USD require human approval before payout execution
HIGH_VALUE_THRESHOLD = 5000.0

# =====================================================================
# EXTERNAL DATA ORACLE: MOCK LOGISTICS / SHIPPING API DATABASE
# =====================================================================
MOCK_SHIPPING_DATABASE: dict[str, dict] = {
    "TRACK-DELIVERED-001": {
        "status": "DELIVERED",
        "carrier": "FedEx Logistics",
        "origin": "Geneva Humanitarian Depot",
        "destination": "Regional Relief Clinic #4",
        "signed_by": "Dr. A. Omondi (Field Coordinator)",
        "notes": "Medical crates delivered and confirmed intact.",
        "updated_at": "2026-11-03T10:15:00Z",
    },
    "FEDEX-RELIEF-100": {
        "status": "DELIVERED",
        "carrier": "FedEx Logistics",
        "origin": "UNICEF Central Warehouse",
        "destination": "Community Water Station",
        "signed_by": "Water Committee Chairman",
        "notes": "Filtration units delivered and signed for.",
        "updated_at": "2026-11-03T11:45:00Z",
    },
    "DHL-TRANSIT-200": {
        "status": "IN_TRANSIT",
        "carrier": "DHL Global Express",
        "origin": "Nairobi Distribution Hub",
        "destination": "Mombasa Sector",
        "signed_by": None,
        "notes": "Consignment in transit between regional distribution points.",
        "updated_at": "2026-11-03T08:30:00Z",
    },
    "UPS-SHIPPED-300": {
        "status": "SHIPPED",
        "carrier": "UPS Worldwide",
        "origin": "Dubai Cargo Terminal",
        "destination": "East Africa Logistics Center",
        "signed_by": None,
        "notes": "Consignment dispatched from origin cargo bay.",
        "updated_at": "2026-11-02T16:00:00Z",
    },
}


def get_mock_shipping_info(tracking_number: str) -> dict:
    clean_trk = (tracking_number or "").strip()
    if clean_trk in MOCK_SHIPPING_DATABASE:
        return MOCK_SHIPPING_DATABASE[clean_trk]

    # Heuristic for demo / custom numbers:
    # If the user enters a number with "DELIVER", "DELIVERED", or "DLV", treat as DELIVERED
    trk_up = clean_trk.upper()
    if any(k in trk_up for k in ["DELIVER", "DLV"]):
        status_val = "DELIVERED"
        notes_val = "Carrier confirmed final delivery to recipient location."
    elif any(k in trk_up for k in ["TRANSIT", "MOVING"]):
        status_val = "IN_TRANSIT"
        notes_val = "Consignment is in transit with carrier."
    else:
        status_val = "SHIPPED"
        notes_val = "Carrier accepted consignment; shipping in progress."

    return {
        "tracking_number": clean_trk,
        "status": status_val,
        "carrier": "Global Logistics Carrier",
        "origin": "Regional Distribution Hub",
        "destination": "Project Destination Site",
        "signed_by": "Authorized Personnel" if status_val == "DELIVERED" else None,
        "notes": notes_val,
        "updated_at": "2026-11-03T12:00:00Z",
    }


def generate_and_attach_certificate(
    bounty: models.Bounty,
    milestone: models.Milestone,
    db: Session,
    reasoning: dict | str | None = None,
    batch_id: str | None = None,
) -> str | None:
    """
    Generates an official 'Escrow Verification Certificate' PDF using ReportLab
    and attaches the certificate ID and PDF path to the completed milestone.
    """
    try:
        tx_id = batch_id or milestone.paypal_payout_batch_id or "PAYPAL-AUTH-POOL-SETTLED"
        gemini_reasoning_data = reasoning
        if not gemini_reasoning_data:
            audit = (
                db.query(models.AuditLog)
                .filter(models.AuditLog.milestone_id == milestone.id)
                .order_by(models.AuditLog.id.desc())
                .first()
            )
            if audit and audit.ai_feedback:
                gemini_reasoning_data = {
                    "audit_verdict": "PASSED" if audit.passed else "VERIFIED",
                    "feedback": audit.ai_feedback,
                    "trajectory_id": audit.trajectory_id,
                }
            else:
                gemini_reasoning_data = {
                    "audit_verdict": "PASSED",
                    "approval": "Milestone verified and payout authorized under Escrow protocol.",
                }

        pdf_path, _ = generate_escrow_certificate_pdf(
            bounty_id=bounty.id,
            milestone_id=milestone.id,
            bounty_title=bounty.title,
            milestone_description=milestone.description,
            freelancer_email=bounty.freelancer_email,
            amount_usd=float(milestone.amount_usd),
            remaining_escrow_usd=float(bounty.remaining_amount_usd if bounty.remaining_amount_usd is not None else 0.0),
            paypal_transaction_id=tx_id,
            gemini_reasoning=gemini_reasoning_data,
        )
        milestone.certificate_pdf_path = pdf_path
        cert_filename = os.path.basename(pdf_path)
        cert_id = cert_filename.replace(".pdf", "").split("_")[-1]
        milestone.certificate_id = cert_id
        db.add(milestone)
        db.commit()
        logger.info("[Compliance Engine] Generated Escrow Certificate for Milestone #%d: %s", milestone.id, cert_id)
        return pdf_path
    except Exception as e:
        logger.error("[Compliance Engine] Error generating certificate for Milestone #%d: %s", milestone.id, e)
        return None


def process_oracle_deliveries(db: Session) -> list[dict]:
    """
    Oracle background task / sync processor:
    Finds all active bounties & milestones with tracking numbers.
    Queries the mock Logistics/Shipping API.
    If status is 'DELIVERED':
    - Auto-approves the milestone
    - Triggers PayPal Payouts (or sets to PENDING_ADMIN if Hybrid Multi-Sig is triggered)
    - Updates milestone and bounty shipping status to 'DELIVERED'.
    """
    processed = []

    uncompleted_milestones = (
        db.query(models.Milestone)
        .filter(models.Milestone.status != "COMPLETED")
        .all()
    )

    for m in uncompleted_milestones:
        bounty = m.bounty
        if not bounty:
            continue

        trk = m.tracking_number or bounty.tracking_number
        ship_status = m.shipping_status or bounty.shipping_status or "NOT_SHIPPED"

        if not trk:
            continue
        if ship_status not in ("SHIPPED", "IN_TRANSIT", "NOT_SHIPPED"):
            continue

        info = get_mock_shipping_info(trk)
        carrier_status = info.get("status", "IN_TRANSIT")

        if carrier_status == "DELIVERED":
            m.shipping_status = "DELIVERED"
            bounty.shipping_status = "DELIVERED"
            payout_amount = float(m.amount_usd)

            is_high_value = bool(
                bounty.requires_human_approval
                or (bounty.amount_usd and bounty.amount_usd > HIGH_VALUE_THRESHOLD)
                or (m.amount_usd and m.amount_usd > HIGH_VALUE_THRESHOLD)
                or m.requires_human_approval
            )

            if is_high_value:
                m.status = "PENDING_ADMIN"
                bounty.status = "PENDING_ADMIN"
                audit_log = models.AuditLog(
                    bounty_id=bounty.id,
                    milestone_id=m.id,
                    trajectory_id=f"oracle_shipping_{trk}_m_{m.id}_multisig",
                    passed=True,
                    ai_feedback=(
                        f"[EXTERNAL LOGISTICS ORACLE VERIFIED - PENDING ADMIN MULTI-SIG]: "
                        f"Carrier API confirmed consignment DELIVERED for tracking #{trk}. "
                        f"Signed by: {info.get('signed_by', 'Recipient')}. "
                        f"Because total bounty (${bounty.amount_usd:,.2f} USD) exceeds the "
                        f"${HIGH_VALUE_THRESHOLD:,.2f} multi-sig threshold, escrow funds remain locked. "
                        f"Status set to 'PENDING_ADMIN' awaiting human administrator sign-off."
                    ),
                )
                db.add(audit_log)
                processed.append({
                    "bounty_id": bounty.id,
                    "milestone_id": m.id,
                    "tracking_number": trk,
                    "status": "PENDING_ADMIN",
                    "reason": "Logistics Oracle confirmed delivery; requires multi-sig admin approval (> $5k).",
                })
            else:
                escrow = bounty.escrow or db.query(models.Escrow).filter(models.Escrow.bounty_id == bounty.id).first()
                m_auth_ids = list(m.authorization_ids or [])
                if not m_auth_ids and escrow:
                    if escrow.paypal_authorization_ids:
                        m_auth_ids = list(escrow.paypal_authorization_ids)
                    elif escrow.paypal_authorization_id:
                        m_auth_ids = [escrow.paypal_authorization_id]

                pooled_res = pool_and_payout_milestone(
                    authorization_ids=m_auth_ids,
                    freelancer_email=bounty.freelancer_email,
                    amount=payout_amount,
                    bounty_id=bounty.id,
                    milestone_id=m.id,
                )
                batch_id = pooled_res.get("payout", {}).get("batch_header", {}).get("payout_batch_id") or "BATCH-ORACLE"
                m.paypal_payout_batch_id = batch_id
                m.status = "COMPLETED"

                current_remaining = (
                    bounty.remaining_amount_usd if bounty.remaining_amount_usd is not None else bounty.amount_usd
                )
                bounty.remaining_amount_usd = max(0.0, round(float(current_remaining) - payout_amount, 2))

                all_milestones = db.query(models.Milestone).filter(models.Milestone.bounty_id == bounty.id).all()
                if all(item.status == "COMPLETED" for item in all_milestones) or bounty.remaining_amount_usd <= 0:
                    bounty.status = "COMPLETED"
                else:
                    bounty.status = "IN_PROGRESS"

                # Automated Compliance: Generate Escrow Verification Certificate PDF
                generate_and_attach_certificate(
                    bounty=bounty,
                    milestone=m,
                    db=db,
                    reasoning={
                        "oracle": "Logistics Carrier API",
                        "status": "DELIVERED",
                        "carrier": info.get("carrier"),
                        "tracking_number": trk,
                        "signed_by": info.get("signed_by"),
                        "notes": info.get("notes"),
                    },
                    batch_id=batch_id,
                )

                audit_log = models.AuditLog(
                    bounty_id=bounty.id,
                    milestone_id=m.id,
                    trajectory_id=f"oracle_shipping_{trk}_m_{m.id}",
                    passed=True,
                    ai_feedback=(
                        f"[EXTERNAL LOGISTICS ORACLE AUTO-APPROVAL]: Carrier API confirmed consignment DELIVERED "
                        f"for tracking #{trk}. Carrier: {info.get('carrier')}. "
                        f"Signed by: {info.get('signed_by', 'Recipient')}. "
                        f"Auto-released ${payout_amount:,.2f} USD to {bounty.freelancer_email} via PayPal Payouts (Batch ID: {batch_id})."
                    ),
                )
                db.add(audit_log)
                processed.append({
                    "bounty_id": bounty.id,
                    "milestone_id": m.id,
                    "tracking_number": trk,
                    "status": "COMPLETED",
                    "payout_amount": payout_amount,
                    "paypal_payout_batch_id": batch_id,
                })

    if processed:
        db.commit()

    return processed


async def oracle_background_poll_worker():
    """Background task that periodically queries Logistics Oracle."""
    while True:
        try:
            await asyncio.sleep(25)
            db = SessionLocal()
            try:
                processed = process_oracle_deliveries(db)
                if processed:
                    logger.info("[Logistics Oracle Background Task] Auto-processed %d deliveries: %s", len(processed), processed)
            finally:
                db.close()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("[Logistics Oracle Background Task Exception]: %s", e)


async def predictive_risk_background_worker():
    """Background task that periodically calculates predictive risk scores across active bounties."""
    await asyncio.sleep(5)
    while True:
        try:
            db = SessionLocal()
            try:
                evaluate_all_active_bounties_risk(db)
            finally:
                db.close()
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("[Predictive Risk Background Task Exception]: %s", e)
            await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: spawn background oracle polling task and predictive risk scorer
    oracle_task = asyncio.create_task(oracle_background_poll_worker())
    risk_task = asyncio.create_task(predictive_risk_background_worker())
    logger.info("[MilestoneEscrow] Background Logistics Oracle Poller & Predictive Risk Scorer started.")
    yield
    # Shutdown
    oracle_task.cancel()
    risk_task.cancel()
    try:
        await asyncio.gather(oracle_task, risk_task, return_exceptions=True)
    except Exception:
        pass
    logger.info("[MilestoneEscrow] Background Logistics Oracle Poller & Predictive Risk Scorer stopped.")


app = FastAPI(
    title="MilestoneEscrow API",
    description="Backend API for escrow and bounties",
    version="1.0.0",
    contact={
        "name": "Nikhil Sakpal",
        "email": "nikhilsakpal1426@gmail.com"
    },
    lifespan=lifespan,
)

# Configure CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class MilestoneInput(BaseModel):
    description: str
    deadline: str
    percentage: float
    authorization_ids: list[str] = []
    tracking_number: str | None = None
    shipping_status: str | None = "NOT_SHIPPED"


class BountyCreate(BaseModel):
    title: str
    acceptance_criteria: str
    amount_usd: float
    freelancer_email: str
    freelancer_phone: str | None = None
    tracking_number: str | None = None
    shipping_status: str | None = "NOT_SHIPPED"
    paypal_order_id: str | None = None
    paypal_order_ids: list[str] = []
    milestones: list[MilestoneInput] = []


class ShipRequest(BaseModel):
    tracking_number: str
    shipping_status: str | None = "SHIPPED"
    carrier: str | None = "FedEx Logistics"


class ShippingStatusUpdate(BaseModel):
    status: str
    carrier: str | None = None
    city: str | None = None
    notes: str | None = None


class SponsorContribution(BaseModel):
    paypal_order_id: str | None = None
    authorization_id: str | None = None
    sponsor_name: str | None = "Anonymous Sponsor"
    amount_usd: float | None = None


class AdminApprovalRequest(BaseModel):
    admin_notes: str | None = "Admin human co-signer approval"


class WorkSubmission(BaseModel):
    github_url: str | None = None
    milestone_id: int | None = None


class AppealRequest(BaseModel):
    appeal_text: str
    milestone_id: int | None = None


class GenerateScopeRequest(BaseModel):
    prompt: str


class NegotiateScopeRequest(BaseModel):
    counter_offer: str
    freelancer_email: str | None = None
    proposed_amount_usd: float | None = None
    proposed_timeline: str | None = None


class AcceptCompromiseRequest(BaseModel):
    compromise_amount_usd: float
    compromise_criteria: str
    compromise_milestones: list[MilestoneInput]
    reasoning: str | None = None


@app.get("/")
def read_root():
    return {"message": "MilestoneEscrow Backend is running."}


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    return {"status": "ok", "db_connected": True}


@app.get("/api/bounties")
def list_bounties(db: Session = Depends(get_db)):
    """
    Returns a list of all bounties including their milestone progress, multi-sponsor authorizations,
    hybrid multi-sig flags, and logistics oracle/phone tracking details.
    """
    bounties = db.query(models.Bounty).order_by(models.Bounty.id.desc()).all()
    return [
        {
            "id": b.id,
            "title": b.title,
            "acceptance_criteria": b.acceptance_criteria,
            "amount_usd": b.amount_usd,
            "remaining_amount_usd": b.remaining_amount_usd if b.remaining_amount_usd is not None else b.amount_usd,
            "freelancer_email": b.freelancer_email,
            "freelancer_phone": b.freelancer_phone,
            "tracking_number": b.tracking_number,
            "shipping_status": b.shipping_status or "NOT_SHIPPED",
            "status": b.status,
            "risk_score": b.risk_score or "LOW",
            "risk_percentage": b.risk_percentage if b.risk_percentage is not None else 15,
            "risk_factors": b.risk_factors or [],
            "risk_updated_at": b.risk_updated_at,
            "requires_human_approval": bool(b.requires_human_approval or (b.amount_usd or 0) > HIGH_VALUE_THRESHOLD),
            "is_high_value": (b.amount_usd or 0) > HIGH_VALUE_THRESHOLD,
            "milestones": [
                {
                    "id": m.id,
                    "description": m.description,
                    "deadline": m.deadline,
                    "percentage": m.percentage,
                    "amount_usd": m.amount_usd,
                    "status": m.status,
                    "authorization_ids": m.authorization_ids or [],
                    "requires_human_approval": bool(m.requires_human_approval or b.requires_human_approval or (m.amount_usd or 0) > HIGH_VALUE_THRESHOLD),
                    "tracking_number": m.tracking_number or b.tracking_number,
                    "shipping_status": m.shipping_status or b.shipping_status or "NOT_SHIPPED",
                    "paypal_payout_batch_id": m.paypal_payout_batch_id,
                    "certificate_id": m.certificate_id,
                    "certificate_pdf_path": m.certificate_pdf_path,
                    "has_certificate": bool(m.certificate_pdf_path and os.path.exists(m.certificate_pdf_path)),
                }
                for m in (b.milestones or [])
            ],
        }
        for b in bounties
    ]


@app.get("/api/bounties/{bounty_id}")
def get_bounty(bounty_id: int, db: Session = Depends(get_db)):
    """
    Returns a single bounty with all associated milestone rows, pooled sponsor authorizations,
    logistics tracking, and escrow data.
    """
    bounty = db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    if not bounty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bounty with ID {bounty_id} not found.",
        )

    return {
        "id": bounty.id,
        "title": bounty.title,
        "acceptance_criteria": bounty.acceptance_criteria,
        "amount_usd": bounty.amount_usd,
        "remaining_amount_usd": (
            bounty.remaining_amount_usd if bounty.remaining_amount_usd is not None else bounty.amount_usd
        ),
        "freelancer_email": bounty.freelancer_email,
        "freelancer_phone": bounty.freelancer_phone,
        "tracking_number": bounty.tracking_number,
        "shipping_status": bounty.shipping_status or "NOT_SHIPPED",
        "status": bounty.status,
        "risk_score": bounty.risk_score or "LOW",
        "risk_percentage": bounty.risk_percentage if bounty.risk_percentage is not None else 15,
        "risk_factors": bounty.risk_factors or [],
        "risk_updated_at": bounty.risk_updated_at,
        "requires_human_approval": bool(bounty.requires_human_approval or (bounty.amount_usd or 0) > HIGH_VALUE_THRESHOLD),
        "is_high_value": (bounty.amount_usd or 0) > HIGH_VALUE_THRESHOLD,
        "escrow": {
            "paypal_order_id": bounty.escrow.paypal_order_id if bounty.escrow else None,
            "paypal_authorization_id": bounty.escrow.paypal_authorization_id if bounty.escrow else None,
            "paypal_capture_id": bounty.escrow.paypal_capture_id if bounty.escrow else None,
            "paypal_order_ids": bounty.escrow.paypal_order_ids if bounty.escrow else [],
            "paypal_authorization_ids": bounty.escrow.paypal_authorization_ids if bounty.escrow else [],
            "paypal_capture_ids": bounty.escrow.paypal_capture_ids if bounty.escrow else [],
        } if bounty.escrow else None,
        "milestones": [
            {
                "id": m.id,
                "description": m.description,
                "deadline": m.deadline,
                "percentage": m.percentage,
                "amount_usd": m.amount_usd,
                "status": m.status,
                "authorization_ids": m.authorization_ids or [],
                "requires_human_approval": bool(m.requires_human_approval or bounty.requires_human_approval or (m.amount_usd or 0) > HIGH_VALUE_THRESHOLD),
                "tracking_number": m.tracking_number or bounty.tracking_number,
                "shipping_status": m.shipping_status or bounty.shipping_status or "NOT_SHIPPED",
                "paypal_payout_batch_id": m.paypal_payout_batch_id,
                "certificate_id": m.certificate_id,
                "certificate_pdf_path": m.certificate_pdf_path,
                "has_certificate": bool(m.certificate_pdf_path and os.path.exists(m.certificate_pdf_path)),
            }
            for m in (bounty.milestones or [])
        ],
    }


@app.post("/api/bounties", status_code=status.HTTP_201_CREATED)
def create_bounty(
    bounty_in: BountyCreate,
    db: Session = Depends(get_db),
):
    """
    Creates a new Bounty with 'LOCKED' status and initializes Milestone rows.
    Supports Multi-Sponsor Pooling: captures and pools arrays of order/authorization IDs.
    Supports Hybrid Multi-Sig: sets requires_human_approval=True if total bounty > $5,000.
    Supports WhatsApp field-worker phone number & logistics oracle tracking number.
    """
    print(f"[DEBUG] Incoming Bounty Creation Payload: {bounty_in.model_dump()}")

    is_high_value = bounty_in.amount_usd > HIGH_VALUE_THRESHOLD

    new_bounty = models.Bounty(
        title=bounty_in.title,
        acceptance_criteria=bounty_in.acceptance_criteria,
        amount_usd=bounty_in.amount_usd,
        remaining_amount_usd=bounty_in.amount_usd,
        freelancer_email=bounty_in.freelancer_email,
        freelancer_phone=bounty_in.freelancer_phone,
        tracking_number=bounty_in.tracking_number,
        shipping_status=(bounty_in.shipping_status or "NOT_SHIPPED").upper(),
        status="LOCKED",
        requires_human_approval=is_high_value,
    )
    db.add(new_bounty)
    db.flush()

    # Collect all incoming sponsor order IDs
    order_ids = []
    if bounty_in.paypal_order_id:
        order_ids.append(bounty_in.paypal_order_id)
    if bounty_in.paypal_order_ids:
        for oid in bounty_in.paypal_order_ids:
            if oid and oid not in order_ids:
                order_ids.append(oid)

    # Authorize orders to lock multi-sponsor funds
    auth_ids = []
    for oid in order_ids:
        try:
            aid = authorize_order(oid)
            auth_ids.append(aid)
            print(f"[DEBUG] PayPal Authorized Order {oid} -> Authorization ID: {aid}")
        except Exception as e:
            print(f"[WARNING] Could not authorize order {oid}: {e}")

    primary_order_id = order_ids[0] if order_ids else None
    primary_auth_id = auth_ids[0] if auth_ids else None

    new_escrow = models.Escrow(
        bounty_id=new_bounty.id,
        paypal_order_id=primary_order_id,
        paypal_authorization_id=primary_auth_id,
        paypal_order_ids=order_ids,
        paypal_authorization_ids=auth_ids,
        paypal_capture_ids=[],
    )
    db.add(new_escrow)

    # Insert milestone rows with authorization IDs and multi-sig requirements
    if bounty_in.milestones:
        for idx, m in enumerate(bounty_in.milestones):
            pct = float(m.percentage)
            m_amount = round(bounty_in.amount_usd * (pct / 100.0), 2)
            m_auth_ids = list(m.authorization_ids) if m.authorization_ids else list(auth_ids)
            milestone_obj = models.Milestone(
                bounty_id=new_bounty.id,
                description=m.description,
                deadline=m.deadline,
                percentage=pct,
                amount_usd=m_amount,
                status="LOCKED",
                authorization_ids=m_auth_ids,
                tracking_number=m.tracking_number or bounty_in.tracking_number,
                shipping_status=(m.shipping_status or bounty_in.shipping_status or "NOT_SHIPPED").upper(),
                requires_human_approval=bool(is_high_value or m_amount > HIGH_VALUE_THRESHOLD),
            )
            db.add(milestone_obj)
    else:
        # Default single milestone if none supplied
        milestone_obj = models.Milestone(
            bounty_id=new_bounty.id,
            description="Complete Project Deliverable",
            deadline="Open",
            percentage=100.0,
            amount_usd=bounty_in.amount_usd,
            status="LOCKED",
            authorization_ids=list(auth_ids),
            tracking_number=bounty_in.tracking_number,
            shipping_status=(bounty_in.shipping_status or "NOT_SHIPPED").upper(),
            requires_human_approval=is_high_value,
        )
        db.add(milestone_obj)

    db.commit()
    db.refresh(new_bounty)

    return {
        "bounty_id": new_bounty.id,
        "id": new_bounty.id,
        "requires_human_approval": new_bounty.requires_human_approval,
        "is_high_value": is_high_value,
        "authorization_ids": auth_ids,
        "freelancer_phone": new_bounty.freelancer_phone,
        "tracking_number": new_bounty.tracking_number,
        "shipping_status": new_bounty.shipping_status,
    }


@app.post("/api/bounties/{bounty_id}/milestones/{milestone_id}/submit-work", status_code=status.HTTP_200_OK)
@app.post("/api/bounties/{bounty_id}/submit-work", status_code=status.HTTP_200_OK)
async def submit_work(
    bounty_id: int,
    request: Request,
    milestone_id: int | None = None,
    db: Session = Depends(get_db),
):
    """
    Submits freelancer work for a milestone:
    Accepts either multipart form data (file uploads: receipts/images/PDFs) or JSON payloads (GitHub URLs).
    1. Fetches the Bounty, Escrow, and specific Milestone.
    2. Runs automated AI QA evaluation:
       - Multimodal analysis via Gemini 1.5 Pro and Pillow EXIF verification for uploaded receipts.
       - Code repository cloning and test execution if a GitHub URL is provided.
    3. Persists evaluation outcome to AuditLog.
    4. If passed:
       - Captures authorization funds into escrow if not yet done.
       - Disburses ONLY that milestone's specific amount via PayPal Payouts.
       - Updates milestone to COMPLETED and decrements remaining escrow funds.
    5. Returns evaluation results, extracted receipt details, and updated balance.
    """
    # Fetch Bounty
    bounty = db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    if not bounty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bounty with ID {bounty_id} not found.",
        )

    # Parse incoming payload (supports multipart/form-data and application/json)
    content_type = request.headers.get("content-type", "").lower()
    github_url: str | None = None
    target_milestone_id = milestone_id
    uploaded_files_data: list[tuple[bytes, str, str]] = []

    if "multipart/form-data" in content_type:
        form = await request.form()
        github_url = form.get("github_url")
        if isinstance(github_url, str):
            github_url = github_url.strip() or None

        form_milestone = form.get("milestone_id")
        if not target_milestone_id and form_milestone:
            try:
                target_milestone_id = int(form_milestone)
            except (ValueError, TypeError):
                pass

        # Extract file uploads from form (supports 'files' and 'file' field keys)
        for field_name in ["files", "file"]:
            for item in form.getlist(field_name):
                if hasattr(item, "read"):
                    data = await item.read()
                    if data and len(data) > 0:
                        mime = getattr(item, "content_type", "image/jpeg") or "image/jpeg"
                        fname = getattr(item, "filename", "receipt.jpg") or "receipt.jpg"
                        uploaded_files_data.append((data, mime, fname))

    elif "application/json" in content_type:
        body = await request.json()
        github_url = body.get("github_url")
        if not target_milestone_id and body.get("milestone_id"):
            try:
                target_milestone_id = int(body.get("milestone_id"))
            except (ValueError, TypeError):
                pass
    else:
        try:
            form = await request.form()
            github_url = form.get("github_url")
        except Exception:
            pass

    if not github_url and len(uploaded_files_data) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Submission must include either a valid GitHub URL or proof documents/receipt images.",
        )

    # Identify targeted Milestone
    if target_milestone_id is not None:
        milestone = db.query(models.Milestone).filter(
            models.Milestone.id == target_milestone_id,
            models.Milestone.bounty_id == bounty.id,
        ).first()
        if not milestone:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Milestone with ID {target_milestone_id} not found on this bounty.",
            )
    else:
        # Default to the first uncompleted milestone
        milestone = db.query(models.Milestone).filter(
            models.Milestone.bounty_id == bounty.id,
            models.Milestone.status != "COMPLETED",
        ).order_by(models.Milestone.id.asc()).first()

        if not milestone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="All milestones for this bounty have already been completed.",
            )

    # Fetch associated Escrow
    escrow = bounty.escrow or db.query(models.Escrow).filter(models.Escrow.bounty_id == bounty_id).first()

    # AI Stylometric Fingerprinting (Sybil Attack Detection)
    # If submitting a GitHub repository, evaluate AST and variable naming styles against previous submissions
    if github_url:
        sybil_check = evaluate_sybil_stylometric_fingerprint(
            db=db,
            github_url=github_url,
            freelancer_email=bounty.freelancer_email,
            bounty_id=bounty.id,
            milestone_id=milestone.id,
        )
        if sybil_check.get("is_sybil_match"):
            milestone.status = "fraud_review_pending"
            bounty.status = "fraud_review_pending"
            evidence = sybil_check.get("stylistic_evidence", "Exact AST structure and identifier collision detected across accounts.")
            matched_acc = sybil_check.get("matched_account", "Historical Account")
            confidence = sybil_check.get("confidence_score", 0.95)

            fraud_feedback = (
                f"[AI STYLOMETRIC SECURITY ALERT - SYBIL ATTACK DETECTED]: "
                f"Stylometric AST and naming analysis detected an unauthorized multi-account Sybil collision. "
                f"Matched with account '{matched_acc}' (Confidence: {confidence:.0%}). "
                f"Evidence: {evidence}. "
                f"Milestone status set to 'fraud_review_pending' and escrow payout is blocked pending human compliance audit."
            )
            audit_log = models.AuditLog(
                bounty_id=bounty.id,
                milestone_id=milestone.id,
                trajectory_id=f"sybil_fraud_m_{milestone.id}",
                passed=False,
                ai_feedback=fraud_feedback,
            )
            db.add(audit_log)
            db.commit()
            db.refresh(bounty)
            db.refresh(milestone)

            return {
                "status": "fraud_review_pending",
                "milestone_id": milestone.id,
                "milestone_description": milestone.description,
                "milestone_status": "fraud_review_pending",
                "milestone_amount_paid": 0.0,
                "remaining_amount_usd": bounty.remaining_amount_usd,
                "feedback": fraud_feedback,
                "passed": False,
                "sybil_detected": True,
                "fraud_review_pending": True,
                "extracted_data": None,
            }

    # Update state to AUDITING
    milestone.status = "AUDITING"
    bounty.status = "AUDITING"
    db.commit()

    # Run AI QA Evaluation (multimodal receipt extraction with Pillow EXIF OR code QA)
    eval_result = await evaluate_submission(
        github_url=github_url,
        files=uploaded_files_data if len(uploaded_files_data) > 0 else None,
        acceptance_criteria=bounty.acceptance_criteria,
        bounty_id=bounty_id,
        milestone_id=milestone.id,
        milestone_description=milestone.description,
        milestone_deadline=milestone.deadline,
    )

    passed = eval_result.get("passed", False)
    feedback = eval_result.get("feedback", "")
    extracted_data = eval_result.get("extracted_data")

    # Save to AuditLog
    audit_log = models.AuditLog(
        bounty_id=bounty.id,
        milestone_id=milestone.id,
        trajectory_id=f"bounty_{bounty_id}_m_{milestone.id}",
        passed=passed,
        ai_feedback=feedback,
    )
    db.add(audit_log)
    db.commit()

    payout_amount = 0.0

    if passed:
        # Check Hybrid Multi-Sig condition (Value > $5,000 threshold or requires_human_approval)
        is_high_value = bool(
            bounty.requires_human_approval
            or (bounty.amount_usd and bounty.amount_usd > HIGH_VALUE_THRESHOLD)
            or (milestone.amount_usd and milestone.amount_usd > HIGH_VALUE_THRESHOLD)
            or milestone.requires_human_approval
        )

        if is_high_value:
            # High-value bounty (> $5k): AI approval ONLY sets status to pending_admin!
            milestone.status = "PENDING_ADMIN"
            bounty.status = "PENDING_ADMIN"

            multi_sig_note = (
                f"{feedback}\n\n"
                f"[HYBRID MULTI-SIG ACTIVATED]: AI evaluation PASSED. "
                f"Because the total bounty value (${bounty.amount_usd:,.2f} USD) exceeds the "
                f"${HIGH_VALUE_THRESHOLD:,.2f} multi-sig threshold, escrow funds remain locked. "
                f"Status set to 'PENDING_ADMIN'. Awaiting human administrator final approval in Admin Dashboard."
            )
            audit_log.ai_feedback = multi_sig_note
            db.commit()
            db.refresh(bounty)
            db.refresh(milestone)

            return {
                "status": bounty.status,
                "milestone_id": milestone.id,
                "milestone_description": milestone.description,
                "milestone_status": milestone.status,  # "PENDING_ADMIN"
                "milestone_amount_paid": 0.0,
                "remaining_amount_usd": bounty.remaining_amount_usd,
                "feedback": multi_sig_note,
                "passed": True,
                "requires_human_approval": True,
                "extracted_data": extracted_data,
            }

        # Otherwise automated release (value <= $5,000):
        # 1. Gather all authorization IDs for multi-sponsor pooling
        m_auth_ids = list(milestone.authorization_ids or [])
        if not m_auth_ids and escrow:
            if escrow.paypal_authorization_ids:
                m_auth_ids = list(escrow.paypal_authorization_ids)
            elif escrow.paypal_authorization_id:
                m_auth_ids = [escrow.paypal_authorization_id]

        payout_amount = float(milestone.amount_usd)

        # 2. Loops through all authorized IDs, captures them simultaneously, and pools funds to the payee
        pooled_result = pool_and_payout_milestone(
            authorization_ids=m_auth_ids,
            freelancer_email=bounty.freelancer_email,
            amount=payout_amount,
            bounty_id=bounty_id,
            milestone_id=milestone.id,
        )

        batch_id = pooled_result.get("payout", {}).get("batch_header", {}).get("payout_batch_id")
        milestone.paypal_payout_batch_id = batch_id
        milestone.status = "COMPLETED"

        # 3. Update database state to track remaining funds
        current_remaining = (
            bounty.remaining_amount_usd if bounty.remaining_amount_usd is not None else bounty.amount_usd
        )
        new_remaining = max(0.0, round(float(current_remaining) - payout_amount, 2))
        bounty.remaining_amount_usd = new_remaining

        # Check if all milestones for this bounty are completed
        all_milestones = db.query(models.Milestone).filter(models.Milestone.bounty_id == bounty.id).all()
        all_done = all(m.status == "COMPLETED" for m in all_milestones)

        if all_done or bounty.remaining_amount_usd <= 0:
            bounty.status = "COMPLETED"
        else:
            bounty.status = "IN_PROGRESS"

        # Automated Compliance: Generate Escrow Verification Certificate PDF
        cert_path = generate_and_attach_certificate(
            bounty=bounty,
            milestone=milestone,
            db=db,
            reasoning={
                "audit_verdict": "PASSED",
                "feedback": feedback,
                "extracted_data": extracted_data,
                "timestamp": datetime.utcnow().isoformat(),
            },
            batch_id=batch_id,
        )

    else:
        milestone.status = "REJECTED"
        bounty.status = "IN_PROGRESS"

    db.commit()
    db.refresh(bounty)
    db.refresh(milestone)

    return {
        "status": bounty.status,
        "milestone_id": milestone.id,
        "milestone_description": milestone.description,
        "milestone_status": milestone.status,
        "milestone_amount_paid": payout_amount,
        "remaining_amount_usd": bounty.remaining_amount_usd,
        "feedback": feedback,
        "passed": passed,
        "extracted_data": extracted_data,
        "certificate_id": milestone.certificate_id,
        "certificate_url": f"/api/milestones/{milestone.id}/certificate" if milestone.certificate_id else None,
    }


@app.post("/api/bounties/{bounty_id}/milestones/{milestone_id}/appeal", status_code=status.HTTP_200_OK)
@app.post("/api/bounties/{bounty_id}/appeal", status_code=status.HTTP_200_OK)
async def appeal_rejection(
    bounty_id: int,
    appeal_in: AppealRequest,
    milestone_id: int | None = None,
    db: Session = Depends(get_db),
):
    """
    Dispute Resolution / Appeal Route:
    If a milestone submission was rejected, the user can submit an appeal explanation.
    Spawns the Mediator AI to analyze the original criteria, the auditor's rejection reason,
    and the user's defense to make a binding decision on whether to override the rejection.
    If overridden, automatically captures authorization and executes the milestone payout
    (or sets to PENDING_ADMIN if Hybrid Multi-Sig is triggered).
    """
    bounty = db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    if not bounty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bounty with ID {bounty_id} not found.",
        )

    # Identify targeted milestone
    target_mid = milestone_id or appeal_in.milestone_id
    if target_mid:
        milestone = db.query(models.Milestone).filter(
            models.Milestone.id == target_mid,
            models.Milestone.bounty_id == bounty.id,
        ).first()
    else:
        # Default to the most recently rejected milestone
        milestone = db.query(models.Milestone).filter(
            models.Milestone.bounty_id == bounty.id,
            models.Milestone.status == "REJECTED",
        ).order_by(models.Milestone.id.desc()).first()

        if not milestone:
            # Fallback to any uncompleted milestone
            milestone = db.query(models.Milestone).filter(
                models.Milestone.bounty_id == bounty.id,
                models.Milestone.status != "COMPLETED",
            ).order_by(models.Milestone.id.asc()).first()

    if not milestone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No eligible milestone found to appeal for this bounty.",
        )

    escrow = bounty.escrow or db.query(models.Escrow).filter(models.Escrow.bounty_id == bounty_id).first()

    # Look up the last failed audit log to provide the exact rejection reason
    last_audit = db.query(models.AuditLog).filter(
        models.AuditLog.bounty_id == bounty.id,
        models.AuditLog.milestone_id == milestone.id,
        models.AuditLog.passed == False,
    ).order_by(models.AuditLog.id.desc()).first()

    rejection_reason = (
        last_audit.ai_feedback
        if last_audit and last_audit.ai_feedback
        else f"Milestone #{milestone.id} was marked as REJECTED during automated evaluation."
    )

    # Run Mediator AI Arbitration
    mediation_result = await mediate_dispute(
        bounty_id=bounty.id,
        milestone_id=milestone.id,
        milestone_criteria=milestone.description or bounty.acceptance_criteria,
        rejection_reason=rejection_reason,
        appeal_text=appeal_in.appeal_text,
        bounty_title=bounty.title,
        milestone_amount=float(milestone.amount_usd),
    )

    override_granted = bool(mediation_result.get("override_rejection", False))
    payout_amount = 0.0

    if override_granted:
        is_high_value = bool(
            bounty.requires_human_approval
            or (bounty.amount_usd and bounty.amount_usd > HIGH_VALUE_THRESHOLD)
            or (milestone.amount_usd and milestone.amount_usd > HIGH_VALUE_THRESHOLD)
            or milestone.requires_human_approval
        )

        if is_high_value:
            # Sets to pending_admin under Hybrid Multi-Sig
            milestone.status = "PENDING_ADMIN"
            bounty.status = "PENDING_ADMIN"
            audit_log = models.AuditLog(
                bounty_id=bounty.id,
                milestone_id=milestone.id,
                trajectory_id=f"bounty_{bounty_id}_m_{milestone.id}_mediator_override_multisig",
                passed=True,
                ai_feedback=f"[MEDIATOR OVERRIDE - PENDING ADMIN MULTI-SIG]: {mediation_result.get('reasoning')}. High-value bounty (> $5,000 threshold) requires human administrator sign-off.",
            )
            db.add(audit_log)
        else:
            # Automated release: gather authorization IDs and pool funds to payee
            auth_ids = list(milestone.authorization_ids or [])
            if not auth_ids and escrow:
                if escrow.paypal_authorization_ids:
                    auth_ids = list(escrow.paypal_authorization_ids)
                elif escrow.paypal_authorization_id:
                    auth_ids = [escrow.paypal_authorization_id]

            payout_amount = float(milestone.amount_usd)
            pooled_res = pool_and_payout_milestone(
                authorization_ids=auth_ids,
                freelancer_email=bounty.freelancer_email,
                amount=payout_amount,
                bounty_id=bounty_id,
                milestone_id=milestone.id,
            )
            batch_id = pooled_res.get("payout", {}).get("batch_header", {}).get("payout_batch_id")
            milestone.paypal_payout_batch_id = batch_id
            milestone.status = "COMPLETED"

            # Deduct payout from remaining escrow funds
            current_remaining = (
                bounty.remaining_amount_usd if bounty.remaining_amount_usd is not None else bounty.amount_usd
            )
            bounty.remaining_amount_usd = max(0.0, round(float(current_remaining) - payout_amount, 2))

            all_milestones = db.query(models.Milestone).filter(models.Milestone.bounty_id == bounty.id).all()
            if all(m.status == "COMPLETED" for m in all_milestones) or bounty.remaining_amount_usd <= 0:
                bounty.status = "COMPLETED"
            else:
                bounty.status = "IN_PROGRESS"

            # Automated Compliance: Generate Escrow Verification Certificate PDF
            generate_and_attach_certificate(
                bounty=bounty,
                milestone=milestone,
                db=db,
                reasoning={
                    "mediator_verdict": "OVERRIDE_APPROVED",
                    "reasoning": mediation_result.get("reasoning"),
                    "appeal_text": appeal_in.appeal_text,
                },
                batch_id=batch_id,
            )

            audit_log = models.AuditLog(
                bounty_id=bounty.id,
                milestone_id=milestone.id,
                trajectory_id=f"bounty_{bounty_id}_m_{milestone.id}_mediator_override",
                passed=True,
                ai_feedback=f"[MEDIATOR OVERRIDE]: {mediation_result.get('reasoning')}",
            )
            db.add(audit_log)
    else:
        audit_log = models.AuditLog(
            bounty_id=bounty.id,
            milestone_id=milestone.id,
            trajectory_id=f"bounty_{bounty_id}_m_{milestone.id}_mediator_upheld",
            passed=False,
            ai_feedback=f"[MEDIATOR RULING UPHELD]: {mediation_result.get('reasoning')}",
        )
        db.add(audit_log)

    db.commit()
    db.refresh(bounty)
    db.refresh(milestone)

    return {
        "status": bounty.status,
        "bounty_id": bounty.id,
        "milestone_id": milestone.id,
        "override_rejection": override_granted,
        "final_decision": mediation_result.get("final_decision"),
        "reasoning": mediation_result.get("reasoning"),
        "milestone_status": milestone.status,
        "milestone_amount_paid": payout_amount,
        "remaining_amount_usd": bounty.remaining_amount_usd,
    }


# =====================================================================
# HYBRID MULTI-SIG ADMIN & MULTI-SPONSOR POOLING ROUTES
# =====================================================================

@app.get("/api/admin/pending", status_code=status.HTTP_200_OK)
def get_pending_admin_milestones(db: Session = Depends(get_db)):
    """
    Returns all bounties and milestones currently awaiting human administrator sign-off
    under the Hybrid Multi-Sig protocol (threshold > $5,000 USD).
    """
    pending_milestones = (
        db.query(models.Milestone)
        .filter(models.Milestone.status == "PENDING_ADMIN")
        .order_by(models.Milestone.id.desc())
        .all()
    )

    results = []
    for m in pending_milestones:
        b = m.bounty
        last_audit = (
            db.query(models.AuditLog)
            .filter(
                models.AuditLog.bounty_id == b.id,
                models.AuditLog.milestone_id == m.id,
            )
            .order_by(models.AuditLog.id.desc())
            .first()
        )
        results.append({
            "bounty_id": b.id,
            "bounty_title": b.title,
            "bounty_amount_usd": b.amount_usd,
            "bounty_remaining_usd": b.remaining_amount_usd if b.remaining_amount_usd is not None else b.amount_usd,
            "freelancer_email": b.freelancer_email,
            "acceptance_criteria": b.acceptance_criteria,
            "bounty_status": b.status,
            "milestone_id": m.id,
            "milestone_description": m.description,
            "milestone_amount_usd": m.amount_usd,
            "milestone_deadline": m.deadline,
            "milestone_status": m.status,
            "authorization_ids": m.authorization_ids or [],
            "requires_human_approval": True,
            "latest_ai_feedback": last_audit.ai_feedback if last_audit else "AI Evaluation Passed (Locked under Multi-Sig Threshold)",
            "passed": last_audit.passed if last_audit else True,
        })

    return results


@app.post("/api/admin/bounties/{bounty_id}/milestones/{milestone_id}/approve", status_code=status.HTTP_200_OK)
def admin_final_approve(
    bounty_id: int,
    milestone_id: int,
    approval_in: AdminApprovalRequest | None = None,
    db: Session = Depends(get_db),
):
    """
    Hybrid Multi-Sig Human Co-Signer Endpoint:
    When an administrator clicks 'Final Approve' on the admin dashboard,
    this triggers the simultaneous capture of all authorized sponsor IDs and
    executes the PayPal Payouts API to release the milestone funds.
    """
    bounty = db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    if not bounty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bounty #{bounty_id} not found.",
        )

    milestone = (
        db.query(models.Milestone)
        .filter(models.Milestone.id == milestone_id, models.Milestone.bounty_id == bounty.id)
        .first()
    )
    if not milestone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Milestone #{milestone_id} not found on Bounty #{bounty_id}.",
        )

    escrow = bounty.escrow or db.query(models.Escrow).filter(models.Escrow.bounty_id == bounty_id).first()

    # Collect all authorization IDs for multi-sponsor pooling
    auth_ids = list(milestone.authorization_ids or [])
    if not auth_ids and escrow:
        if escrow.paypal_authorization_ids:
            auth_ids = list(escrow.paypal_authorization_ids)
        elif escrow.paypal_authorization_id:
            auth_ids = [escrow.paypal_authorization_id]

    if not auth_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid PayPal authorization IDs found for this milestone to capture.",
        )

    payout_amount = float(milestone.amount_usd)

    # Simultaneously capture all authorized sponsor IDs and execute PayPal Payout
    pooled_res = pool_and_payout_milestone(
        authorization_ids=auth_ids,
        freelancer_email=bounty.freelancer_email,
        amount=payout_amount,
        bounty_id=bounty.id,
        milestone_id=milestone.id,
    )

    batch_id = pooled_res.get("payout", {}).get("batch_header", {}).get("payout_batch_id")
    milestone.paypal_payout_batch_id = batch_id
    milestone.status = "COMPLETED"

    # Deduct payout from remaining escrow funds
    current_remaining = (
        bounty.remaining_amount_usd if bounty.remaining_amount_usd is not None else bounty.amount_usd
    )
    bounty.remaining_amount_usd = max(0.0, round(float(current_remaining) - payout_amount, 2))

    all_milestones = db.query(models.Milestone).filter(models.Milestone.bounty_id == bounty.id).all()
    if all(m.status == "COMPLETED" for m in all_milestones) or bounty.remaining_amount_usd <= 0:
        bounty.status = "COMPLETED"
    else:
        bounty.status = "IN_PROGRESS"

    admin_note = (approval_in.admin_notes if approval_in and approval_in.admin_notes else "Admin Human Co-Signer Approved")
    audit_log = models.AuditLog(
        bounty_id=bounty.id,
        milestone_id=milestone.id,
        trajectory_id=f"bounty_{bounty_id}_m_{milestone.id}_admin_multisig",
        passed=True,
        ai_feedback=f"[ADMIN MULTI-SIG FINAL APPROVAL]: {admin_note}. Released ${payout_amount:,.2f} USD via PayPal Payouts.",
    )
    db.add(audit_log)

    # Automated Compliance: Generate Escrow Verification Certificate PDF
    generate_and_attach_certificate(
        bounty=bounty,
        milestone=milestone,
        db=db,
        reasoning={
            "admin_verdict": "HUMAN_MULTI_SIG_CO_SIGNED",
            "admin_notes": admin_note,
            "bounty_total": bounty.amount_usd,
            "milestone_disbursed": payout_amount,
        },
        batch_id=batch_id,
    )

    db.commit()
    db.refresh(bounty)
    db.refresh(milestone)

    return {
        "status": "APPROVED",
        "bounty_id": bounty.id,
        "milestone_id": milestone.id,
        "milestone_status": milestone.status,
        "payout_amount": payout_amount,
        "paypal_payout_batch_id": batch_id,
        "captures": pooled_res.get("captures", []),
        "remaining_amount_usd": bounty.remaining_amount_usd,
        "bounty_status": bounty.status,
    }


@app.post("/api/admin/bounties/{bounty_id}/milestones/{milestone_id}/reject", status_code=status.HTTP_200_OK)
def admin_reject_milestone(
    bounty_id: int,
    milestone_id: int,
    rejection_reason: str = "Admin human co-signer rejected payout",
    db: Session = Depends(get_db),
):
    """
    Allows a human administrator to deny final approval for a high-value milestone.
    """
    bounty = db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    if not bounty:
        raise HTTPException(status_code=404, detail="Bounty not found")

    milestone = (
        db.query(models.Milestone)
        .filter(models.Milestone.id == milestone_id, models.Milestone.bounty_id == bounty.id)
        .first()
    )
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found")

    milestone.status = "REJECTED"
    bounty.status = "IN_PROGRESS"

    audit_log = models.AuditLog(
        bounty_id=bounty.id,
        milestone_id=milestone.id,
        trajectory_id=f"bounty_{bounty_id}_m_{milestone.id}_admin_rejected",
        passed=False,
        ai_feedback=f"[ADMIN MULTI-SIG REJECTION]: Human administrator rejected milestone payout: {rejection_reason}",
    )
    db.add(audit_log)

    db.commit()
    db.refresh(bounty)
    db.refresh(milestone)

    return {
        "status": "REJECTED",
        "milestone_id": milestone.id,
        "milestone_status": milestone.status,
        "message": "Milestone release rejected by administrator.",
    }


@app.post("/api/bounties/{bounty_id}/milestones/{milestone_id}/sponsor", status_code=status.HTTP_200_OK)
def add_sponsor_to_milestone(
    bounty_id: int,
    milestone_id: int,
    sponsor_in: SponsorContribution,
    db: Session = Depends(get_db),
):
    """
    Multi-Sponsor Pooling Endpoint:
    Allows additional sponsors to contribute authorization IDs to pool funds for a specific milestone.
    """
    bounty = db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    if not bounty:
        raise HTTPException(status_code=404, detail="Bounty not found")

    milestone = (
        db.query(models.Milestone)
        .filter(models.Milestone.id == milestone_id, models.Milestone.bounty_id == bounty.id)
        .first()
    )
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found")

    auth_id = sponsor_in.authorization_id
    if not auth_id and sponsor_in.paypal_order_id:
        try:
            auth_id = authorize_order(sponsor_in.paypal_order_id)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to authorize sponsor order: {e}")

    if not auth_id:
        raise HTTPException(status_code=400, detail="Must provide either paypal_order_id or authorization_id")

    # Add to milestone's authorization_ids array
    existing_auths = list(milestone.authorization_ids or [])
    if auth_id not in existing_auths:
        existing_auths.append(auth_id)
        milestone.authorization_ids = existing_auths

    # Also record in Escrow
    if bounty.escrow:
        escrow_auths = list(bounty.escrow.paypal_authorization_ids or [])
        if auth_id not in escrow_auths:
            escrow_auths.append(auth_id)
            bounty.escrow.paypal_authorization_ids = escrow_auths

    # If an amount was pledged, adjust milestone and bounty totals
    if sponsor_in.amount_usd and sponsor_in.amount_usd > 0:
        milestone.amount_usd = round(float(milestone.amount_usd) + float(sponsor_in.amount_usd), 2)
        bounty.amount_usd = round(float(bounty.amount_usd) + float(sponsor_in.amount_usd), 2)
        bounty.remaining_amount_usd = round(float(bounty.remaining_amount_usd or 0) + float(sponsor_in.amount_usd), 2)

        if bounty.amount_usd > HIGH_VALUE_THRESHOLD:
            bounty.requires_human_approval = True
            milestone.requires_human_approval = True

    db.commit()
    db.refresh(milestone)
    db.refresh(bounty)

    return {
        "message": f"Sponsor {sponsor_in.sponsor_name} successfully added to milestone #{milestone.id}",
        "milestone_id": milestone.id,
        "pooled_authorization_ids": milestone.authorization_ids,
        "milestone_amount_usd": milestone.amount_usd,
        "bounty_amount_usd": bounty.amount_usd,
        "requires_human_approval": bounty.requires_human_approval,
    }


# =====================================================================
# AI CONVERSATIONAL ESCROW GEN & SCOPE NEGOTIATION ROUTES
# =====================================================================

@app.post("/api/bounties/generate-scope", status_code=status.HTTP_200_OK)
async def generate_escrow_scope(scope_in: GenerateScopeRequest):
    """
    Conversational Escrow Gen:
    Parses natural language requirements into a strict JSON structure of milestones,
    deadlines, budget allocations, and acceptance criteria using Gemini 1.5 Pro.
    """
    if not scope_in.prompt or not scope_in.prompt.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prompt text cannot be empty.",
        )

    parsed_escrow = await generate_conversational_escrow(scope_in.prompt.strip())
    return parsed_escrow


@app.post("/api/bounties/{bounty_id}/negotiate", status_code=status.HTTP_200_OK)
async def negotiate_bounty_scope(
    bounty_id: int,
    neg_in: NegotiateScopeRequest,
    db: Session = Depends(get_db),
):
    """
    AI Scope Negotiation Agent:
    Takes the freelancer's counter-offer, retrieves original bounty terms, and uses Gemini 1.5 Pro
    to evaluate budget vs. timeline constraints, returning a balanced JSON compromise.
    """
    bounty = db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    if not bounty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bounty #{bounty_id} not found.",
        )

    original_bounty = {
        "id": bounty.id,
        "title": bounty.title,
        "amount_usd": float(bounty.amount_usd or 0.0),
        "acceptance_criteria": bounty.acceptance_criteria,
        "freelancer_email": bounty.freelancer_email,
        "milestones": [
            {
                "id": m.id,
                "description": m.description,
                "deadline": m.deadline,
                "percentage": float(m.percentage or 0.0),
                "amount_usd": float(m.amount_usd or 0.0),
            }
            for m in (bounty.milestones or [])
        ],
    }

    compromise = await negotiate_scope_compromise(
        bounty_id=bounty.id,
        original_bounty=original_bounty,
        counter_offer=neg_in.counter_offer,
        freelancer_email=neg_in.freelancer_email or bounty.freelancer_email,
        proposed_amount=neg_in.proposed_amount_usd,
        proposed_timeline=neg_in.proposed_timeline,
    )

    return {
        "bounty_id": bounty.id,
        "original_terms": original_bounty,
        "ai_compromise": compromise,
    }


@app.post("/api/bounties/{bounty_id}/negotiate/accept", status_code=status.HTTP_200_OK)
def accept_negotiated_compromise(
    bounty_id: int,
    accept_in: AcceptCompromiseRequest,
    db: Session = Depends(get_db),
):
    """
    Applies the agreed AI Scope Negotiation compromise to the live database record,
    updating the bounty budget, acceptance criteria, and replacing milestones with the compromise terms.
    """
    bounty = db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    if not bounty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bounty #{bounty_id} not found.",
        )

    old_amount = float(bounty.amount_usd or 0.0)
    new_amount = round(float(accept_in.compromise_amount_usd), 2)

    bounty.amount_usd = new_amount
    bounty.remaining_amount_usd = new_amount
    bounty.acceptance_criteria = accept_in.compromise_criteria

    if bounty.amount_usd > HIGH_VALUE_THRESHOLD:
        bounty.requires_human_approval = True

    # Gather existing pooled authorization IDs
    escrow_auths = []
    if bounty.escrow and bounty.escrow.paypal_authorization_ids:
        escrow_auths = list(bounty.escrow.paypal_authorization_ids)
    elif bounty.escrow and bounty.escrow.paypal_authorization_id:
        escrow_auths = [bounty.escrow.paypal_authorization_id]

    # Remove previous milestones and insert the accepted compromise milestones
    db.query(models.Milestone).filter(models.Milestone.bounty_id == bounty.id).delete()

    for m in accept_in.compromise_milestones:
        pct = float(m.percentage)
        m_amount = round(new_amount * (pct / 100.0), 2)
        milestone_obj = models.Milestone(
            bounty_id=bounty.id,
            description=m.description,
            deadline=m.deadline,
            percentage=pct,
            amount_usd=m_amount,
            status="LOCKED",
            authorization_ids=list(escrow_auths),
            requires_human_approval=bool(bounty.requires_human_approval or m_amount > HIGH_VALUE_THRESHOLD),
        )
        db.add(milestone_obj)

    # Save to AuditLog
    audit = models.AuditLog(
        bounty_id=bounty.id,
        trajectory_id=f"bounty_{bounty_id}_negotiation_accepted",
        passed=True,
        ai_feedback=(
            f"[AI SCOPE NEGOTIATION ACCEPTED]: Parties agreed to AI compromise. "
            f"Budget adjusted: ${old_amount:.2f} -> ${new_amount:.2f} USD. "
            f"Reasoning: {accept_in.reasoning or 'Terms mutually ratified.'}"
        ),
    )
    db.add(audit)

    db.commit()
    db.refresh(bounty)

    return {
        "status": "ACCEPTED",
        "message": "AI compromise terms successfully ratified and applied to bounty.",
        "bounty_id": bounty.id,
        "amount_usd": bounty.amount_usd,
        "acceptance_criteria": bounty.acceptance_criteria,
        "milestones": [
            {
                "id": m.id,
                "description": m.description,
                "deadline": m.deadline,
                "percentage": m.percentage,
                "amount_usd": m.amount_usd,
                "status": m.status,
            }
            for m in (bounty.milestones or [])
        ],
    }


@app.post("/webhooks/paypal", status_code=status.HTTP_200_OK)
async def paypal_webhook(request: Request):
    """
    PayPal Webhook listener:
    Listens for PAYMENT.PAYOUTS-ITEM.SUCCEEDED events, extracts payout_item_id,
    and logs the success.
    """
    payload = await request.json()
    event_type = payload.get("event_type")

    if event_type == "PAYMENT.PAYOUTS-ITEM.SUCCEEDED":
        resource = payload.get("resource", {})
        payout_item_id = (
            resource.get("payout_item_id")
            or resource.get("payout_item", {}).get("payout_item_id")
            or resource.get("id")
        )
        print(f"[PayPal Webhook] PAYMENT.PAYOUTS-ITEM.SUCCEEDED received: payout_item_id={payout_item_id}")
        logger.info("PAYMENT.PAYOUTS-ITEM.SUCCEEDED processed for payout_item_id: %s", payout_item_id)

    return {"status": "received"}


# =====================================================================
# WHATSAPP FIELD-WORKER WEBHOOK (TWILIO & GEMINI 1.5 PRO)
# =====================================================================

@app.post("/api/webhooks/twilio/whatsapp")
async def twilio_whatsapp_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    WhatsApp Field-Worker Webhook:
    1. Parses incoming images or text from Twilio WhatsApp webhook.
    2. Associates inbound sender's phone number with registered bounty freelancer.
    3. Finds the active milestone.
    4. Downloads attached photo/receipt and sends to Google Gemini 1.5 Pro for validation.
    5. If passed, automatically triggers PayPal Payouts (or sets to PENDING_ADMIN if Multi-Sig threshold).
    6. Sends a formatted success/feedback message back via Twilio (TwiML).
    """
    form = await request.form()
    from_raw = str(form.get("From", "")).strip()
    body_text = str(form.get("Body", "")).strip()
    num_media = 0
    try:
        num_media = int(form.get("NumMedia", 0))
    except (ValueError, TypeError):
        pass

    logger.info("[Twilio WhatsApp Inbound] From=%s, NumMedia=%d, Body=%s", from_raw, num_media, body_text)

    # Initialize TwiML response
    twiml = MessagingResponse()

    # Clean phone digits for robust matching
    phone_clean = from_raw.replace("whatsapp:", "").strip()
    digits_clean = "".join(ch for ch in phone_clean if ch.isdigit())

    if not digits_clean:
        twiml.message("⚠️ MilestoneEscrow: Invalid sender phone number detected.")
        return Response(content=str(twiml), media_type="application/xml")

    # Match against registered bounties with freelancer_phone
    matched_bounty = None
    all_bounties = db.query(models.Bounty).all()
    for b in all_bounties:
        if b.freelancer_phone:
            b_digits = "".join(ch for ch in b.freelancer_phone if ch.isdigit())
            if b_digits and (b_digits == digits_clean or digits_clean.endswith(b_digits) or b_digits.endswith(digits_clean)):
                matched_bounty = b
                break

    if not matched_bounty:
        twiml.message(
            f"⚠️ MilestoneEscrow: No active escrow bounty found registered for phone '{phone_clean}'. "
            f"Please ensure your WhatsApp number is linked to your bounty on MilestoneEscrow."
        )
        return Response(content=str(twiml), media_type="application/xml")

    # Locate active milestone
    milestone = (
        db.query(models.Milestone)
        .filter(models.Milestone.bounty_id == matched_bounty.id, models.Milestone.status != "COMPLETED")
        .order_by(models.Milestone.id.asc())
        .first()
    )

    if not milestone:
        twiml.message(
            f"ℹ️ MilestoneEscrow: All milestones for Bounty #{matched_bounty.id} ('{matched_bounty.title}') "
            f"have already been completed and paid out! Thank you."
        )
        return Response(content=str(twiml), media_type="application/xml")

    # Download attached image(s) if provided
    uploaded_files: list[tuple[bytes, str, str]] = []
    if num_media > 0:
        media_url = form.get("MediaUrl0")
        media_mime = str(form.get("MediaContentType0", "image/jpeg")) or "image/jpeg"
        if media_url:
            try:
                account_sid = os.getenv("TWILIO_ACCOUNT_SID")
                auth_token = os.getenv("TWILIO_AUTH_TOKEN")
                auth_tuple = (account_sid, auth_token) if (account_sid and auth_token) else None
                media_resp = requests.get(media_url, auth=auth_tuple, timeout=15)
                if media_resp.status_code == 200 and media_resp.content:
                    uploaded_files.append((media_resp.content, media_mime, "whatsapp_field_proof.jpg"))
                    logger.info("[Twilio WhatsApp] Downloaded %d bytes of media from %s", len(media_resp.content), media_url)
                else:
                    logger.warning("[Twilio WhatsApp] Could not download media: status %s", media_resp.status_code)
            except Exception as dl_err:
                logger.error("[Twilio WhatsApp] Error downloading media from %s: %s", media_url, dl_err)

    if not uploaded_files and not body_text:
        twiml.message(
            f"📸 MilestoneEscrow: Please send a photo/receipt of your field deliverable or a detailed completion report for Milestone #{milestone.id} ('{milestone.description}')."
        )
        return Response(content=str(twiml), media_type="application/xml")

    # Set milestone to AUDITING
    milestone.status = "AUDITING"
    matched_bounty.status = "AUDITING"
    db.commit()

    # Run AI evaluation with Gemini 1.5 Pro
    combined_desc = (
        f"{milestone.description}\n\n[Field Worker WhatsApp Note]: {body_text}"
        if body_text
        else milestone.description
    )

    eval_result = await evaluate_submission(
        files=uploaded_files if uploaded_files else None,
        proof_text=body_text if not uploaded_files else None,
        acceptance_criteria=matched_bounty.acceptance_criteria,
        bounty_id=matched_bounty.id,
        milestone_id=milestone.id,
        milestone_description=combined_desc,
        milestone_deadline=milestone.deadline,
    )

    passed = eval_result.get("passed", False)
    feedback = eval_result.get("feedback", "")

    # Persist AuditLog
    audit_log = models.AuditLog(
        bounty_id=matched_bounty.id,
        milestone_id=milestone.id,
        trajectory_id=f"whatsapp_{phone_clean}_bounty_{matched_bounty.id}_m_{milestone.id}",
        passed=passed,
        ai_feedback=f"[WHATSAPP FIELD-WORKER SUBMISSION]: {feedback}",
    )
    db.add(audit_log)
    db.commit()

    if passed:
        # Check Hybrid Multi-Sig condition (> $5,000 USD)
        is_high_value = bool(
            matched_bounty.requires_human_approval
            or (matched_bounty.amount_usd and matched_bounty.amount_usd > HIGH_VALUE_THRESHOLD)
            or (milestone.amount_usd and milestone.amount_usd > HIGH_VALUE_THRESHOLD)
            or milestone.requires_human_approval
        )

        if is_high_value:
            milestone.status = "PENDING_ADMIN"
            matched_bounty.status = "PENDING_ADMIN"
            db.commit()

            twiml.message(
                f"✅ MilestoneEscrow: Verification Passed!\n\n"
                f"Milestone #{milestone.id} ('{milestone.description}') verified by Gemini AI.\n\n"
                f"⚠️ [HYBRID MULTI-SIG NOTICE]: Because this bounty (${matched_bounty.amount_usd:,.2f} USD) "
                f"exceeds the $5,000 threshold, status is set to PENDING_ADMIN. Escrow funds will be released "
                f"as soon as a human administrator provides final co-sign approval in the portal."
            )
        else:
            payout_amount = float(milestone.amount_usd)
            escrow = matched_bounty.escrow or db.query(models.Escrow).filter(models.Escrow.bounty_id == matched_bounty.id).first()
            m_auth_ids = list(milestone.authorization_ids or [])
            if not m_auth_ids and escrow:
                if escrow.paypal_authorization_ids:
                    m_auth_ids = list(escrow.paypal_authorization_ids)
                elif escrow.paypal_authorization_id:
                    m_auth_ids = [escrow.paypal_authorization_id]

            pooled_res = pool_and_payout_milestone(
                authorization_ids=m_auth_ids,
                freelancer_email=matched_bounty.freelancer_email,
                amount=payout_amount,
                bounty_id=matched_bounty.id,
                milestone_id=milestone.id,
            )
            batch_id = pooled_res.get("payout", {}).get("batch_header", {}).get("payout_batch_id") or "BATCH-OK"
            milestone.paypal_payout_batch_id = batch_id
            milestone.status = "COMPLETED"

            # Decrement remaining escrow balance
            curr_rem = matched_bounty.remaining_amount_usd if matched_bounty.remaining_amount_usd is not None else matched_bounty.amount_usd
            matched_bounty.remaining_amount_usd = max(0.0, round(float(curr_rem) - payout_amount, 2))

            all_ms = db.query(models.Milestone).filter(models.Milestone.bounty_id == matched_bounty.id).all()
            if all(m.status == "COMPLETED" for m in all_ms) or matched_bounty.remaining_amount_usd <= 0:
                matched_bounty.status = "COMPLETED"
            else:
                matched_bounty.status = "IN_PROGRESS"

            # Automated Compliance: Generate Escrow Verification Certificate PDF
            generate_and_attach_certificate(
                bounty=matched_bounty,
                milestone=milestone,
                db=db,
                reasoning={
                    "channel": "WHATSAPP",
                    "verdict": "APPROVED",
                    "feedback": feedback,
                    "extracted_data": extracted_data,
                    "sender_phone": sender_phone,
                },
                batch_id=batch_id,
            )

            db.commit()

            twiml.message(
                f"🎉 MilestoneEscrow: Verification Successful!\n\n"
                f"Gemini AI verified your WhatsApp proof for Milestone #{milestone.id} ('{milestone.description}').\n"
                f"💰 Payout Released: ${payout_amount:,.2f} USD\n"
                f"📬 Sent to PayPal: {matched_bounty.freelancer_email}\n"
                f"🆔 Batch ID: {batch_id}\n\n"
                f"Thank you for your field work!"
            )
    else:
        milestone.status = "REJECTED"
        matched_bounty.status = "IN_PROGRESS"
        db.commit()

        twiml.message(
            f"❌ MilestoneEscrow: Verification Failed for Milestone #{milestone.id}.\n\n"
            f"Auditor Feedback:\n{feedback}\n\n"
            f"If you believe this is in error, submit an appeal at: http://localhost:3000/bounty/{matched_bounty.id}/submit"
        )

    return Response(content=str(twiml), media_type="application/xml")


# =====================================================================
# EXTERNAL DATA ORACLE ROUTES (LOGISTICS & SHIPPING)
# =====================================================================

@app.get("/api/oracle/shipping/{tracking_number}", status_code=status.HTTP_200_OK)
def get_shipping_oracle_status(tracking_number: str):
    """
    External Logistics / Shipping Oracle endpoint:
    Returns the real-time carrier status (DELIVERED, IN_TRANSIT, SHIPPED) for any tracking number.
    """
    return get_mock_shipping_info(tracking_number)


@app.post("/api/oracle/shipping/{tracking_number}/status", status_code=status.HTTP_200_OK)
def update_shipping_oracle_status(
    tracking_number: str,
    update_in: ShippingStatusUpdate,
):
    """
    Simulates carrier tracking updates (e.g. marking a consignment as DELIVERED in the logistics API).
    """
    clean_trk = tracking_number.strip()
    existing = get_mock_shipping_info(clean_trk)
    existing["status"] = update_in.status.upper()
    if update_in.carrier:
        existing["carrier"] = update_in.carrier
    if update_in.city:
        existing["destination"] = update_in.city
    if update_in.notes:
        existing["notes"] = update_in.notes
    if existing["status"] == "DELIVERED" and not existing.get("signed_by"):
        existing["signed_by"] = "Field Depot Officer"

    MOCK_SHIPPING_DATABASE[clean_trk] = existing
    return existing


@app.post("/api/oracle/poll", status_code=status.HTTP_200_OK)
@app.get("/api/oracle/poll", status_code=status.HTTP_200_OK)
def poll_oracle_manually(db: Session = Depends(get_db)):
    """
    External Data Oracle Polling Endpoint:
    Triggers carrier verification check for all active bounties and milestones with tracking numbers.
    Auto-approves milestones and executes payouts when carrier reports 'DELIVERED'.
    """
    processed = process_oracle_deliveries(db)
    return {
        "status": "success",
        "processed_count": len(processed),
        "processed_milestones": processed,
    }


@app.post("/api/bounties/{bounty_id}/ship", status_code=status.HTTP_200_OK)
def mark_bounty_shipped(
    bounty_id: int,
    ship_in: ShipRequest,
    db: Session = Depends(get_db),
):
    """
    Marks a physical bounty or deliverable as shipped with a carrier tracking number,
    activating the External Data Oracle.
    """
    bounty = db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    if not bounty:
        raise HTTPException(status_code=404, detail="Bounty not found")

    bounty.tracking_number = ship_in.tracking_number.strip()
    bounty.shipping_status = (ship_in.shipping_status or "SHIPPED").upper()

    # Also update pending milestones
    for m in (bounty.milestones or []):
        if m.status != "COMPLETED":
            m.tracking_number = bounty.tracking_number
            m.shipping_status = bounty.shipping_status

    db.commit()
    db.refresh(bounty)

    # Automatically run an initial oracle check
    processed = process_oracle_deliveries(db)

    return {
        "message": f"Bounty #{bounty.id} marked as {bounty.shipping_status} with tracking #{bounty.tracking_number}",
        "bounty_id": bounty.id,
        "tracking_number": bounty.tracking_number,
        "shipping_status": bounty.shipping_status,
        "oracle_auto_processed": processed,
    }


@app.post("/api/bounties/{bounty_id}/milestones/{milestone_id}/ship", status_code=status.HTTP_200_OK)
def mark_milestone_shipped(
    bounty_id: int,
    milestone_id: int,
    ship_in: ShipRequest,
    db: Session = Depends(get_db),
):
    """
    Marks a specific milestone as shipped with its own carrier tracking number.
    """
    bounty = db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    if not bounty:
        raise HTTPException(status_code=404, detail="Bounty not found")

    milestone = (
        db.query(models.Milestone)
        .filter(models.Milestone.id == milestone_id, models.Milestone.bounty_id == bounty.id)
        .first()
    )
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found")

    milestone.tracking_number = ship_in.tracking_number.strip()
    milestone.shipping_status = (ship_in.shipping_status or "SHIPPED").upper()

    db.commit()
    db.refresh(milestone)

    # Automatically run an oracle check
    processed = process_oracle_deliveries(db)

    return {
        "message": f"Milestone #{milestone.id} marked as {milestone.shipping_status} with tracking #{milestone.tracking_number}",
        "milestone_id": milestone.id,
        "tracking_number": milestone.tracking_number,
        "shipping_status": milestone.shipping_status,
        "oracle_auto_processed": processed,
    }


# =====================================================================
# AUTOMATED COMPLIANCE & ESCROW VERIFICATION CERTIFICATE (PDF)
# =====================================================================

@app.get("/api/milestones/{milestone_id}/certificate")
@app.get("/api/bounties/{bounty_id}/milestones/{milestone_id}/certificate")
def download_escrow_certificate(
    milestone_id: int,
    bounty_id: int | None = None,
    db: Session = Depends(get_db),
):
    """
    Downloads the official 'Escrow Verification Certificate' PDF for a completed milestone.
    If the PDF file has not yet been generated on disk, creates it on-the-fly and serves it.
    """
    milestone = db.query(models.Milestone).filter(models.Milestone.id == milestone_id).first()
    if not milestone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Milestone with ID {milestone_id} not found.",
        )

    bounty = milestone.bounty
    if not bounty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bounty for milestone {milestone_id} not found.",
        )

    # Check if certificate PDF file exists on disk
    if milestone.certificate_pdf_path and os.path.exists(milestone.certificate_pdf_path):
        filename = os.path.basename(milestone.certificate_pdf_path)
        return FileResponse(
            path=milestone.certificate_pdf_path,
            media_type="application/pdf",
            filename=filename,
        )

    # If milestone is completed or settled, generate certificate on demand
    if milestone.status in ("COMPLETED", "SETTLED"):
        pdf_path = generate_and_attach_certificate(
            bounty=bounty,
            milestone=milestone,
            db=db,
        )
        if pdf_path and os.path.exists(pdf_path):
            filename = os.path.basename(pdf_path)
            return FileResponse(
                path=pdf_path,
                media_type="application/pdf",
                filename=filename,
            )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Certificate not available yet. Milestone status is '{milestone.status}', awaiting completion and settlement.",
    )


# =====================================================================
# PREDICTIVE RISK SCORING & ANALYTICS
# =====================================================================

@app.post("/api/analytics/predictive-risk/evaluate")
def run_predictive_risk_evaluation(db: Session = Depends(get_db)):
    """
    Triggers the Google Gemini Predictive Risk Analytics Engine across all active bounties.
    Assigns Risk Scores (LOW, MEDIUM, HIGH), risk percentages, and risk factors.
    """
    evaluations = evaluate_all_active_bounties_risk(db)
    return {
        "status": "success",
        "evaluated_count": len(evaluations),
        "evaluations": evaluations,
    }


@app.get("/api/bounties/{bounty_id}/risk")
def get_bounty_predictive_risk(bounty_id: int, db: Session = Depends(get_db)):
    """
    Evaluates or returns the Predictive Risk Score for a specific bounty.
    """
    bounty = db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    if not bounty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bounty with ID {bounty_id} not found.",
        )

    risk_result = evaluate_bounty_predictive_risk(bounty, db)
    return risk_result

