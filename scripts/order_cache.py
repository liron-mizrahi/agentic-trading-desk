#!/usr/bin/env python3
"""
order_cache.py
==============
Order cache for the Agentic Trading Desk.
JSON-based persistent order state machine.

States:
  draft               → Created by the EOD pipeline, not yet reviewed
  pending_confirm     → Sent to user for /confirm
  confirmed           → User confirmed via /confirm; awaiting pre-market check
  sanity_check_ok     → Pre-market check passed; ready for manual execution
  sanity_check_fail   → Pre-market gap > 2%; flagged for reassessment
  ready_for_execution → Final state; flagged as executable
  executed            → User confirmed it was placed (manual ACK)
  cancelled           → Cancelled by user or reassessment

Usage:
  python3 scripts/order_cache.py add        --ticker NVDA --action ENTER --close 120.50 --score +4
  python3 scripts/order_cache.py confirm    ORD-20260710-001
  python3 scripts/order_cache.py list       [--status pending_confirm]
  python3 scripts/order_cache.py get        ORD-20260710-001
  python3 scripts/order_cache.py update     ORD-20260710-001 --status sanity_check_ok
  python3 scripts/order_cache.py cancel     ORD-20260710-001
  python3 scripts/order_cache.py premarket  ORD-20260710-001 --premarket 123.00
  python3 scripts/order_cache.py next-id
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Optional

CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "pending_orders.json"
)

VALID_STATUSES = {
    "draft", "pending_confirm", "confirmed", "sanity_check_ok",
    "sanity_check_fail", "ready_for_execution", "executed", "cancelled"
}

NEXT_ID_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".order_sequence"
)


def _load() -> list[dict]:
    if not os.path.exists(CACHE_PATH):
        return []
    with open(CACHE_PATH) as f:
        data = json.load(f)
    return data.get("orders", [])


def _save(orders: list[dict]):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump({"orders": orders, "updated_at": datetime.now(timezone.utc).isoformat()},
                  f, indent=2)


def _next_sequence() -> int:
    """Get next sequence number for today."""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    seq_file = NEXT_ID_PATH
    seq = 0
    if os.path.exists(seq_file):
        with open(seq_file) as f:
            last_date, last_seq = f.read().strip().split("-")
        if last_date == today:
            seq = int(last_seq)
    seq += 1
    with open(seq_file, "w") as f:
        f.write(f"{today}-{seq:03d}")
    return seq


def generate_order_id() -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    seq = _next_sequence()
    return f"ORD-{today}-{seq:03d}"


def add_order(ticker: str, action: str, close: float, score: int,
              analyst: Optional[dict] = None, risk: Optional[dict] = None,
              pm: Optional[dict] = None, macro_score: Optional[int] = None,
              note: Optional[str] = None) -> dict:
    orders = _load()
    order_id = generate_order_id()

    now = datetime.now(timezone.utc).isoformat()

    order = {
        "id": order_id,
        "ticker": ticker.upper(),
        "action": action,
        "status": "draft",
        "account": "agentic",
        "created_at": now,
        "confirmed_at": None,
        "sanity_checked_at": None,
        "close_price": close,
        "pre_market_price": None,
        "gap_pct": None,
        "score": score,
        "macro_score": macro_score,
        "note": note,
        "analysis": {
            "analyst": analyst or {},
            "risk": risk or {},
            "pm": pm or {},
        },
        "entry": None,
        "cancelled_at": None,
        "executed_at": None,
    }

    orders.append(order)
    _save(orders)
    return order


def get_order(order_id: str) -> Optional[dict]:
    for o in _load():
        if o["id"] == order_id:
            return o
    return None


def list_orders(status: Optional[str] = None) -> list[dict]:
    orders = _load()
    if status:
        if status == "active":
            statuses = {"draft", "pending_confirm", "confirmed",
                        "sanity_check_ok", "ready_for_execution"}
            return [o for o in orders if o["status"] in statuses]
        return [o for o in orders if o["status"] == status]
    return orders


def update_status(order_id: str, new_status: str, **extra) -> bool:
    if new_status not in VALID_STATUSES:
        print(f"Invalid status: {new_status}", file=sys.stderr)
        return False

    orders = _load()
    for o in orders:
        if o["id"] == order_id:
            o["status"] = new_status
            o["updated_at"] = datetime.now(timezone.utc).isoformat()
            for k, v in extra.items():
                if k in o:
                    o[k] = v
            _save(orders)
            return True
    return False


def set_premarket(order_id: str, premarket_price: float) -> Optional[dict]:
    orders = _load()
    for o in orders:
        if o["id"] == order_id:
            o["pre_market_price"] = premarket_price
            close = o.get("close_price")
            if close and close > 0:
                o["gap_pct"] = round((premarket_price - close) / close * 100, 2)
            o["sanity_checked_at"] = datetime.now(timezone.utc).isoformat()
            _save(orders)
            return o
    return None


def update_entry(order_id: str, limit_price: float, quantity: int,
                 stop_loss: Optional[float] = None,
                 take_profit: Optional[float] = None) -> bool:
    orders = _load()
    for o in orders:
        if o["id"] == order_id:
            o["entry"] = {
                "limit_price": limit_price,
                "quantity": quantity,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
            }
            o["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save(orders)
            return True
    return False


def cancel_order(order_id: str) -> bool:
    return update_status(order_id, "cancelled",
                         cancelled_at=datetime.now(timezone.utc).isoformat())


def mark_executed(order_id: str) -> bool:
    return update_status(order_id, "executed",
                         executed_at=datetime.now(timezone.utc).isoformat())


def summary() -> str:
    orders = _load()
    active = [o for o in orders if o["status"] in
              {"draft", "pending_confirm", "confirmed", "sanity_check_ok",
               "ready_for_execution"}]
    if not active:
        return "No active orders."

    lines = [f"Active orders ({len(active)}):"]
    for o in active:
        gap = f" | gap: {o['gap_pct']:+.1f}%" if o.get("gap_pct") is not None else ""
        lines.append(
            f"  {o['id']} | {o['ticker']:6s} | {o['action']:12s} "
            f"| {o['status']:20s} | score {o['score']:+d}/6{gap}"
        )
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description="Order cache for the trading desk")
    sub = p.add_subparsers(dest="cmd")

    # add
    a = sub.add_parser("add", help="Create a new order")
    a.add_argument("--ticker", required=True)
    a.add_argument("--action", required=True, choices=["ENTER", "EXIT", "TRIM", "HOLD", "SKIP"])
    a.add_argument("--close", type=float, required=True)
    a.add_argument("--score", type=int, required=True)
    a.add_argument("--macro", type=int, default=None)
    a.add_argument("--note", default=None)
    a.add_argument("--analyst", type=str, default=None)
    a.add_argument("--risk", type=str, default=None)
    a.add_argument("--pm", type=str, default=None)
    a.add_argument("--json", action="store_true")

    # confirm
    c = sub.add_parser("confirm", help="Mark order as confirmed")
    c.add_argument("order_id", help="Order ID (e.g. ORD-20260710-001)")

    # list
    l = sub.add_parser("list", help="List orders")
    l.add_argument("--status", default=None, choices=list(VALID_STATUSES) + ["active"])
    l.add_argument("--json", action="store_true")

    # get
    g = sub.add_parser("get", help="Get order details")
    g.add_argument("order_id", help="Order ID")
    g.add_argument("--json", action="store_true")

    # update
    u = sub.add_parser("update", help="Update order status")
    u.add_argument("order_id", help="Order ID")
    u.add_argument("--status", required=True, choices=list(VALID_STATUSES))

    # cancel
    x = sub.add_parser("cancel", help="Cancel order")
    x.add_argument("order_id", help="Order ID")

    # premarket
    pm = sub.add_parser("premarket", help="Set pre-market price")
    pm.add_argument("order_id", help="Order ID")
    pm.add_argument("--premarket", type=float, required=True)

    # entry
    e = sub.add_parser("entry", help="Set entry parameters")
    e.add_argument("order_id", help="Order ID")
    e.add_argument("--limit", type=float, required=True)
    e.add_argument("--qty", type=int, required=True)
    e.add_argument("--stop", type=float, default=None)
    e.add_argument("--target", type=float, default=None)

    # next-id
    sub.add_parser("next-id", help="Show the next order ID")

    # summary
    sub.add_parser("summary", help="Show active orders summary")

    # executed
    exe = sub.add_parser("executed", help="Mark order as executed")
    exe.add_argument("order_id", help="Order ID")

    args = p.parse_args()

    if not args.cmd:
        p.print_help()
        return

    # Resolve order_id from parsed args
    order_id = getattr(args, 'order_id', None)

    if args.cmd == "add":
        analyst = json.loads(args.analyst) if args.analyst else None
        risk = json.loads(args.risk) if args.risk else None
        pm = json.loads(args.pm) if args.pm else None
        order = add_order(args.ticker, args.action, args.close, args.score,
                          analyst=analyst, risk=risk, pm=pm,
                          macro_score=args.macro, note=args.note)
        if args.json:
            print(json.dumps(order, indent=2))
        else:
            print(f"Created: {order['id']} | {order['ticker']} | {order['action']} | score {order['score']:+d}/6")

    elif args.cmd == "confirm":
        if not order_id:
            print("Usage: order_cache.py confirm ORDER_ID", file=sys.stderr)
            return
        if update_status(order_id, "confirmed", confirmed_at=datetime.now(timezone.utc).isoformat()):
            print(f"Confirmed: {order_id} → status: confirmed")
        else:
            print(f"Order not found: {order_id}")

    elif args.cmd == "list":
        orders = list_orders(args.status)
        if args.json:
            print(json.dumps(orders, indent=2))
        else:
            for o in orders:
                gap = f" gap:{o['gap_pct']:+.1f}%" if o.get("gap_pct") else ""
                print(f"  {o['id']} | {o['ticker']:6s} | {o['action']:10s} | {o['status']:20s} | ${o['close_price']} | {o['score']:+d}/6{gap}")

    elif args.cmd == "get":
        if not order_id:
            print("Usage: order_cache.py get ORDER_ID", file=sys.stderr)
            return
        o = get_order(order_id)
        if o:
            if args.json:
                print(json.dumps(o, indent=2))
            else:
                for k, v in o.items():
                    print(f"  {k}: {v}")
        else:
            print(f"Not found: {order_id}")

    elif args.cmd == "update":
        if not order_id:
            print("Usage: order_cache.py update ORDER_ID --status STATUS", file=sys.stderr)
            return
        if update_status(order_id, args.status):
            print(f"Updated: {order_id} → {args.status}")
        else:
            print(f"Not found: {order_id}")

    elif args.cmd == "cancel":
        if not order_id:
            print("Usage: order_cache.py cancel ORDER_ID", file=sys.stderr)
            return
        if cancel_order(order_id):
            print(f"Cancelled: {order_id}")
        else:
            print(f"Not found: {order_id}")

    elif args.cmd == "premarket":
        if not order_id:
            print("Usage: order_cache.py premarket ORDER_ID --premarket PRICE", file=sys.stderr)
            return
        o = set_premarket(order_id, args.premarket)
        if o:
            print(f"Pre-market set: {order_id} | close ${o['close_price']} → pre ${args.premarket} | gap {o['gap_pct']:+.1f}%")
        else:
            print(f"Not found: {order_id}")

    elif args.cmd == "entry":
        if not order_id:
            print("Usage: order_cache.py entry ORDER_ID --limit PRICE --qty N [--stop S] [--target T]", file=sys.stderr)
            return
        if update_entry(order_id, args.limit, args.qty, args.stop, args.target):
            print(f"Entry set: {order_id} | limit ${args.limit} x {args.qty}")
        else:
            print(f"Not found: {order_id}")

    elif args.cmd == "next-id":
        print(generate_order_id())

    elif args.cmd == "summary":
        print(summary())

    elif args.cmd == "executed":
        if not order_id:
            print("Usage: order_cache.py executed ORDER_ID", file=sys.stderr)
            return
        if mark_executed(order_id):
            print(f"Marked executed: {order_id}")
        else:
            print(f"Not found: {order_id}")


if __name__ == "__main__":
    main()
