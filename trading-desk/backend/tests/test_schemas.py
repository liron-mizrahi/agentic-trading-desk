"""
Unit tests for Pydantic schemas — validation and serialisation.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.schemas import (
    TradeCreate,
    TradeResponse,
    TradeAction,
    TradeActionEnum,
    AnalysisRequest,
    WebSocketEvent,
)


class TestTradeActionEnum:
    def test_values(self):
        assert TradeActionEnum.APPROVE == "APPROVE"
        assert TradeActionEnum.REJECT == "REJECT"

    def test_count(self):
        assert len(TradeActionEnum) == 2


class TestTradeCreate:
    def test_minimal_valid(self):
        tc = TradeCreate(ticker="AAPL")
        assert tc.ticker == "AAPL"
        assert tc.strategy == "momentum_dip"

    def test_ticker_too_long(self):
        from pydantic import ValidationError
        try:
            TradeCreate(ticker="A" * 17)
            assert False, "Should have raised"
        except ValidationError:
            pass

    def test_ticker_empty(self):
        from pydantic import ValidationError
        try:
            TradeCreate(ticker="")
            assert False, "Should have raised"
        except ValidationError:
            pass

    def test_optional_fields_default_none(self):
        tc = TradeCreate(ticker="MSFT")
        assert tc.proposed_price is None
        assert tc.confidence is None
        assert tc.rsi_2_value is None

    def test_full_payload(self):
        tc = TradeCreate(
            ticker="NVDA",
            strategy="momentum_dip",
            decision="BUY",
            confidence=0.92,
            proposed_price=800.00,
            position_size_pct=3.0,
            exit_condition="QS Exit: close > prev high",
            stop_loss=760.00,
            take_profit=864.00,
            risk_reward_ratio=1.6,
            rsi_2_value=12.5,
            chop_value=27.3,
            sma_200_value=720.00,
            sector="Technology",
        )
        assert tc.ticker == "NVDA"
        assert tc.confidence == 0.92
        assert tc.stop_loss == 760.00


class TestTradeAction:
    def test_approve(self):
        ta = TradeAction(action="APPROVE")
        assert ta.action == TradeActionEnum.APPROVE

    def test_reject_with_feedback(self):
        ta = TradeAction(action="REJECT", feedback="CHOP too high")
        assert ta.action == TradeActionEnum.REJECT
        assert ta.feedback == "CHOP too high"

    def test_invalid_action(self):
        from pydantic import ValidationError
        try:
            TradeAction(action="HOLD")
            assert False
        except ValidationError:
            pass

    def test_feedback_too_long(self):
        from pydantic import ValidationError
        try:
            TradeAction(action="APPROVE", feedback="x" * 2001)
            assert False
        except ValidationError:
            pass


class TestAnalysisRequest:
    def test_valid_ticker(self):
        ar = AnalysisRequest(ticker="TSLA")
        assert ar.ticker == "TSLA"

    def test_ticker_too_long(self):
        from pydantic import ValidationError
        try:
            AnalysisRequest(ticker="A" * 17)
            assert False
        except ValidationError:
            pass

    def test_ticker_empty(self):
        from pydantic import ValidationError
        try:
            AnalysisRequest(ticker="")
            assert False
        except ValidationError:
            pass

    def test_uppercase_validation(self):
        # Schema just validates length; uppercasing is API logic
        ar = AnalysisRequest(ticker="aapl")
        assert ar.ticker == "aapl"


class TestWebSocketEvent:
    def test_minimal_event(self):
        evt = WebSocketEvent(event="CONNECTION_OK")
        assert evt.event == "CONNECTION_OK"
        assert evt.trade_id is None
        assert evt.data == {}

    def test_new_trade_event(self):
        evt = WebSocketEvent(
            event="NEW_TRADE",
            trade_id="550e8400-e29b-41d4-a716-446655440000",
            data={"ticker": "AAPL", "confidence": 0.85},
        )
        assert evt.event == "NEW_TRADE"
        assert evt.trade_id == "550e8400-e29b-41d4-a716-446655440000"
        assert evt.data["ticker"] == "AAPL"

    def test_system_warning_event(self):
        evt = WebSocketEvent(
            event="SYSTEM_WARNING",
            data={"message": "DLQ: analysis failed for TSLA after 3 retries"},
        )
        assert evt.event == "SYSTEM_WARNING"
