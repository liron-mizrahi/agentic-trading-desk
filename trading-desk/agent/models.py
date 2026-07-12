"""
SQLAlchemy ORM models for the Agent Layer — sync-compatible mirror
of the canonical schema used by the FastAPI backend.

Tables must match the backend models exactly so both services share
the same PostgreSQL schema.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Trade(Base):
    __tablename__ = "trades"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String(16), nullable=False, index=True)
    strategy = Column(String(64), nullable=False, default="momentum_dip")
    decision = Column(String(16), nullable=True)
    confidence = Column(Float, nullable=True)
    reasoning = Column(Text, nullable=True)
    proposed_price = Column(Float, nullable=True)
    position_size = Column(Float, nullable=True)
    position_size_pct = Column(Float, nullable=True)
    exit_condition = Column(Text, nullable=True)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    risk_reward_ratio = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="PENDING", index=True)
    rsi_2_value = Column(Float, nullable=True)
    chop_value = Column(Float, nullable=True)
    sma_200_value = Column(Float, nullable=True)
    sector = Column(String(50), nullable=True)
    human_feedback = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    analysis_logs = relationship(
        "AnalysisLog",
        back_populates="trade",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AnalysisLog.created_at",
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "ticker": self.ticker,
            "strategy": self.strategy,
            "decision": self.decision,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "proposed_price": self.proposed_price,
            "position_size": self.position_size,
            "position_size_pct": self.position_size_pct,
            "exit_condition": self.exit_condition,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "risk_reward_ratio": self.risk_reward_ratio,
            "status": self.status,
            "rsi_2_value": self.rsi_2_value,
            "chop_value": self.chop_value,
            "sma_200_value": self.sma_200_value,
            "sector": self.sector,
            "human_feedback": self.human_feedback,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<Trade {self.ticker} status={self.status}>"


class AnalysisLog(Base):
    __tablename__ = "analysis_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trade_id = Column(
        UUID(as_uuid=True),
        ForeignKey("trades.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    ticker = Column(String(16), nullable=False, index=True)
    step1_passed = Column(Boolean, nullable=True)
    step2_passed = Column(Boolean, nullable=True)
    step3_passed = Column(Boolean, nullable=True)
    rsi2 = Column(Float, nullable=True)
    chop = Column(Float, nullable=True)
    sma200 = Column(Float, nullable=True)
    price = Column(Float, nullable=True)
    raw_llm_reasoning = Column(Text, nullable=True)
    technical_data = Column(JSONB, nullable=True)
    news_context = Column(JSONB, nullable=True)
    llm_decision = Column(String(16), nullable=True)
    llm_confidence = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    dead_letter = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    trade = relationship("Trade", back_populates="analysis_logs")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "trade_id": str(self.trade_id) if self.trade_id else None,
            "ticker": self.ticker,
            "step1_passed": self.step1_passed,
            "step2_passed": self.step2_passed,
            "step3_passed": self.step3_passed,
            "rsi2": self.rsi2,
            "chop": self.chop,
            "sma200": self.sma200,
            "price": self.price,
            "raw_llm_reasoning": self.raw_llm_reasoning,
            "technical_data": self.technical_data,
            "news_context": self.news_context,
            "llm_decision": self.llm_decision,
            "llm_confidence": self.llm_confidence,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "dead_letter": self.dead_letter,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<AnalysisLog {self.ticker} steps={self.step1_passed}/{self.step2_passed}/{self.step3_passed}>"
