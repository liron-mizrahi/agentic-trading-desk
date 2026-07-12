"""AI Trading Desk — FastAPI application entry point.

Central nervous system of the platform:
  - Routes REST API requests from the frontend
  - Manages WebSocket connections for real-time event streaming
  - Dispatches heavy analytical workloads to the Celery task queue
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import close_db, init_db
from app.routers import analysis, trades, data, pipelines, fundamentals
from app.websocket import ws_manager

# ── Logging ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lifespan (startup / shutdown) ─────────────────────────
@asynccontextmanager
async def lifespan(application: FastAPI) -> Any:
    """Handle application startup and shutdown cleanly."""
    # ── Startup ──
    logger.info("Starting AI Trading Desk backend...")
    await init_db()
    await ws_manager.start()
    logger.info("Backend ready — listening on %s:%s", settings.HOST, settings.PORT)
    yield
    # ── Shutdown ──
    logger.info("Shutting down AI Trading Desk backend...")
    await ws_manager.stop_redis_listener()
    await close_db()
    logger.info("Shutdown complete.")


# ── FastAPI app ───────────────────────────────────────────
app = FastAPI(
    title="AI Trading Desk API",
    description="Backend API for the AI-powered Trading Desk platform.",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS (allow all origins for development) ──────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

# ── Include routers ───────────────────────────────────────
app.include_router(trades.router)
app.include_router(pipelines.router)
app.include_router(analysis.router)
app.include_router(data.router)
app.include_router(fundamentals.router)


# ── Health check ──────────────────────────────────────────
@app.get("/", tags=["health"])
async def health_check() -> dict[str, Any]:
    """Simple health-check endpoint."""
    return {
        "service": "ai-trading-desk-backend",
        "status": "ok",
        "version": "0.1.0",
    }


# ── WebSocket endpoint ────────────────────────────────────
@app.websocket("/ws/notifications")
async def websocket_notifications(websocket: WebSocket) -> None:
    """Live event stream for connected clients.

    Events pushed by the server:
      - NEW_TRADE       — A new trade proposal was created by an agent
      - TRADE_UPDATED   — An existing trade's status changed
      - SYSTEM_WARNING  — Non-critical operational alert
      - CONNECTION_OK   — Periodic keepalive confirmation

    The server also forwards events received via Redis Pub/Sub
    from the agent layer (e.g., agent analyses, execution results).
    """
    await ws_manager.connect(websocket)
    try:
        # Send immediate connection confirmation
        await websocket.send_json({
            "event": "CONNECTION_OK",
            "message": "Connected to AI Trading Desk event stream.",
        })

        # Keep the connection alive by reading (client may send pings)
        while True:
            try:
                data = await websocket.receive_text()
                # Client may send a ping; acknowledge with CONNECTION_OK
                if data.strip().lower() == "ping":
                    await websocket.send_json({
                        "event": "CONNECTION_OK",
                        "message": "ack",
                    })
            except WebSocketDisconnect:
                break
    except Exception:
        logger.exception("WebSocket error")
    finally:
        await ws_manager.disconnect(websocket)
