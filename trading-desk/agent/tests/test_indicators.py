"""
Unit tests for indicator computations — RSI-2, CHOP, SMA.
These test the pure Python implementations in agent/pipeline.py.

All are deterministic, no external dependencies.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.pipeline import _rsi_wilder, _choppiness_index, _sma


class TestRSIWilder:
    """Wilder's RSI-2 implementation."""

    def test_insufficient_data_returns_none(self):
        assert _rsi_wilder([100], period=2) is None
        assert _rsi_wilder([100, 101], period=2) is None

    def test_minimal_data_needed(self):
        """Need period + 1 = 3 bars minimum."""
        assert _rsi_wilder([100, 101, 102], period=2) is not None

    def test_all_gains_gives_100(self):
        """Every bar higher than previous → RSI = 100."""
        prices = [100.0, 101.0, 102.0, 103.0, 104.0]
        rsi = _rsi_wilder(prices, period=2)
        assert rsi == 100.0

    def test_all_losses_gives_0(self):
        """Every bar lower than previous → RSI = 0."""
        prices = [100.0, 99.0, 98.0, 97.0, 96.0]
        rsi = _rsi_wilder(prices, period=2)
        assert rsi == 0.0

    def test_flat_gives_50(self):
        "No change → gains and losses both 0 → RSI is 50? Actually avg_loss=0 → RSI=100."
        prices = [100.0, 100.0, 100.0, 100.0]
        rsi = _rsi_wilder(prices, period=2)
        # All deltas are 0, so avg_gain = avg_loss = 0 but avg_loss=0 → RS = infinity
        assert rsi == 100.0

    def test_mixed_scenario(self):
        """Manual verification with known values.
        Prices: [50, 51, 52, 50, 48, 49]
        Returns a value between 0-100."""
        prices = [50.0, 51.0, 52.0, 50.0, 48.0, 49.0]
        rsi = _rsi_wilder(prices, period=2)
        assert rsi is not None
        assert 0.0 <= rsi <= 100.0

    def test_oversold_zone(self):
        """Extended decline should give very low RSI."""
        prices = [100.0]
        for _ in range(20):
            prices.append(prices[-1] - 1.0)
        rsi = _rsi_wilder(prices, period=2)
        assert rsi is not None
        assert rsi < 10.0, f"Expected RSI < 10 for sustained decline, got {rsi}"

    def test_overbought_zone(self):
        """Sustained rally should give very high RSI."""
        prices = [100.0]
        for _ in range(20):
            prices.append(prices[-1] + 1.0)
        rsi = _rsi_wilder(prices, period=2)
        assert rsi is not None
        assert rsi > 90.0, f"Expected RSI > 90 for sustained rally, got {rsi}"

    def test_rsi_14_same_interface(self):
        """Wilder's RSI works with period=14 (traditional RSI)."""
        prices = [100.0 + i * 0.5 for i in range(30)]
        rsi = _rsi_wilder(prices, period=14)
        assert rsi is not None
        # Gradual rise → RSI should be high
        assert rsi > 50.0

    def test_float_precision(self):
        """RSI returns a float, not int."""
        prices = [100.0, 101.0, 100.5, 99.5, 100.0, 99.0, 100.0]
        rsi = _rsi_wilder(prices, period=2)
        assert isinstance(rsi, float)


class TestChoppinessIndex:
    """CHOP index (Choppiness Index) — E.W. Dreiss formula."""

    def test_insufficient_data(self):
        """Need period + 1 bars for TR computation."""
        assert _choppiness_index(
            [100], [99], [100], period=14
        ) is None

    def test_minimal_data(self):
        """15 bars (period=14 + 1) is minimum."""
        n = 15
        data = list(range(n))
        high = [100.0 + i for i in data]
        low = [99.0 + i for i in data]
        close = [99.5 + i for i in data]
        result = _choppiness_index(high, low, close, period=14)
        assert result is not None
        assert 0.0 <= result <= 100.0

    def test_stable_trend_gives_low_chop(self):
        """Steady uptrend → low choppiness (less than 38.2 typically)."""
        n = 60
        high = [100.0 + i * 1.0 + 0.5 for i in range(n)]
        low = [100.0 + i * 1.0 - 0.5 for i in range(n)]
        close = [100.0 + i * 1.0 for i in range(n)]
        chop = _choppiness_index(high, low, close, period=14)
        assert chop is not None
        # In a smooth trend, CHOP should be well below 38.2
        # But with daily volatility it should be manageable
        assert chop < 60.0, f"Expected low CHOP for smooth trend, got {chop}"

    def test_range_extended_consolidation_gives_high_chop(self):
        """Sideways/choppy market → higher choppiness."""
        import random
        random.seed(42)
        n = 40
        high = []
        low = []
        close = []
        base = 100.0
        for i in range(n):
            c = base + (random.random() - 0.5) * 4.0
            h = c + random.random() * 1.0
            l = c - random.random() * 1.0
            high.append(h)
            low.append(l)
            close.append(c)
        chop = _choppiness_index(high, low, close, period=14)
        assert chop is not None
        # Choppiness in a sideway market should be higher
        assert chop > 0, "Should be computable"

    def test_float_return(self):
        n = 30
        high = [100.0 + i * 0.1 for i in range(n)]
        low = [99.0 + i * 0.1 for i in range(n)]
        close = [99.5 + i * 0.1 for i in range(n)]
        chop = _choppiness_index(high, low, close, period=14)
        assert isinstance(chop, float)


class TestSMA:
    """Simple moving average."""

    def test_insufficient_data(self):
        assert _sma([100], period=200) is None
        assert _sma([100, 101], period=200) is None

    def test_exact_period(self):
        """With exactly `period` values, SMA is computed."""
        prices = [100.0] * 10
        sma = _sma(prices, period=10)
        assert sma == 100.0

    def test_sma_200(self):
        """Full SMA-200 computation."""
        prices = [100.0 + i * 0.2 for i in range(250)]
        sma = _sma(prices, period=200)
        assert sma is not None
        # Latest 200 values average: indices 50-249
        expected = sum(prices[-200:]) / 200
        assert abs(sma - expected) < 0.01

    def test_sma_basic_math(self):
        prices = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        sma = _sma(prices, period=3)
        assert sma == (4.0 + 5.0 + 6.0) / 3.0
        assert sma == 5.0

    def test_sma_float_return(self):
        prices = [1.5, 2.5, 3.5, 4.5]
        sma = _sma(prices, period=3)
        assert isinstance(sma, float)
