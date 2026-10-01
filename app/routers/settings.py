from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .. import notifications
from ..db import get_db
from ..models import EVENT_KINDS, EVENT_LABELS, Notification
from ..security import CurrentUser
from ..templating import flash_redirect, render

router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/settings")
def settings_page(request: Request, db: DbSession, user: CurrentUser):
    preference = notifications.get_or_create_preference(db, user)
    return render(
        request,
        "settings/index.html",
        db,
        user=user,
        preference=preference,
        event_kinds=EVENT_KINDS,
        event_labels=EVENT_LABELS,
    )


@router.post("/settings/notifications")
def save_notifications(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    new_events_enabled: str = Form(""),
    group_reminders_enabled: str = Form(""),
    web_push_enabled: str = Form(""),
    kinds: Annotated[list[str], Form()] = (),
):
    preference = notifications.get_or_create_preference(db, user)
    selected = [kind for kind in kinds if kind in EVENT_KINDS]
    if not selected:
        selected = list(EVENT_KINDS)

    preference.new_events_enabled = new_events_enabled == "on"
    preference.group_reminders_enabled = group_reminders_enabled == "on"
    preference.web_push_enabled = web_push_enabled == "on"
    preference.event_kinds = selected
    db.commit()

    return flash_redirect(request, "/settings", "Notification settings saved.")


@router.get("/notifications")
def notifications_page(request: Request, db: DbSession, user: CurrentUser):
    items = db.scalars(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(200)
    ).all()
    for item in items:
        if not item.is_read:
            item.is_read = True
    db.commit()
    return render(
        request, "notifications/index.html", db, user=user, notifications=items
    )


@router.post("/notifications/read-all")
def mark_all_read(request: Request, db: DbSession, user: CurrentUser):
    db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    db.commit()
    return flash_redirect(request, "/notifications", "All notifications marked as read.")