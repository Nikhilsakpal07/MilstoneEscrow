from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Bounty(Base):
    __tablename__ = "bounties"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    acceptance_criteria = Column(Text)
    amount_usd = Column(Float)
    freelancer_email = Column(String)
    status = Column(String, default="AWAITING_FUNDS") # AWAITING_FUNDS, LOCKED, AUDITING, COMPLETED
    
    escrow = relationship("Escrow", back_populates="bounty", uselist=False)
    audit_logs = relationship("AuditLog", back_populates="bounty")

class Escrow(Base):
    __tablename__ = "escrows"
    
    id = Column(Integer, primary_key=True, index=True)
    bounty_id = Column(Integer, ForeignKey("bounties.id"))
    paypal_order_id = Column(String, unique=True, index=True)
    paypal_authorization_id = Column(String, unique=True, nullable=True)
    paypal_capture_id = Column(String, unique=True, nullable=True)
    
    bounty = relationship("Bounty", back_populates="escrow")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    bounty_id = Column(Integer, ForeignKey("bounties.id"))
    trajectory_id = Column(String)
    passed = Column(Boolean)
    ai_feedback = Column(Text)
    
    bounty = relationship("Bounty", back_populates="audit_logs")