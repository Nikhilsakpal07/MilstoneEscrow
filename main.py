import logging
from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db, engine
import models
from paypal_client import authorize_order, capture_authorization, execute_payout
from qa_agent import evaluate_submission, mediate_dispute

# Ensure database tables and newly added columns exist
models.Base.metadata.create_all(bind=engine)
try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE bounties ADD COLUMN IF NOT EXISTS remaining_amount_usd FLOAT;"))
        conn.execute(text("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS milestone_id INTEGER;"))
        conn.commit()
except Exception as migration_err:
    logging.getLogger("milestone_escrow").warning("Migration check: %s", migration_err)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("milestone_escrow")

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


class BountyCreate(BaseModel):
    title: str
    acceptance_criteria: str
    amount_usd: float
    freelancer_email: str
    paypal_order_id: str
    milestones: list[MilestoneInput] = []


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
    Returns a list of all bounties including their milestone progress and remaining funds.
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
            "milestones": [
                {
                    "id": m.id,
                    "description": m.description,
                    "deadline": m.deadline,
                    "percentage": m.percentage,
                    "amount_usd": m.amount_usd,
                    "status": m.status,
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
    Returns a single bounty with all associated milestone rows and escrow data.
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
        "escrow": {
            "paypal_order_id": bounty.escrow.paypal_order_id if bounty.escrow else None,
            "paypal_authorization_id": bounty.escrow.paypal_authorization_id if bounty.escrow else None,
            "paypal_capture_id": bounty.escrow.paypal_capture_id if bounty.escrow else None,
        } if bounty.escrow else None,
        "milestones": [
            {
                "id": m.id,
                "description": m.description,
                "deadline": m.deadline,
                "percentage": m.percentage,
                "amount_usd": m.amount_usd,
                "status": m.status,
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
    Creates a new Bounty with 'LOCKED' status and initializes individual Milestone rows,
    storing the provided PayPal order ID and authorization ID in Escrow.
    """
    print(f"[DEBUG] Incoming Bounty Creation Payload: {bounty_in.model_dump()}")

    new_bounty = models.Bounty(
        title=bounty_in.title,
        acceptance_criteria=bounty_in.acceptance_criteria,
        amount_usd=bounty_in.amount_usd,
        remaining_amount_usd=bounty_in.amount_usd,
        freelancer_email=bounty_in.freelancer_email,
        status="LOCKED",
    )
    db.add(new_bounty)
    db.flush()

    # Authorize order to lock funds & fetch authorization_id
    authorization_id = None
    try:
        authorization_id = authorize_order(bounty_in.paypal_order_id)
        print(f"[DEBUG] PayPal Authorized Successfully! Authorization ID: {authorization_id}")
    except Exception as e:
        print(f"[WARNING] Could not authorize order via PayPal API: {e}")

    new_escrow = models.Escrow(
        bounty_id=new_bounty.id,
        paypal_order_id=bounty_in.paypal_order_id,
        paypal_authorization_id=authorization_id,
    )
    db.add(new_escrow)

    # Insert milestone rows
    if bounty_in.milestones:
        for idx, m in enumerate(bounty_in.milestones):
            pct = float(m.percentage)
            m_amount = round(bounty_in.amount_usd * (pct / 100.0), 2)
            milestone_obj = models.Milestone(
                bounty_id=new_bounty.id,
                description=m.description,
                deadline=m.deadline,
                percentage=pct,
                amount_usd=m_amount,
                status="LOCKED",
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
        )
        db.add(milestone_obj)

    db.commit()
    db.refresh(new_bounty)

    return {"bounty_id": new_bounty.id, "id": new_bounty.id}


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
        if not escrow or not escrow.paypal_authorization_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Escrow record with a valid PayPal authorization ID is missing.",
            )

        # 1. Pull funds by capturing authorization (once for escrow if not yet captured)
        if not escrow.paypal_capture_id:
            capture_response = capture_authorization(escrow.paypal_authorization_id)
            if isinstance(capture_response, dict) and "id" in capture_response:
                escrow.paypal_capture_id = capture_response["id"]

        # 2. Execute payout for ONLY this specific milestone's amount
        payout_amount = float(milestone.amount_usd)
        payout_res = execute_payout(
            freelancer_email=bounty.freelancer_email,
            amount=payout_amount,
            bounty_id=bounty_id,
            milestone_id=milestone.id,
        )

        batch_id = payout_res.get("batch_header", {}).get("payout_batch_id")
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
    If overridden, automatically captures authorization and executes the milestone payout.
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
        # Release funds if escrow authorization is active
        if escrow and escrow.paypal_authorization_id:
            if not escrow.paypal_capture_id:
                capture_res = capture_authorization(escrow.paypal_authorization_id)
                if isinstance(capture_res, dict) and "id" in capture_res:
                    escrow.paypal_capture_id = capture_res["id"]

            payout_amount = float(milestone.amount_usd)
            payout_res = execute_payout(
                freelancer_email=bounty.freelancer_email,
                amount=payout_amount,
                bounty_id=bounty_id,
                milestone_id=milestone.id,
            )
            batch_id = payout_res.get("batch_header", {}).get("payout_batch_id")
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
