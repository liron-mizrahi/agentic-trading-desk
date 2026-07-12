"""Pydantic schemas for API request/response serialisation."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class TradeActionEnum(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class TradeCreate(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=16)
    strategy: str = Field(default="momentum_dip", max_length=64)
    decision: str | None = None
    confidence: float | None = None
    reasoning: str | None = None
    proposed_price: float | None = None
    position_size: float | None = None
    position_size_pct: float | None = None
    exit_condition: str | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    risk_reward_ratio: float | None = None
    rsi_2_value: float | None = None
    chop_value: float | None = None
    sma_200_value: float | None = None
    sector: str | None = None


class TradeResponse(BaseModel):
    id: str
    ticker: str
    strategy: str
    decision: str | None
    confidence: float | None
    reasoning: str | None
    proposed_price: float | None
    position_size: float | None
    position_size_pct: float | None
    exit_condition: str | None
    stop_loss: float | None
    take_profit: float | None
    risk_reward_ratio: float | None
    status: str
    rsi_2_value: float | None
    chop_value: float | None
    sma_200_value: float | None
    sector: str | None
    human_feedback: str | None
    analysis_logs: list[dict[str, Any]] | None = None
    created_at: str | None
    updated_at: str | None

    model_config = {"from_attributes": True}


class TradeAction(BaseModel):
    action: TradeActionEnum
    feedback: str | None = Field(None, max_length=2000)


class AnalysisRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=16)


class AnalysisLogResponse(BaseModel):
    id: str
    trade_id: str | None
    ticker: str
    step1_passed: bool | None
    step2_passed: bool | None
    step3_passed: bool | None
    rsi2: float | None
    chop: float | None
    sma200: float | None
    price: float | None
    raw_llm_reasoning: str | None
    technical_data: dict[str, Any] | None
    news_context: dict[str, Any] | None
    llm_decision: str | None
    llm_confidence: float | None
    error_message: str | None
    retry_count: int
    dead_letter: bool
    created_at: str | None

    model_config = {"from_attributes": True}


class WebSocketEvent(BaseModel):
    event: str = Field(description="NEW_TRADE | TRADE_UPDATED | SYSTEM_WARNING | CONNECTION_OK")
    trade_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
