"""
Unit tests for backend ORM models — Trade, AnalysisLog, TradeStatus.
"""

import sys
import os
from datetime import datetime, timezone
from uuid import UUID, uuid4

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# Must import from app package; add backend to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# We test model construction without a live DB by building instances manually
from app.models import Trade, TradeStatus, AnalysisLog, TimestampMixin
from app.database import Base


class TestTradeStatus:
    """Trade lifecycle state machine."""

    def test_enum_values(self):
        assert TradeStatus.PENDING.value == "PENDING"
        assert TradeStatus.APPROVED.value == "APPROVED"
        assert TradeStatus.REJECTED.value == "REJECTED"
        assert TradeStatus.EXECUTED.value == "EXECUTED"
        assert TradeStatus.FAILED.value == "FAILED"
        assert TradeStatus.EXPIRED.value == "EXPIRED"

    def test_enum_count(self):
        assert len(TradeStatus) == 6

    def test_from_string(self):
        assert TradeStatus("PENDING") == TradeStatus.PENDING
        assert TradeStatus("EXECUTED") == TradeStatus.EXECUTED

    def test_enum_membership(self):
        valid = {s.value for s in TradeStatus}
        assert "PENDING" in valid
        assert "APPROVED" in valid
        assert "FOO" not in valid


class TestTradeModel:
    """Trade model construction without DB — verifies defaults and to_dict()."""

    def _make_trade(self, **overrides):
        kwargs = {
            "id": uuid4(),
            "ticker": "AAPL",
            "strategy": "momentum_dip",
            "decision": "BUY",
            "confidence": 0.85,
            "reasoning": "Strong oversold bounce with RSI-2 at 8.3",
            "proposed_price": 150.00,
            "position_size": None,
            "position_size_pct": 2.5,
            "exit_condition": "QS Exit: close > previous day's high",
            "stop_loss": 142.50,
            "take_profit": 162.00,
            "risk_reward_ratio": 1.6,
            "status": TradeStatus.PENDING,
            "rsi_2_value": 8.3,
            "chop_value": 28.5,
            "sma_200_value": 145.00,
            "sector": "Technology",
            "human_feedback": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        kwargs.update(overrides)
        return Trade(**kwargs)

    def test_default_strategy(self):
        trade = self._make_trade(strategy="momentum_dip")
        assert trade.strategy == "momentum_dip"

    def test_ticker_stored(self):
        trade = self._make_trade(ticker="NVDA")
        assert trade.ticker == "NVDA"

    def test_status_pending_default(self):
        trade = self._make_trade()
        assert trade.status == TradeStatus.PENDING

    def test_to_dict_contains_all_keys(self):
        trade = self._make_trade()
        d = trade.to_dict()
        expected_keys = (
            "id", "ticker", "strategy", "decision", "confidence",
            "reasoning", "proposed_price", "position_size",
            "position_size_pct", "exit_condition", "stop_loss",
            "take_profit", "risk_reward_ratio", "status",
            "rsi_2_value", "chop_value", "sma_200_value",
            "sector", "human_feedback", "created_at", "updated_at",
        )
        for key in expected_keys:
            assert key in d, f"Missing key: {key}"

    def test_to_dict_id_is_string(self):
        trade = self._make_trade()
        assert isinstance(trade.to_dict()["id"], str)

    def test_to_dict_status_is_string(self):
        trade = self._make_trade()
        assert trade.to_dict()["status"] == "PENDING"

    def test_to_dict_nullables_are_none(self):
        trade = self._make_trade(
            human_feedback=None, confidence=None,
            position_size=None, reasoning=None,
        )
        d = trade.to_dict()
        assert d["human_feedback"] is None
        assert d["confidence"] is None
        assert d["position_size"] is None
        assert d["reasoning"] is None

    def test_to_dict_numeric_values(self):
        trade = self._make_trade(
            proposed_price=175.33,
            stop_loss=166.50,
            confidence=0.92,
        )
        d = trade.to_dict()
        assert d["proposed_price"] == 175.33
        assert d["stop_loss"] == 166.50
        assert d["confidence"] == 0.92

    def test_repr_contains_ticker_and_status(self):
        trade = self._make_trade(ticker="MSFT", status=TradeStatus.APPROVED)
        r = repr(trade)
        assert "MSFT" in r
        assert "APPROVED" in r

    def test_multiple_statuses(self):
        for status in TradeStatus:
            trade = self._make_trade(status=status)
            assert trade.status == status
            assert trade.to_dict()["status"] == status.value


class TestAnalysisLogModel:
    """AnalysisLog construction and to_dict()."""

    def _make_log(self, **overrides):
        kwargs = {
            "id": uuid4(),
            "trade_id": uuid4(),
            "ticker": "AAPL",
            "step1_passed": True,
            "step2_passed": True,
            "step3_passed": True,
            "rsi2": 8.3,
            "chop": 28.5,
            "sma200": 145.00,
            "price": 150.00,
            "raw_llm_reasoning": "RSI-2 oversold, CHOP trending, SMA200 confirmed",
            "technical_data": {"rsi2": 8.3, "chop": 28.5},
            "news_context": None,
            "llm_decision": "BUY",
            "llm_confidence": 0.85,
            "error_message": None,
            "retry_count": 0,
            "dead_letter": False,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        kwargs.update(overrides)
        return AnalysisLog(**kwargs)

    def test_dead_letter_entry_has_null_trade_id(self):
        log = self._make_log(trade_id=None, dead_letter=True, step1_passed=None)
        assert log.trade_id is None
        assert log.dead_letter is True

    def test_to_dict_all_keys(self):
        d = self._make_log().to_dict()
        expected = (
            "id", "trade_id", "ticker", "step1_passed", "step2_passed",
            "step3_passed", "rsi2", "chop", "sma200", "price",
            "raw_llm_reasoning", "technical_data", "news_context",
            "llm_decision", "llm_confidence", "error_message",
            "retry_count", "dead_letter", "created_at", "updated_at",
        )
        for key in expected:
            assert key in d, f"Missing key: {key}"

    def test_to_dict_retry_count_is_int(self):
        d = self._make_log(retry_count=2).to_dict()
        assert isinstance(d["retry_count"], int)
        assert d["retry_count"] == 2

    def test_to_dict_dead_letter_is_bool(self):
        d = self._make_log(dead_letter=True).to_dict()
        assert d["dead_letter"] is True

    def test_jsonb_fields(self):
        d = self._make_log(
            technical_data={"rsi": 8.3, "volume_spike": False},
            news_context={"sentiment": "neutral"},
        ).to_dict()
        assert d["technical_data"]["rsi"] == 8.3
        assert d["news_context"]["sentiment"] == "neutral"
