#!/usr/bin/env python3
"""
news_sentiment.py
=================
News Sentiment extraction for the Agentic Trading Desk.

Extracts structured sentiment data from multiple free sources:
  1. GDELT GKG API  — geopolitical event tone (free, no API key, pre-computed tone)
  2. Yahoo Finance RSS — ticker-specific headlines (free, no API key)
  3. Keyword-based heuristic fallback when APIs are unavailable

Returns a sentiment score in [-1, +1] per ticker/sector/macro.

Design: stdlib-only for HTTP (urllib), graceful degradation — if all sources
fail, returns neutral (0.0). Never blocks the pipeline.

Usage:
  python3 scripts/news_sentiment.py macro              # Macro/geopolitical sentiment
  python3 scripts/news_sentiment.py ticker AAPL        # Ticker-specific sentiment
  python3 scripts/news_sentiment.py sector Technology  # Sector-level sentiment
  python3 scripts/news_sentiment.py full AAPL Technology  # Combined ticker + sector + macro
  python3 scripts/news_sentiment.py --json full AAPL Technology
"""

from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import urllib.request
from datetime import datetime, timezone
from typing import Optional
from xml.etree import ElementTree


# ── GDELT GKG API ──────────────────────────────────────────────────────

GKG_URL = "https://api.gdeltproject.org/api/v2/gkg/gkg"
YAHOO_RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline"

# Unverified SSL context for APIs that may have cert issues in server environments
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


def _http_get(url: str, timeout: int = 10) -> Optional[str]:
    """HTTP GET with stdlib, returns text or None on any failure."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "AgenticTradingDesk/1.0",
            "Accept": "application/json, application/xml, text/*",
        })
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            raw = resp.read()
            return raw.decode("utf-8", errors="replace")
    except Exception:
        return None


# ── Geopolitical Sentiment (GDELT GKG) ─────────────────────────────────

# Keywords mapped to categories for the GDELT query
GEOPOLITICAL_KEYWORDS = [
    "geopolitical conflict",
    "sanctions",
    "trade war",
    "tariffs",
    "military escalation",
    "central bank emergency",
    "sovereign debt crisis",
    "energy supply disruption",
    "chip export control",
    "technology restrictions",
]

FINANCIAL_MACRO_KEYWORDS = [
    "federal reserve interest rate",
    "inflation report",
    "recession risk",
    "market crash",
    "bank failure",
    "credit crisis",
    "bond market",
    "stock market rally",
    "earnings season",
    "economic growth",
]


def _fetch_gdelt_tone(query: str, max_records: int = 10) -> Optional[float]:
    """Fetch average tone score from GDELT GKG for a given query.

    GDELT tone ranges roughly -10 to +10, centered around 0.
    Returns None if no data or API failure.
    """
    encoded = urllib.parse.quote(query)
    url = f"{GKG_URL}?query={encoded}&mode=tonechart&format=json&maxrecords={max_records}"
    text = _http_get(url, timeout=15)
    if not text:
        return None

    try:
        data = json.loads(text)
        # tonechart format returns an array of arrays:
        # [tone_value, count, ...]
        if isinstance(data, list) and len(data) > 0:
            total_tone = 0.0
            total_count = 0
            for row in data:
                if isinstance(row, list) and len(row) >= 2:
                    tone = float(row[0])
                    count = int(row[1])
                    # Weight by count
                    total_tone += tone * count
                    total_count += count
            if total_count > 0:
                return total_tone / total_count
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    return None


def _gdelt_tone_to_score(tone: float) -> float:
    """Convert GDELT raw tone (-10..+10) to sentiment score [-1, +1]."""
    # Clamp to [-3, +3] range (extreme tone values are rare)
    clamped = max(-3.0, min(3.0, tone))
    return round(clamped / 3.0, 2)


def fetch_geopolitical_sentiment() -> dict:
    """Fetch geopolitical and macro news sentiment via GDELT.

    Returns:
      {
        "score": float in [-1, +1],
        "confidence": float in [0, 1],
        "signals": list[str],
        "source": "gdelt_gkg" | "fallback_neutral",
        "fetched_at": "ISO-8601"
      }
    """
    signals = []
    tones = []

    # Fetch geopolitical tone
    geo_tone = _fetch_gdelt_tone(" OR ".join(GEOPOLITICAL_KEYWORDS[:5]))
    if geo_tone is not None:
        tones.append(geo_tone)
        desc = "risk_on" if geo_tone > 0.5 else "risk_off" if geo_tone < -0.5 else "neutral"
        signals.append(f"geopolitical: {desc} (tone {geo_tone:.2f})")

    # Fetch macro financial tone
    macro_tone = _fetch_gdelt_tone(" OR ".join(FINANCIAL_MACRO_KEYWORDS[:5]))
    if macro_tone is not None:
        tones.append(macro_tone)
        desc = "positive" if macro_tone > 0.5 else "negative" if macro_tone < -0.5 else "neutral"
        signals.append(f"macro_financial: {desc} (tone {macro_tone:.2f})")

    if not tones:
        return {
            "score": 0.0,
            "confidence": 0.0,
            "signals": ["no GDELT data available"],
            "source": "fallback_neutral",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    avg_tone = sum(tones) / len(tones)
    score = _gdelt_tone_to_score(avg_tone)
    confidence = min(1.0, len(tones) / 2.0)  # Higher confidence with more data points

    return {
        "score": score,
        "confidence": confidence,
        "signals": signals,
        "source": "gdelt_gkg",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Ticker-Specific Sentiment (Yahoo Finance RSS) ──────────────────────

# Simple keyword sentiment lexicon for headline classification
# Used as fallback when no LLM is available
POSITIVE_KEYWORDS = [
    "beat", "beats", "raised", "raises", "upgrade", "upgraded",
    "surge", "surges", "surged", "rally", "rallies", "rallied",
    "jump", "jumps", "jumped", "soar", "soars", "soared",
    "record high", "record profit", "record revenue",
    "strong earnings", "strong revenue", "strong growth",
    "outperform", "outperforms", "outperformed",
    "buyback", "dividend increase", "guidance raise",
    "breakthrough", "breakout", "momentum",
]

NEGATIVE_KEYWORDS = [
    "miss", "misses", "missed", "cut", "cuts", "downgrade", "downgraded",
    "plunge", "plunges", "plunged", "crash", "crashes", "crashed",
    "drop", "drops", "dropped", "sink", "sinks", "sank",
    "decline", "declines", "declined", "fall", "falls", "fell",
    "weak earnings", "weak revenue", "weak guidance",
    "layoff", "layoffs", "restructuring",
    "investigation", "lawsuit", "fine", "penalty",
    "warning", "warns", "recall", "delay",
    "risk", "uncertainty", "volatility",
]


def _classify_headline(headline: str) -> float:
    """Simple keyword-based headline sentiment classification.

    Returns a float in [-1, +1].
    """
    text = headline.lower()
    pos_hits = sum(1 for kw in POSITIVE_KEYWORDS if kw in text)
    neg_hits = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text)

    if pos_hits == 0 and neg_hits == 0:
        return 0.0

    total = pos_hits + neg_hits
    return round((pos_hits - neg_hits) / max(total, 1), 2)


def _fetch_yahoo_headlines(ticker: str, max_items: int = 5) -> list[dict]:
    """Fetch recent headlines for a ticker from Yahoo Finance RSS."""
    url = f"{YAHOO_RSS}?s={ticker}&region=US&lang=en-US"
    text = _http_get(url, timeout=10)
    if not text:
        return []

    try:
        # Clean common XML issues
        text = re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;)', '&amp;', text)

        root = ElementTree.fromstring(text)
        channel = root.find("channel")
        if channel is None:
            return []

        items = []
        for item in channel.findall("item"):
            title_el = item.find("title")
            pub_date_el = item.find("pubDate")
            if title_el is not None and title_el.text:
                headline = title_el.text.strip()
                sentiment = _classify_headline(headline)
                items.append({
                    "headline": headline,
                    "sentiment": sentiment,
                    "published": pub_date_el.text if pub_date_el is not None and pub_date_el.text else None,
                })
                if len(items) >= max_items:
                    break
        return items
    except (ElementTree.ParseError, Exception):
        return []


def fetch_ticker_sentiment(ticker: str) -> dict:
    """Fetch news sentiment for a specific ticker.

    Returns:
      {
        "ticker": str,
        "score": float in [-1, +1],
        "confidence": float in [0, 1],
        "headlines": list[dict],
        "signals": list[str],
        "source": str,
        "fetched_at": "ISO-8601"
      }
    """
    headlines = _fetch_yahoo_headlines(ticker)

    if not headlines:
        return {
            "ticker": ticker.upper(),
            "score": 0.0,
            "confidence": 0.0,
            "headlines": [],
            "signals": ["no headlines available"],
            "source": "fallback_neutral",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    scores = [h["sentiment"] for h in headlines]
    avg_score = sum(scores) / len(scores) if scores else 0.0
    confidence = min(1.0, len(headlines) / 5.0)

    signals = []
    for h in headlines:
        tag = "🟢" if h["sentiment"] > 0 else "🔴" if h["sentiment"] < 0 else "⚪"
        signals.append(f"{tag} {h['headline']}")

    return {
        "ticker": ticker.upper(),
        "score": round(avg_score, 2),
        "confidence": confidence,
        "headlines": headlines,
        "signals": signals,
        "source": "yahoo_finance_rss",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Sector-Level Sentiment ─────────────────────────────────────────────

def _sector_keywords(sector: str) -> list[str]:
    """Map sector to GDELT search keywords."""
    mapping = {
        "Technology": ["semiconductor", "chip maker", "AI technology", "cloud computing", "software IPO"],
        "Financial Services": ["bank earnings", "financial regulation", "fintech", "interest rate bank"],
        "Healthcare": ["drug approval", "biotech", "pharmaceutical", "healthcare policy"],
        "Energy": ["oil price", "OPEC", "crude oil", "energy transition", "natural gas"],
        "Consumer Cyclical": ["retail sales", "consumer spending", "e-commerce"],
        "Consumer Defensive": ["consumer staples", "food prices", "household goods"],
        "Industrials": ["manufacturing", "supply chain", "infrastructure spending"],
        "Communication": ["social media", "streaming", "telecom", "advertising revenue"],
        "Basic Materials": ["commodity prices", "mining", "steel", "chemicals"],
        "Real Estate": ["housing market", "mortgage rates", "commercial real estate", "REIT"],
        "Utilities": ["power grid", "renewable energy", "utility regulation"],
    }
    return mapping.get(sector, [sector.lower()])


def fetch_sector_sentiment(sector: str) -> dict:
    """Fetch news sentiment for a sector via GDELT + keyword fallback.

    Returns:
      {
        "sector": str,
        "score": float in [-1, +1],
        "confidence": float in [0, 1],
        "signals": list[str],
        "source": str,
        "fetched_at": "ISO-8601"
      }
    """
    keywords = _sector_keywords(sector)
    query = " OR ".join(keywords)
    tone = _fetch_gdelt_tone(query)

    if tone is not None:
        score = _gdelt_tone_to_score(tone)
        return {
            "sector": sector,
            "score": score,
            "confidence": 0.7,
            "signals": [f"sector tone: {tone:.2f} → score {score:+.2f}"],
            "source": "gdelt_gkg",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "sector": sector,
        "score": 0.0,
        "confidence": 0.0,
        "signals": ["no sector data available"],
        "source": "fallback_neutral",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Combined Sentiment (ticker + sector + macro) ───────────────────────

def compute_combined(ticker: str, sector: str,
                     macro_weight: float = 0.3,
                     sector_weight: float = 0.3,
                     ticker_weight: float = 0.4) -> dict:
    """Compute combined sentiment from macro, sector, and ticker sources.

    Weights default to: 40% ticker, 30% sector, 30% macro.
    This prioritizes the specific ticker story over broad market noise.

    Returns a full sentiment profile dict.
    """
    macro = fetch_geopolitical_sentiment()
    sec = fetch_sector_sentiment(sector)
    tkr = fetch_ticker_sentiment(ticker)

    total_weight = 0.0
    weighted_score = 0.0
    all_signals = []

    if macro["confidence"] > 0:
        weighted_score += macro["score"] * macro_weight
        total_weight += macro_weight
        all_signals.extend(macro["signals"])

    if sec["confidence"] > 0:
        weighted_score += sec["score"] * sector_weight
        total_weight += sector_weight
        all_signals.extend(sec["signals"])

    if tkr["confidence"] > 0:
        weighted_score += tkr["score"] * ticker_weight
        total_weight += ticker_weight
        all_signals.extend(tkr["signals"])

    if total_weight == 0:
        combined_score = 0.0
        combined_confidence = 0.0
    else:
        combined_score = round(weighted_score / total_weight, 2)
        combined_confidence = round(total_weight / (macro_weight + sector_weight + ticker_weight), 2)

    return {
        "ticker": ticker.upper(),
        "sector": sector,
        "score": combined_score,
        "confidence": combined_confidence,
        "components": {
            "macro": {"score": macro["score"], "confidence": macro["confidence"]},
            "sector": {"score": sec["score"], "confidence": sec["confidence"]},
            "ticker": {"score": tkr["score"], "confidence": tkr["confidence"]},
        },
        "signals": all_signals,
        "headlines": tkr.get("headlines", []),
        "source": "combined",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Main (CLI) ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="News Sentiment extraction for the Agentic Trading Desk")
    parser.add_argument("--json", action="store_true", help="JSON output")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("macro", help="Fetch macro/geopolitical sentiment")
    p_ticker = sub.add_parser("ticker", help="Fetch ticker-specific sentiment")
    p_ticker.add_argument("symbol", help="Ticker symbol")

    p_sector = sub.add_parser("sector", help="Fetch sector-level sentiment")
    p_sector.add_argument("name", help="Sector name (e.g. Technology)")

    p_full = sub.add_parser("full", help="Combined ticker + sector + macro")
    p_full.add_argument("symbol", help="Ticker symbol")
    p_full.add_argument("sector", help="Sector name (or 'auto' to infer)")

    args = parser.parse_args()

    if args.command == "macro":
        result = fetch_geopolitical_sentiment()
    elif args.command == "ticker":
        result = fetch_ticker_sentiment(args.symbol)
    elif args.command == "sector":
        result = fetch_sector_sentiment(args.name)
    elif args.command == "full":
        result = compute_combined(args.symbol, args.sector)
    else:
        parser.print_help()
        sys.exit(1)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Sentiment Score: {result['score']:+.2f}  (confidence: {result['confidence']:.0%})")
        print(f"Source: {result['source']}")
        print()
        sigs = result.get("signals", result.get("components", {}).get("signals", []))
        # Flatten if nested
        if isinstance(result.get("components"), dict):
            sigs = result.get("signals", [])
        for s in sigs:
            print(f"  {s}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
