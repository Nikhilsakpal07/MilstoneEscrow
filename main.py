import logging
from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db, engine
import models
from paypal_client import (
    authorize_order,
    capture_authorization,
    execute_payout,
    capture_multiple_authorizations,
    pool_and_payout_milestone,
)
from qa_agent import evaluate_submission, mediate_dispute

# Ensure database tables and newly added columns exist
models.Base.metadata.create_all(bind=engine)
try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE bounties ADD COLUMN IF NOT EXISTS remaining_amount_usd FLOAT;"))
        conn.execute(text("ALTER TABLE bounties ADD COLUMN IF NOT EXISTS requires_human_approval BOOLEAN DEFAULT FALSE;"))
        conn.execute(text("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS milestone_id INTEGER;"))
        conn.execute(text("ALTER TABLE milestones ADD COLUMN IF NOT EXISTS authorization_ids JSON DEFAULT '[]'::json;"))
        conn.execute(text("ALTER TABLE milestones ADD COLUMN IF NOT EXISTS requires_human_approval BOOLEAN DEFAULT FALSE;"))
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

app = FastAPI(title="MilestoneEscrow API")

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


class BountyCreate(BaseModel):
    title: str
    acceptance_criteria: str
    amount_usd: float
    freelancer_email: str
    paypal_order_id: str | None = None
    paypal_order_ids: list[str] = []
    milestones: list[MilestoneInput] = []


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
    and hybrid multi-sig flags.
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
            "status": b.status,
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
                    "paypal_payout_batch_id": m.paypal_payout_batch_id,
                }
                for m in (b.milestones or [])
            ],
        }
        for b in bounties
    ]


@app.get("/api/bounties/{bounty_id}")
def get_bounty(bounty_id: int, db: Session = Depends(get_db)):
    """
    Returns a single bounty with all associated milestone rows, pooled sponsor authorizations, and escrow data.
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
        "status": bounty.status,
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
                "paypal_payout_batch_id": m.paypal_payout_batch_id,
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
    """
    print(f"[DEBUG] Incoming Bounty Creation Payload: {bounty_in.model_dump()}")

    is_high_value = bounty_in.amount_usd > HIGH_VALUE_THRESHOLD

    new_bounty = models.Bounty(
        title=bounty_in.title,
        acceptance_criteria=bounty_in.acceptance_criteria,
        amount_usd=bounty_in.amount_usd,
        remaining_amount_usd=bounty_in.amount_usd,
        freelancer_email=bounty_in.freelancer_email,
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
