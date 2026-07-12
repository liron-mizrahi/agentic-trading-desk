"""Initial migration: create ``trades`` and ``analysis_logs`` tables.

Revision ID: 001
Revises: None
Create Date: 2026-07-11 06:31:00.000000+00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None

TRADE_STATUSES = ("PENDING", "APPROVED", "REJECTED", "EXECUTED", "FAILED", "EXPIRED")


def upgrade() -> None:
    # Enum type
    sa.Enum(*TRADE_STATUSES, name="trade_status_enum", create_constraint=True).create(
        op.get_bind()
    )

    # ── trades ──────────────────────────────────────────────────────────
    op.create_table(
        "trades",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"), nullable=False,
        ),
        sa.Column("ticker", sa.String(16), nullable=False, index=True),
        sa.Column("strategy", sa.String(64), nullable=False, server_default="momentum_dip"),
        sa.Column("decision", sa.String(16), nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("reasoning", sa.Text, nullable=True),
        sa.Column("proposed_price", sa.Float, nullable=True),
        sa.Column("position_size", sa.Float, nullable=True),
        sa.Column("position_size_pct", sa.Float, nullable=True),
        sa.Column("exit_condition", sa.Text, nullable=True),
        sa.Column("stop_loss", sa.Float, nullable=True),
        sa.Column("take_profit", sa.Float, nullable=True),
        sa.Column("risk_reward_ratio", sa.Float, nullable=True),
        sa.Column(
            "status",
            sa.Enum(*TRADE_STATUSES, name="trade_status_enum", create_constraint=True),
            nullable=False, server_default="PENDING", index=True,
        ),
        sa.Column("rsi_2_value", sa.Float, nullable=True),
        sa.Column("chop_value", sa.Float, nullable=True),
        sa.Column("sma_200_value", sa.Float, nullable=True),
        sa.Column("sector", sa.String(50), nullable=True),
        sa.Column("human_feedback", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── analysis_logs ───────────────────────────────────────────────────
    op.create_table(
        "analysis_logs",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"), nullable=False,
        ),
        sa.Column(
            "trade_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trades.id", ondelete="CASCADE"),
            nullable=True, index=True,
        ),
        sa.Column("ticker", sa.String(16), nullable=False, index=True),
        sa.Column("step1_passed", sa.Boolean, nullable=True),
        sa.Column("step2_passed", sa.Boolean, nullable=True),
        sa.Column("step3_passed", sa.Boolean, nullable=True),
        sa.Column("rsi2", sa.Float, nullable=True),
        sa.Column("chop", sa.Float, nullable=True),
        sa.Column("sma200", sa.Float, nullable=True),
        sa.Column("price", sa.Float, nullable=True),
        sa.Column("raw_llm_reasoning", sa.Text, nullable=True),
        sa.Column("technical_data", postgresql.JSONB, nullable=True),
        sa.Column("news_context", postgresql.JSONB, nullable=True),
        sa.Column("llm_decision", sa.String(16), nullable=True),
        sa.Column("llm_confidence", sa.Float, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("dead_letter", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("analysis_logs")
    op.drop_table("trades")
    sa.Enum(name="trade_status_enum").drop(op.get_bind(), checkfirst=True)
