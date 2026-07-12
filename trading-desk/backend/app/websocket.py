"""WebSocket connection manager with Redis Pub/Sub bridge.

Forwards agent-layer events (published to Redis "trading_events") to all
connected WebSocket clients using consistent event types:
  NEW_TRADE, TRADE_UPDATED, SYSTEM_WARNING, CONNECTION_OK
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import redis.asyncio as aioredis
from fastapi import WebSocket

from app.config import settings

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._redis: aioredis.Redis | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)
        logger.info("WS client connected (%d total)", len(self._connections))

    async def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)
        logger.info("WS client disconnected (%d remaining)", len(self._connections))

    async def broadcast(self, event: dict[str, Any]) -> None:
        """Send JSON event to all connected clients."""
        stale: set[WebSocket] = set()
        message = json.dumps(event, default=str)

        for ws in self._connections:
            try:
                await ws.send_text(message)
            except Exception:
                stale.add(ws)

        for ws in stale:
            self._connections.discard(ws)

    async def start_redis_listener(self) -> None:
        """Subscribe to Redis trading_events and forward to WS clients."""
        try:
            self._redis = aioredis.from_url(settings.REDIS_URL)
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(settings.REDIS_EVENT_CHANNEL)
            logger.info("Subscribed to Redis channel '%s'", settings.REDIS_EVENT_CHANNEL)

            async for message in pubsub.listen():
                if self._stop.is_set():
                    break
                if message.get("type") != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                    # Normalise event types from agent layer
                    agent_type = data.get("type", "")
                    if agent_type == "NEW_PROPOSAL":
                        data["event"] = "NEW_TRADE"
                    elif agent_type == "TRADE_EXECUTED":
                        data["event"] = "TRADE_UPDATED"
                    elif agent_type.startswith("System"):
                        data["event"] = "SYSTEM_WARNING"
                    else:
                        data["event"] = agent_type
                    await self.broadcast(data)
                except (json.JSONDecodeError, TypeError):
                    logger.warning("Non-JSON Redis message skipped")
                    continue
        except asyncio.CancelledError:
            logger.info("Redis listener cancelled.")
        except Exception:
            logger.exception("Redis listener error — restarting in 5s")
            await asyncio.sleep(5)
            if not self._stop.is_set():
                self._task = asyncio.create_task(self.start_redis_listener())
        finally:
            if self._redis:
                try:
                    await self._redis.close()
                except Exception:
                    pass

    async def stop_redis_listener(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Redis listener stopped.")

    async def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self.start_redis_listener())


ws_manager = ConnectionManager()
