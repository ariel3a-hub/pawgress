from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import notifications
from ..db import get_db
from ..models import EVENT_KINDS, EVENT_LABELS, Dog, Event, utc_to_local
from ..security import CurrentUser, require_group_access
from ..templating import flash_redirect, render

router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/groups/{group_id}/events")
def event_timeline(
    request: Request, db: DbSession, user: CurrentUser, group_id: int, dog_id: int | None = None
):
    group, membership = require_group_access(db, user, group_id)
    dogs = db.scalars(
        select(Dog).where(Dog.group_id == group.id).order_by(Dog.name)
    ).all()

    selected_dog: Dog | None = None
    if dog_id is not None:
        selected_dog = next((dog for dog in dogs if dog.id == dog_id), None)
        if selected_dog is None:
            raise HTTPException(status_code=404, detail="That dog is not in this group")

    events = db.scalars(
        select(Event)
        .where(Event.dog_id.in_([dog.id for dog in dogs] or [0]))
        .order_by(Event.created_at.desc(), Event.id.desc())
        .limit(300)
    ).all()

    days: list[tuple[str, list[Event]]] = []
    for event in events:
        if selected_dog is not None and event.dog_id != selected_dog.id:
            continue
        local_time = utc_to_local(event.created_at)
        day = local_time.strftime("%A, %d %B %Y")
        if not days or days[-1][0] != day:
            days.append((day, []))
        days[-1][1].append(event)

    return render(
        request,
        "events/timeline.html",
        db,
        user=user,
        group=group,
        membership=membership,
        dogs=dogs,
        selected_dog=selected_dog,
        days=days,
        event_labels=EVENT_LABELS,
    )


@router.get("/groups/{group_id}/events/new")
def new_event_page(
    request: Request, db: DbSession, user: CurrentUser, group_id: int, dog_id: int | None = None
):
    group, membership = require_group_access(db, user, group_id)
    dogs = db.scalars(
        select(Dog).where(Dog.group_id == group.id).order_by(Dog.name)
    ).all()

    selected_dog: Dog | None = None
    if dog_id is not None:
        selected_dog = next((dog for dog in dogs if dog.id == dog_id), None)
        if selected_dog is None:
            selected_dog = dogs[0] if dogs else None

    return render(
        request,
        "events/new.html",
        db,
        user=user,
        group=group,
        membership=membership,
        dogs=dogs,
        selected_dog=selected_dog,
        event_kinds=EVENT_KINDS,
        event_labels=EVENT_LABELS,
    )


@router.post("/groups/{group_id}/events")
def create_event(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    group_id: int,
    dog_id: int = Form(),
    kind: str = Form(),
    note: str = Form(""),
):
    group, _ = require_group_access(db, user, group_id)
    dog = db.scalar(select(Dog).where(Dog.id == dog_id, Dog.group_id == group.id))
    if dog is None:
        raise HTTPException(status_code=404, detail="That dog is not in this group")
    if kind not in EVENT_KINDS:
        raise HTTPException(status_code=400, detail="Unknown event type")

    event = Event(
        dog_id=dog.id,
        user_id=user.id,
        kind=kind,
        note=note.strip()[:500] or None,
    )
    db.add(event)
    db.commit()

    notifications.notify_new_event(db, group, dog, kind, user)

    return flash_redirect(
        request,
        f"/groups/{group.id}/events?dog_id={dog.id}",
        f"{EVENT_LABELS[kind]} {dog.name} with {user.username} added.",
    )