from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import notifications
from ..db import get_db
from ..models import (
    ROLE_MEMBER,
    ROLE_OWNER,
    Dog,
    Event,
    Group,
    Membership,
    Reminder,
    local_wallclock_to_utc,
    utcnow,
)
from ..security import (
    CurrentUser,
    generate_join_code,
    normalize_join_code,
    require_group_access,
    require_group_owner,
)
from ..templating import flash_redirect, render

router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]


def _unique_join_code(db: Session) -> str:
    for _ in range(10):
        code = generate_join_code()
        if db.scalar(select(Group.id).where(Group.join_code == code)) is None:
            return code
    raise HTTPException(status_code=500, detail="Could not allocate a join code")


@router.get("/groups")
def list_groups(request: Request, db: DbSession, user: CurrentUser):
    groups = db.scalars(
        select(Group)
        .join(Membership, Membership.group_id == Group.id)
        .where(Membership.user_id == user.id)
        .order_by(Group.name)
    ).all()
    roles = {
        membership.group_id: membership.role
        for membership in db.scalars(
            select(Membership).where(Membership.user_id == user.id)
        ).all()
    }
    return render(
        request,
        "groups/index.html",
        db,
        user=user,
        groups=groups,
        roles=roles,
        form={},
        join_form={},
    )


@router.post("/groups")
def create_group(request: Request, db: DbSession, user: CurrentUser, name: str = Form("")):
    clean = name.strip()[:80]
    if not clean:
        return flash_redirect(request, "/groups", "A group needs a name.", "error")

    group = Group(name=clean, join_code=_unique_join_code(db), owner_id=user.id)
    db.add(group)
    db.flush()
    db.add(Membership(user_id=user.id, group_id=group.id, role=ROLE_OWNER))
    db.commit()
    return flash_redirect(
        request, f"/groups/{group.id}", f'Group "{group.name}" created. You are the owner.'
    )


@router.post("/groups/join")
def join_group(request: Request, db: DbSession, user: CurrentUser, code: str = Form("")):
    clean = normalize_join_code(code)
    group = db.scalar(select(Group).where(Group.join_code == clean))
    if group is None:
        return flash_redirect(request, "/groups", "No group matches that code.", "error")

    existing = db.scalar(
        select(Membership).where(
            Membership.user_id == user.id, Membership.group_id == group.id
        )
    )
    if existing is not None:
        return flash_redirect(
            request, f"/groups/{group.id}", f'You are already in "{group.name}".'
        )

    db.add(Membership(user_id=user.id, group_id=group.id, role=ROLE_MEMBER))
    db.commit()
    return flash_redirect(request, f"/groups/{group.id}", f'You joined "{group.name}".')


@router.get("/groups/{group_id}")
def group_detail(request: Request, db: DbSession, user: CurrentUser, group_id: int):
    group, membership = require_group_access(db, user, group_id)
    members = db.scalars(
        select(Membership)
        .where(Membership.group_id == group.id)
        .order_by(Membership.role.desc(), Membership.joined_at)
    ).all()
    dogs = db.scalars(
        select(Dog).where(Dog.group_id == group.id).order_by(Dog.name)
    ).all()
    reminders = db.scalars(
        select(Reminder)
        .where(Reminder.group_id == group.id)
        .order_by(Reminder.scheduled_for.desc())
    ).all()
    last_events = {
        dog_id: created_at
        for dog_id, created_at in db.execute(
            select(Event.dog_id, func.max(Event.created_at)).where(
                Event.dog_id.in_([dog.id for dog in dogs] or [0])
            ).group_by(Event.dog_id)
        ).all()
    }
    return render(
        request,
        "groups/detail.html",
        db,
        user=user,
        group=group,
        membership=membership,
        is_owner=membership.role == ROLE_OWNER,
        members=members,
        dogs=dogs,
        reminders=reminders,
        last_events=last_events,
        reminder_form={},
        now=utcnow(),
    )


@router.post("/groups/{group_id}/transfer")
def transfer_ownership(
    request: Request, db: DbSession, user: CurrentUser, group_id: int, member_id: int = Form()
):
    group, _ = require_group_owner(db, user, group_id)
    target = db.scalar(
        select(Membership).where(
            Membership.id == member_id, Membership.group_id == group.id
        )
    )
    if target is None:
        return flash_redirect(
            request, f"/groups/{group.id}", "That member is not in this group.", "error"
        )
    if target.user_id == user.id:
        return flash_redirect(request, f"/groups/{group.id}", "You already own this group.")

    for membership in db.scalars(
        select(Membership).where(Membership.group_id == group.id)
    ).all():
        membership.role = ROLE_MEMBER
    target.role = ROLE_OWNER
    group.owner_id = target.user_id
    db.commit()
    return flash_redirect(
        request,
        f"/groups/{group.id}",
        f"Ownership transferred to {target.user.username}.",
    )


@router.post("/groups/{group_id}/leave")
def leave_group(request: Request, db: DbSession, user: CurrentUser, group_id: int):
    group, membership = require_group_access(db, user, group_id)
    if group.owner_id == user.id:
        remaining = db.scalars(
            select(Membership).where(
                Membership.group_id == group.id, Membership.user_id != user.id
            )
        ).all()
        if remaining:
            heir = remaining[0]
            heir.role = ROLE_OWNER
            group.owner_id = heir.user_id
        else:
            db.delete(group)
            db.commit()
            return flash_redirect(request, "/groups", f'You deleted "{group.name}".')

    db.delete(membership)
    db.commit()
    return flash_redirect(request, "/groups", f'You left "{group.name}".')


@router.post("/groups/{group_id}/reminders")
def create_reminder(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    group_id: int,
    title: str = Form(""),
    body: str = Form(""),
    scheduled_for: str = Form(""),
):
    group, _ = require_group_access(db, user, group_id)
    clean_title = title.strip()[:120]
    if not clean_title:
        return flash_redirect(
            request, f"/groups/{group.id}", "The reminder needs a title.", "error"
        )

    try:
        when = local_wallclock_to_utc(datetime.fromisoformat(scheduled_for))
    except ValueError:
        return flash_redirect(
            request, f"/groups/{group.id}", "Pick a valid date and time for the reminder.", "error"
        )

    reminder = Reminder(
        group_id=group.id,
        created_by=user.id,
        title=clean_title,
        body=body.strip()[:400],
        scheduled_for=when,
    )
    db.add(reminder)
    db.commit()

    if when <= utcnow():
        notifications.notify_group_reminder(db, group, reminder)
        reminder.sent_at = utcnow()
        db.commit()
        return flash_redirect(
            request, f"/groups/{group.id}", "Reminder sent to everyone in the group."
        )
    return flash_redirect(
        request, f"/groups/{group.id}", "Reminder scheduled for the whole group."
    )


@router.post("/reminders/{reminder_id}/delete")
def delete_reminder(
    request: Request, db: DbSession, user: CurrentUser, reminder_id: int
):
    reminder = db.get(Reminder, reminder_id)
    if reminder is None:
        raise HTTPException(status_code=404, detail="Reminder not found")
    _, membership = require_group_access(db, user, reminder.group_id)
    if membership.role != ROLE_OWNER and reminder.created_by != user.id:
        raise HTTPException(status_code=403, detail="You cannot delete this reminder")
    db.delete(reminder)
    db.commit()
    return flash_redirect(
        request, f"/groups/{reminder.group_id}", "Reminder deleted."
    )