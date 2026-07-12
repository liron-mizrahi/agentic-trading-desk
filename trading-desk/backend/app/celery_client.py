"""Celery client helper — enqueues tasks to the agent-worker service."""

from __future__ import annotations

from celery import Celery

from app.config import settings

celery_app = Celery(
    "trading_desk_backend",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    broker_transport_options={"visibility_timeout": 3600},
)

# No custom routing — all tasks go to default "celery" queue
