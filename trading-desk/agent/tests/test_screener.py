"""
Unit tests for the agent screener module.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.screener import (
    SECTOR_TICKERS,
    get_tickers_for_sector,
    list_sectors,
)


class TestScreenerSectors:
    """Sector mapping and watchlist tests."""

    def test_all_sectors_have_tickers(self):
        for sector in SECTOR_TICKERS:
            tickers = SECTOR_TICKERS[sector]
            assert len(tickers) > 0, f"Sector {sector} has no tickers"
            assert len(tickers) <= 10, f"Sector {sector} has >10 tickers"

    def test_known_sectors(self):
        expected = [
            "Technology", "Financial Services", "Industrials",
            "Communication", "Consumer Cyclical", "Healthcare",
            "Energy", "Consumer Defensive", "Basic Materials",
            "Real Estate", "Utilities",
        ]
        for sec in expected:
            assert sec in SECTOR_TICKERS, f"Missing sector: {sec}"

    def test_get_tickers_returns_list(self):
        tickers = get_tickers_for_sector("Technology")
        assert isinstance(tickers, list)
        assert "AAPL" in tickers
        assert "MSFT" in tickers
        assert "NVDA" in tickers

    def test_unknown_sector_returns_empty(self):
        tickers = get_tickers_for_sector("NonExistent")
        assert tickers == []

    def test_list_sectors(self):
        sectors = list_sectors()
        assert len(sectors) == 11
        assert "Technology" in sectors
        assert "Healthcare" in sectors

    def test_all_tickers_are_uppercase(self):
        for sector, tickers in SECTOR_TICKERS.items():
            for ticker in tickers:
                assert ticker == ticker.upper(), f"{ticker} is not uppercase"
                assert ticker.isalpha(), f"{ticker} is not alphabetic"

    def test_no_duplicate_tickers_across_sectors(self):
        """Each ticker should appear in exactly one sector."""
        all_tickers = []
        for tickers in SECTOR_TICKERS.values():
            all_tickers.extend(tickers)
        assert len(all_tickers) == len(set(all_tickers)), "Duplicate tickers across sectors"
