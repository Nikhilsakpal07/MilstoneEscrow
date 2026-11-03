import logging
from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db, engine
import models
from paypal_client import authorize_order, capture_authorization, execute_payout
from qa_agent import evaluate_submission

# Ensure database tables are created on startup
models.Base.metadata.create_all(bind=engine)

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


class BountyCreate(BaseModel):
    title: str
    acceptance_criteria: str
    amount_usd: float
    freelancer_email: str
    paypal_order_id: str


class WorkSubmission(BaseModel):
    github_url: str


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
    print(f"[DEBUG] Incoming Bounty Creation Payload: {bounty_in.model_dump()}")

    new_bounty = models.Bounty(
        title=bounty_in.title,
        acceptance_criteria=bounty_in.acceptance_criteria,
        amount_usd=bounty_in.amount_usd,
        freelancer_email=bounty_in.freelancer_email,
        status="LOCKED",
    )
    db.add(new_bounty)
    db.flush()

    # Authorize the order to lock funds and retrieve PayPal Authorization ID
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

    db.commit()
    db.refresh(new_bounty)

    return {"bounty_id": new_bounty.id, "id": new_bounty.id}


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
    4. If passed: captures PayPal escrow authorization and executes freelancer payout.
    5. Updates bounty status to COMPLETED or REJECTED and commits to DB.
    """
    # Fetch the Bounty
    bounty = db.query(models.Bounty).filter(models.Bounty.id == bounty_id).first()
    if not bounty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bounty with ID {bounty_id} not found.",
        )

    # Fetch associated Escrow
    escrow = bounty.escrow or db.query(models.Escrow).filter(models.Escrow.bounty_id == bounty_id).first()

    # Evaluate submission via Antigravity QA Agent
    eval_result = await evaluate_submission(
        github_url=submission.github_url,
        acceptance_criteria=bounty.acceptance_criteria,
        bounty_id=bounty_id,
    )

    passed = eval_result.get("passed", False)
    feedback = eval_result.get("feedback", "")

    # Save the AI result to the AuditLog table
    audit_log = models.AuditLog(
        bounty_id=bounty.id,
        trajectory_id=f"bounty_{bounty_id}",
        passed=passed,
        ai_feedback=feedback,
    )
    db.add(audit_log)
    db.commit()

    # Process escrow & payout if submission passed
    if passed:
        if not escrow or not escrow.paypal_authorization_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Escrow record with a valid PayPal authorization ID is missing.",
            )

        # 1. Pull funds by capturing authorization
        capture_response = capture_authorization(escrow.paypal_authorization_id)
        if isinstance(capture_response, dict) and "id" in capture_response:
            escrow.paypal_capture_id = capture_response["id"]

        # 2. Execute payout to the freelancer
        execute_payout(
            freelancer_email=bounty.freelancer_email,
            amount=bounty.amount_usd,
            bounty_id=bounty_id,
        )

        bounty.status = "COMPLETED"
    else:
        bounty.status = "REJECTED"

    db.commit()
    db.refresh(bounty)

    return {
        "status": bounty.status,
        "feedback": feedback,
        "passed": passed,
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
