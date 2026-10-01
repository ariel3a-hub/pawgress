from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import notifications, push
from ..db import get_db
from ..models import PushSubscription
from ..security import CurrentUser

router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class SubscriptionPayload(BaseModel):
    endpoint: str = Field(min_length=8, max_length=512)
    keys: dict[str, str]

    @property
    def p256dh(self) -> str:
        return self.keys.get("p256dh", "")

    @property
    def auth(self) -> str:
        return self.keys.get("auth", "")


@router.get("/api/notifications/unread-count")
def unread_count(request: Request, db: DbSession, user: CurrentUser):
    return {"count": notifications.unread_count(db, user.id)}


@router.get("/api/push/key")
def push_key():
    return {"public_key": push.public_key_urlsafe()}


@router.post("/api/push/subscribe")
def subscribe(request: Request, db: DbSession, user: CurrentUser, payload: SubscriptionPayload):
    if not payload.p256dh or not payload.auth:
        raise HTTPException(status_code=400, detail="Subscription keys are missing.")

    existing = db.scalar(
        select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint)
    )
    if existing is not None:
        existing.user_id = user.id
        existing.p256dh = payload.p256dh
        existing.auth = payload.auth
        existing.user_agent = request.headers.get("user-agent")
    else:
        db.add(
            PushSubscription(
                user_id=user.id,
                endpoint=payload.endpoint,
                p256dh=payload.p256dh,
                auth=payload.auth,
                user_agent=request.headers.get("user-agent"),
            )
        )
    db.commit()
    return {"status": "subscribed"}


@router.post("/api/push/unsubscribe")
def unsubscribe(request: Request, db: DbSession, user: CurrentUser, payload: SubscriptionPayload):
    subscription = db.scalar(
        select(PushSubscription).where(
            PushSubscription.endpoint == payload.endpoint,
            PushSubscription.user_id == user.id,
        )
    )
    if subscription is not None:
        db.delete(subscription)
        db.commit()
    return {"status": "unsubscribed"}


@router.get("/sw.js")
def service_worker():
    return FileResponse(
        STATIC_DIR / "sw.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
    )