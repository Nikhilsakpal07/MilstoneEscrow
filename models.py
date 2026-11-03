from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, Text, JSON
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Bounty(Base):
    __tablename__ = "bounties"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    acceptance_criteria = Column(Text)
    amount_usd = Column(Float)
    remaining_amount_usd = Column(Float, nullable=True)  # Tracks remaining funds in escrow
    freelancer_email = Column(String)
    status = Column(String, default="AWAITING_FUNDS")  # AWAITING_FUNDS, LOCKED, IN_PROGRESS, PENDING_ADMIN, COMPLETED, REJECTED
    requires_human_approval = Column(Boolean, default=False)  # Hybrid Multi-Sig (> $5,000 threshold)
    freelancer_phone = Column(String, nullable=True, index=True)  # WhatsApp Field-Worker Integration
    tracking_number = Column(String, nullable=True, index=True)  # External Data Oracle (Logistics)
    shipping_status = Column(String, default="NOT_SHIPPED")  # NOT_SHIPPED, SHIPPED, IN_TRANSIT, DELIVERED
    # Predictive Risk Scoring
    risk_score = Column(String, default="LOW")  # LOW, MEDIUM, HIGH
    risk_factors = Column(JSON, default=list)
    risk_percentage = Column(Integer, default=15)
    risk_updated_at = Column(String, nullable=True)

    escrow = relationship("Escrow", back_populates="bounty", uselist=False)
    audit_logs = relationship("AuditLog", back_populates="bounty")
    milestones = relationship("Milestone", back_populates="bounty", cascade="all, delete-orphan", order_by="Milestone.id")


class Milestone(Base):
    __tablename__ = "milestones"

    id = Column(Integer, primary_key=True, index=True)
    bounty_id = Column(Integer, ForeignKey("bounties.id"), index=True)
    description = Column(Text)
    deadline = Column(String)  # e.g., '2026-12-01'
    percentage = Column(Float)  # e.g., 50.0 (%)
    amount_usd = Column(Float)  # e.g., 250.00 ($)
    status = Column(String, default="LOCKED")  # LOCKED, AUDITING, PENDING_ADMIN, COMPLETED, REJECTED
    paypal_payout_batch_id = Column(String, nullable=True)
    authorization_ids = Column(JSON, default=list)  # Multi-Sponsor Pooling: array of PayPal authorization IDs
    requires_human_approval = Column(Boolean, default=False)  # Hybrid Multi-Sig (> $5,000)
    tracking_number = Column(String, nullable=True, index=True)  # Logistics tracking number
    shipping_status = Column(String, default="NOT_SHIPPED")  # NOT_SHIPPED, SHIPPED, IN_TRANSIT, DELIVERED
    # Automated Compliance Certificate (PDF)
    certificate_id = Column(String, nullable=True, index=True)
    certificate_pdf_path = Column(String, nullable=True)

    bounty = relationship("Bounty", back_populates="milestones")
    audit_logs = relationship("AuditLog", back_populates="milestone")


class CodeFingerprint(Base):
    __tablename__ = "code_fingerprints"

    id = Column(Integer, primary_key=True, index=True)
    freelancer_email = Column(String, index=True)
    bounty_id = Column(Integer, ForeignKey("bounties.id"))
    milestone_id = Column(Integer, nullable=True)
    github_url = Column(String, nullable=True)
    ast_hash = Column(String, index=True)
    naming_style = Column(JSON, default=dict)
    identifiers = Column(JSON, default=list)
    code_summary = Column(Text, nullable=True)
    created_at = Column(String)


class Escrow(Base):
    __tablename__ = "escrows"

    id = Column(Integer, primary_key=True, index=True)
    bounty_id = Column(Integer, ForeignKey("bounties.id"))
    paypal_order_id = Column(String, unique=True, index=True, nullable=True)
    paypal_authorization_id = Column(String, unique=True, nullable=True)
    paypal_capture_id = Column(String, unique=True, nullable=True)
    # Multi-Sponsor Pooling
    paypal_order_ids = Column(JSON, default=list)
    paypal_authorization_ids = Column(JSON, default=list)
    paypal_capture_ids = Column(JSON, default=list)

    bounty = relationship("Bounty", back_populates="escrow")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    bounty_id = Column(Integer, ForeignKey("bounties.id"))
    milestone_id = Column(Integer, ForeignKey("milestones.id"), nullable=True)
    trajectory_id = Column(String)
    passed = Column(Boolean)
    ai_feedback = Column(Text)

    bounty = relationship("Bounty", back_populates="audit_logs")
    milestone = relationship("Milestone", back_populates="audit_logs")
