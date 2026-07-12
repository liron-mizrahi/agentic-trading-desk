#!/usr/bin/env python3
"""
eod_pipeline.py
===============
End-of-Day pipeline for the Agentic Trading Desk.
Orchestrates the full pipeline:

  Step 1 — Screener:  filter universe by macro bias + sector focus
  Step 2 — Metrics:   score candidates through three-pillar engine
  Step 3 — Review:    persona chain (analyst → risk → portfolio manager)
                      → DB persistence for pipeline history
  Step 4 — Orders:    optional order cache entries

Results are stored in the trades table (strategy="three_pillar") for
historical pipeline review on the Pipelines UI page.

Usage:
  python3 scripts/eod_pipeline.py
  python3 scripts/eod_pipeline.py --sectors Technology,Healthcare
  python3 scripts/eod_pipeline.py --dry-run
  python3 scripts/eod_pipeline.py --json
"""

import argparse
import json
import math
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(SCRIPT_DIR)


def _run(cmd: list, desc: str = "") -> tuple[bool, str]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=WORKSPACE)
        if result.returncode == 0:
            return True, result.stdout
        return False, result.stderr
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except FileNotFoundError as e:
        return False, str(e)


# ── DB persistence ───────────────────────────────────────────────────

def _save_pipeline_results(analyzed: list[dict], proposals: list[dict]) -> int:
    """Persist three-pillar analysis results to the trades table.
    
    Each analyzed candidate gets a Trade row with strategy="three_pillar".
    Returns number of rows written.
    """
    try:
        import psycopg2
        import psycopg2.extras
        
        db_url = os.environ.get(
            "DATABASE_URL",
            "postgresql://admin:tradingdesk@localhost:5432/trading_desk"
        )
        
        conn = psycopg2.connect(db_url)
        conn.autocommit = False
        cur = conn.cursor()
        
        # Set up: insert UUID extension if needed
        cur.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
        
        written = 0
        proposal_map = {p["ticker"]: p for p in proposals}
        
        for c in analyzed:
            ticker = c.get("ticker", "?")
            a = c.get("analysis", {})
            decision_data = a.get("decision", {})
            pillars = a.get("pillars", {})
            indicators = a.get("indicators", {})
            prop = proposal_map.get(ticker, {})
            
            # Extract pillar scores
            trend = pillars.get("trend", {})
            momentum = pillars.get("momentum", {})
            macro = pillars.get("macro_sentiment", {})
            
            action = decision_data.get("action", "OBSERVE")
            rationale = decision_data.get("rationale", "")[:2000]
            framing = decision_data.get("framing", "")[:500]
            
            # Map action to decision
            decision = None
            if "RE-ENTRY" in action or "TACTICAL" in action:
                decision = "BUY"
            elif action.startswith("WAIT") or action.startswith("OBSERVE"):
                decision = "NO_TRADE"
            elif action.startswith("HOLD"):
                decision = "HOLD"
            elif "EXIT" in action:
                decision = "EXIT"
            else:
                decision = "NO_TRADE"
            
            close = indicators.get("close", 0)
            sector = c.get("sector", "Unclassified")
            score = c.get("score", 0)
            
            # Store technical data as JSONB with indicator snapshot for dashboard
            # Filter out NaN values (JSONB doesn't support NaN)
            def _clean(v):
                if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    return None
                return v
            
            technical_data = json.dumps({
                "trend_score": trend.get("score"),
                "trend_detail": trend.get("detail", ""),
                "momentum_score": momentum.get("score"),
                "momentum_detail": momentum.get("detail", ""),
                "macro_score": macro.get("score"),
                "macro_detail": macro.get("detail", ""),
                "pillar_total": a.get("pillar_total"),
                "close": close,
                "sector": sector,
                "framing": framing,
                # Raw technicals for frontend three-pillar display
                "rsi14": _clean(indicators.get("rsi14")),
                "macd_hist": _clean(indicators.get("macd_hist")),
                "trix": _clean(indicators.get("trix")),
                "trix_signal": _clean(indicators.get("trix_signal")),
                "ema20": _clean(indicators.get("ema20")),
                "ema50": _clean(indicators.get("ema50")),
                "ema200": _clean(indicators.get("ema200")),
                "percent_b": _clean(indicators.get("percent_b")),
            })
            
            try:
                cur.execute("""
                    INSERT INTO trades (
                        id, ticker, strategy, decision, confidence,
                        reasoning, proposed_price, position_size_pct,
                        exit_condition, stop_loss, take_profit,
                        status, sector,
                        rsi_2_value, chop_value, sma_200_value,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, 'three_pillar', %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        'PENDING', %s,
                        %s, %s, %s,
                        %s, %s
                    )
                """, (
                    str(uuid.uuid4()),
                    ticker,
                    decision,
                    None,  # confidence — set if BUY
                    rationale,
                    close if close else None,
                    None,  # position_size_pct
                    None,  # exit_condition
                    None,  # stop_loss
                    None,  # take_profit
                    sector,
                    None,  # rsi_2_value
                    None,  # chop_value
                    None,  # sma_200_value
                    datetime.now(timezone.utc),
                    datetime.now(timezone.utc),
                ))
                
                # Also insert an analysis log for pipeline step tracking
                # Get the inserted trade's ID
                cur.execute(
                    "SELECT id FROM trades WHERE ticker = %s AND strategy = 'three_pillar' ORDER BY created_at DESC LIMIT 1",
                    (ticker,)
                )
                row = cur.fetchone()
                trade_id = row[0] if row else None
                
                if trade_id:
                    cur.execute("""
                        INSERT INTO analysis_logs (
                            id, trade_id, ticker,
                            step1_passed, step2_passed, step3_passed,
                            price, technical_data,
                            llm_decision, llm_confidence,
                            raw_llm_reasoning, retry_count, dead_letter,
                            created_at, updated_at
                        ) VALUES (
                            %s, %s, %s,
                            %s, %s, %s,
                            %s, %s,
                            %s, %s,
                            %s, %s, %s,
                            %s, %s
                        )
                    """, (
                        str(uuid.uuid4()),
                        trade_id,
                        ticker,
                        trend.get("score", 0) is not None and trend.get("score", 0) >= 0,
                        momentum.get("score", 0) is not None and momentum.get("score", 0) >= 0,
                        macro.get("score", 0) is not None and macro.get("score", 0) >= 0,
                        close if close else None,
                        technical_data,
                        decision,
                        None,
                        rationale[:2000],
                        0,
                        False,
                        datetime.now(timezone.utc),
                        datetime.now(timezone.utc),
                    ))
                
                written += 1
            except Exception as exc:
                print(f"    ⚠ DB write failed for {ticker}: {exc}")
                conn.rollback()
                # Restart a fresh transaction for subsequent rows
                conn.autocommit = False
        
        conn.commit()
        cur.close()
        conn.close()
        print(f"\n  💾 Persisted {written} results to trades table (strategy=three_pillar)")
        return written
        
    except ImportError:
        print("  ⚠ psycopg2 not available, skipping DB persistence")
        return 0
    except Exception as exc:
        print(f"  ⚠ DB persistence failed: {exc}")
        return 0


# ── Step 1: Screener ──────────────────────────────────────────────────

def step1_screener(sector_focus: list[str] | None, dry_run: bool) -> dict:
    print("─── Step 1: Screener ───", flush=True)

    ok, out = _run(
        [sys.executable, "scripts/ibkr_webapi.py", "macro-etfs"],
        "Fetch macro ETFs"
    )
    if not ok:
        print(f"  ❌ Macro data refresh failed: {out[:200]}")

    ok2, out2 = _run(
        [sys.executable, "scripts/yield_spread.py", "--history", "60", "--json"],
        "Fetch yield spread"
    )
    if ok2:
        try:
            spread = json.loads(out2)
            print(f"  ✅ Yield spread: {spread.get('latest_raw', {}).get('spread', '?')}bps")
        except json.JSONDecodeError:
            print("  ⚠ Yield spread parse error")

    screener_cmd = [sys.executable, "scripts/screener.py", "--score", "--limit", "15"]
    if not ok or not ok2:
        screener_cmd.append("--refresh")
    if sector_focus:
        screener_cmd += ["--sectors", ",".join(sector_focus)]

    ok3, out3 = _run(screener_cmd, "Run screener")
    if not ok3:
        print(f"  ❌ Screener failed: {out3[:300]}")
        return {"error": out3, "candidates": []}

    print(out3)

    candidates = []
    for line in out3.split("\n"):
        parts = line.strip().split("|")
        if len(parts) >= 3 and "/6" in parts[1]:
            ticker = parts[0].strip()
            try:
                score = int(parts[1].strip().split("/")[0])
            except ValueError:
                score = 0
            decision = parts[2].strip() if len(parts) > 2 else "?"
            sector = parts[3].strip() if len(parts) > 3 else "?"
            candidates.append({"ticker": ticker, "score": score, "decision": decision, "sector": sector})

    if not candidates:
        json_cmd = [sys.executable, "scripts/screener.py", "--score", "--limit", "15", "--json"]
        if sector_focus:
            json_cmd += ["--sectors", ",".join(sector_focus)]
        ok4, out4 = _run(json_cmd, "Run screener (JSON)")
        if ok4:
            try:
                data = json.loads(out4)
                for sc in data.get("scored", []):
                    sym = sc.get("symbol", "?")
                    sc_card = sc.get("scorecard", {})
                    score = sc_card.get("pillar_total", 0)
                    decision = sc_card.get("decision", {}).get("action", "?")
                    candidates.append({
                        "ticker": sym, "score": score,
                        "decision": decision,
                        "sector": sc.get("sector", "?"),
                        "scorecard": sc_card,
                    })
            except json.JSONDecodeError:
                pass

    print(f"\n  → {len(candidates)} candidates scored")
    return {"candidates": candidates}


# ── Step 2: Analyze ───────────────────────────────────────────────────

def step2_analyze(candidates: list[dict]) -> list[dict]:
    print("\n─── Step 2: Metric Layer + Cognitive Review ───", flush=True)

    enriched = []
    for c in candidates:
        ticker = c["ticker"]
        print(f"\n  📊 Analyzing {ticker} (score {c.get('score', 0):+d})...", end=" ", flush=True)

        ok, out = _run(
            [sys.executable, "scripts/analyze.py", ticker, "--json"],
            f"Analyze {ticker}"
        )
        if ok:
            try:
                analysis = json.loads(out)
                c["analysis"] = analysis
                print(f"✅  {analysis.get('decision', {}).get('action', '?')}")
                enriched.append(c)
            except json.JSONDecodeError:
                print("❌ parse error")
        else:
            print(f"❌ {out[:100]}")

    return enriched


# ── Step 3: Propose ───────────────────────────────────────────────────

def step3_propose(analyzed: list[dict]) -> list[dict]:
    print("\n─── Step 3: Order Proposals ───", flush=True)

    proposals = []
    for c in analyzed:
        a = c.get("analysis", {})
        decision = a.get("decision", {})
        action = decision.get("action", "OBSERVE")
        ticker = c["ticker"]
        score = c.get("score", 0)
        indicators = a.get("indicators", {})
        close = indicators.get("close", 0)

        if "RE-ENTRY" in action or "TACTICAL" in action:
            prop_action = "ENTER"
        elif "EXIT" in action and "RIDE" not in action:
            prop_action = "EXIT"
        elif action.startswith("WAIT") or action.startswith("STAY") or action.startswith("OBSERVE"):
            prop_action = "SKIP"
        elif action.startswith("HOLD"):
            prop_action = "HOLD"
        else:
            prop_action = "SKIP"

        if prop_action == "SKIP":
            continue

        proposals.append({
            "ticker": ticker,
            "action": prop_action,
            "close": close,
            "score": score,
            "decision": action,
            "rationale": decision.get("rationale", ""),
            "framing": decision.get("framing", ""),
            "analysis": a,
        })

        print(f"  {ticker}: {prop_action:6s} | score {score:+d}/6 | close ${close:.2f}")

    return proposals


def store_orders(proposals: list[dict], dry_run: bool) -> list[dict]:
    orders = []
    for p in proposals:
        if p["action"] in ("ENTER", "EXIT", "TRIM"):
            cmd = [
                sys.executable, "scripts/order_cache.py", "add",
                "--ticker", p["ticker"],
                "--action", p["action"],
                "--close", str(p["close"]),
                "--score", str(p["score"]),
            ]
            cmd += ["--note", f"EOD {datetime.now(timezone.utc).strftime('%Y-%m-%d')}: {p['rationale']}"]

            if dry_run:
                print(f"  [DRY RUN] Would create order: {p['ticker']} {p['action']}")
                continue

            ok, out = _run(cmd, f"Cache order {p['ticker']}")
            if ok:
                for line in out.split("\n"):
                    if line.startswith("Created:"):
                        order_id = line.split("|")[0].replace("Created:", "").strip()
                        p["order_id"] = order_id
                        orders.append(p)
                        _run(
                            [sys.executable, "scripts/order_cache.py", "update", order_id,
                             "--status", "pending_confirm"],
                            f"Mark {order_id} pending_confirm"
                        )
                        print(f"    ✅ Order {order_id} created → pending_confirm")
            else:
                print(f"    ❌ Failed: {out[:100]}")

    return orders


def output_summary(proposals: list[dict], orders: list[dict], dry_run: bool, db_count: int = 0):
    print("\n" + "=" * 60)
    print("  📋 EOD PIPELINE SUMMARY")
    print("=" * 60)
    print(f"  Date:       {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Proposals:  {len(proposals)}")
    print(f"  Orders:     {len(orders)}")
    if db_count:
        print(f"  DB writes:  {db_count} results persisted")
    if dry_run:
        print("  Mode:       DRY RUN (no orders cached)")
    print("─" * 60)

    for p in proposals:
        oid = p.get("order_id", "—")
        if p["action"] in ("ENTER", "EXIT", "TRIM"):
            print(f"\n  ▶ {p['ticker']}")
            print(f"    Action:   {p['action']}")
            print(f"    Score:    {p['score']:+d}/6")
            print(f"    Price:    ${p['close']:.2f}")
            print(f"    Order:    {oid}")
            print(f"    Framing:  {p['framing'][:120]}")

    if not proposals:
        print("\n  No actionable proposals today.")
    print("=" * 60)


def main():
    p = argparse.ArgumentParser(description="EOD Pipeline for Agentic Trading Desk")
    p.add_argument("--sectors", type=str, default=None)
    p.add_argument("--all-sectors", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-cache", action="store_true")

    args = p.parse_args()

    sector_focus = None
    if args.all_sectors:
        sector_focus = None
    elif args.sectors:
        sector_focus = [s.strip() for s in args.sectors.split(",")]
    else:
        sector_focus = ["Technology"]

    print(f"Agentic Trading Desk — EOD Pipeline")
    print(f"  Run:       {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Sectors:   {', '.join(sector_focus) if sector_focus else 'ALL'}")
    print(f"  Mode:      {'DRY RUN' if args.dry_run else 'LIVE'}")

    screen = step1_screener(sector_focus, args.dry_run)
    if "error" in screen:
        print(f"\n❌ Pipeline failed: {screen['error']}")
        sys.exit(1)

    candidates = screen.get("candidates", [])
    if not candidates:
        if args.json:
            print(json.dumps({"status": "no_candidates", "timestamp": datetime.now(timezone.utc).isoformat()}))
        else:
            print("\n  No candidates passed the screener today.")
        return

    analyzed = step2_analyze(candidates)
    proposals = step3_propose(analyzed)

    # Persist ALL analyzed results to DB for pipeline history page
    db_count = _save_pipeline_results(analyzed, proposals)

    if not args.no_cache:
        orders = store_orders(proposals, args.dry_run)
    else:
        orders = []

    if args.json:
        result = {
            "status": "complete",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sectors": sector_focus,
            "candidates": len(candidates),
            "analyzed": len(analyzed),
            "proposals": [{"ticker": p["ticker"], "action": p["action"], "score": p["score"], "close": p["close"]} for p in proposals],
            "db_persisted": db_count,
        }
        print(json.dumps(result, indent=2))
    else:
        output_summary(proposals, orders, args.dry_run, db_count)


if __name__ == "__main__":
    main()
