import os
import json
import logging
from datetime import datetime, date
from sqlalchemy.orm import Session

import models
from qa_agent import _generate_with_gemini

logger = logging.getLogger("milestone_escrow")


def evaluate_bounty_predictive_risk(bounty: models.Bounty, db: Session) -> dict:
    """
    Compares a bounty's approaching milestone deadlines against the frequency of
    submission updates and historical progress, using Google Gemini to assign a
    predictive Risk Score (LOW, MEDIUM, HIGH), risk percentage, and risk factors.
    """
    today = date.today()

    # 1. Inspect Milestones & Deadlines
    milestones = bounty.milestones or []
    total_milestones = len(milestones)
    completed_milestones = sum(1 for m in milestones if m.status == "COMPLETED")
    pending_milestones = [m for m in milestones if m.status != "COMPLETED"]

    nearest_deadline = None
    min_days_remaining = 999

    milestone_lines = []
    for m in milestones:
        m_deadline_date = None
        days_left_str = "Open / No date"
        if m.deadline:
            try:
                # Expecting YYYY-MM-DD
                d_parts = m.deadline.split("-")
                if len(d_parts) == 3:
                    m_deadline_date = date(int(d_parts[0]), int(d_parts[1]), int(d_parts[2]))
                    diff = (m_deadline_date - today).days
                    days_left_str = f"{diff} days remaining"
                    if m.status != "COMPLETED" and diff < min_days_remaining:
                        min_days_remaining = diff
                        nearest_deadline = m.deadline
            except Exception:
                pass

        milestone_lines.append(
            f"- Phase #{m.id}: {m.description} (${m.amount_usd:.2f}) &bull; Status: {m.status} &bull; Deadline: {m.deadline or 'Open'} ({days_left_str})"
        )

    milestone_summary = "\n".join(milestone_lines) if milestone_lines else "No milestones configured."

    # 2. Count Historical Submission / Audit Activity
    audit_count = (
        db.query(models.AuditLog)
        .filter(models.AuditLog.bounty_id == bounty.id)
        .count()
    )

    days_disp = min_days_remaining if min_days_remaining != 999 else "Not Specified"

    # Deterministic Baseline Rule
    if min_days_remaining <= 1 and completed_milestones == 0 and total_milestones > 0:
        fallback_score = "HIGH"
        fallback_pct = 85
        fallback_factors = [
            f"Imminent deadline ({days_disp} days remaining) with zero completed deliverables.",
            "High probability of schedule overrun or project delay.",
        ]
    elif min_days_remaining <= 4 and completed_milestones < (total_milestones / 2):
        fallback_score = "MEDIUM"
        fallback_pct = 55
        fallback_factors = [
            f"Approaching deadline ({days_disp} days remaining) with major milestones pending.",
            f"Recorded {audit_count} submission attempt(s) so far.",
        ]
    else:
        fallback_score = "LOW"
        fallback_pct = 15
        fallback_factors = [
            f"Comfortable timeline ({days_disp} days remaining) or steady milestone progress.",
            f"Completed {completed_milestones}/{total_milestones} milestones.",
        ]

    # 3. Call Google Gemini for Comprehensive Predictive Assessment
    try:
        from google import genai
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if api_key:
            client = genai.Client(api_key=api_key)
            risk_prompt = f"""You are the Predictive Risk Analytics Engine for MilestoneEscrow.
Analyze the delivery, abandonment, and default risk for this active escrow bounty.

Current Date: {today.isoformat()}
Bounty ID: #{bounty.id}
Title: {bounty.title}
Total Budget: ${bounty.amount_usd:.2f} USD
Status: {bounty.status}
Milestones Breakdown:
{milestone_summary}

Nearest Pending Milestone Deadline: {nearest_deadline or 'Open'} ({days_disp} days remaining)
Historical Submission / Audit Attempts Count: {audit_count}
Freelancer: {bounty.freelancer_email}

Instructions:
1. Objectively evaluate the delivery risk based on the time remaining until deadline vs completed work vs submission frequency.
2. If the deadline is <= 2 days away with 0 deliverables or low activity, assign HIGH.
3. If the deadline is 3-7 days with moderate deliverables, assign MEDIUM.
4. If healthy timeline or high completion rate, assign LOW.
5. Output strictly a raw JSON block at the very end in the format:
{{
  "risk_score": "LOW" | "MEDIUM" | "HIGH",
  "risk_percentage": integer,
  "risk_factors": ["concise factor 1", "concise factor 2"],
  "recommended_action": "Actionable advice for the client"
}}
"""
            response = _generate_with_gemini(client, risk_prompt, preferred_model="gemini-3.5-flash")
            resp_text = response.text or ""
            start = resp_text.rfind("{")
            end = resp_text.rfind("}")
            if start != -1 and end != -1:
                parsed = json.loads(resp_text[start : end + 1])
                score = str(parsed.get("risk_score", fallback_score)).upper()
                if score not in ("LOW", "MEDIUM", "HIGH"):
                    score = fallback_score
                pct = int(parsed.get("risk_percentage", fallback_pct))
                factors = parsed.get("risk_factors", fallback_factors)
                rec = parsed.get("recommended_action", "Monitor progress and keep communication active.")

                bounty.risk_score = score
                bounty.risk_percentage = pct
                bounty.risk_factors = factors
                bounty.risk_updated_at = datetime.utcnow().isoformat()
                db.commit()

                return {
                    "bounty_id": bounty.id,
                    "risk_score": score,
                    "risk_percentage": pct,
                    "risk_factors": factors,
                    "recommended_action": rec,
                    "updated_at": bounty.risk_updated_at,
                }
    except Exception as e:
        logger.warning("[Predictive Risk] Gemini evaluation exception for Bounty #%s: %s", bounty.id, e)

    # Use deterministic fallback
    bounty.risk_score = fallback_score
    bounty.risk_percentage = fallback_pct
    bounty.risk_factors = fallback_factors
    bounty.risk_updated_at = datetime.utcnow().isoformat()
    db.commit()

    return {
        "bounty_id": bounty.id,
        "risk_score": fallback_score,
        "risk_percentage": fallback_pct,
        "risk_factors": fallback_factors,
        "recommended_action": "Monitor progress on nearing deadlines.",
        "updated_at": bounty.risk_updated_at,
    }


def evaluate_all_active_bounties_risk(db: Session) -> list[dict]:
    """
    Evaluates predictive risk scores across all active, uncompleted bounties in the platform.
    """
    active_bounties = (
        db.query(models.Bounty)
        .filter(models.Bounty.status.in_(["LOCKED", "IN_PROGRESS", "AWAITING_FUNDS", "AUDITING"]))
        .all()
    )

    results = []
    for b in active_bounties:
        try:
            res = evaluate_bounty_predictive_risk(b, db)
            results.append(res)
        except Exception as err:
            logger.error("[Predictive Risk] Failed assessing Bounty #%s: %s", b.id, err)

    return results

