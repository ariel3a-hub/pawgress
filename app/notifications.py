from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import push
from .models import (
    EVENT_KINDS,
    NOTIFY_GROUP_REMINDER,
    NOTIFY_NEW_EVENT,
    Dog,
    Group,
    Membership,
    Notification,
    NotificationPreference,
    PushSubscription,
    Reminder,
    User,
    utcnow,
)


def default_preference() -> NotificationPreference:
    """The settings a brand new account starts with (notifications on, all types)."""
    return NotificationPreference(
        new_events_enabled=True,
        event_kinds=list(EVENT_KINDS),
        group_reminders_enabled=True,
        web_push_enabled=True,
    )


def get_or_create_preference(db: Session, user: User) -> NotificationPreference:
    preference = db.scalar(
        select(NotificationPreference).where(NotificationPreference.user_id == user.id)
    )
    if preference is None:
        preference = default_preference()
        preference.user_id = user.id
        db.add(preference)
        db.commit()
        db.refresh(preference)
    return preference


def unread_count(db: Session, user_id: int) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.is_read.is_(False))
    ) or 0


def _push_targets(db: Session, user_ids: list[int]) -> dict[int, list[push.PushTarget]]:
    if not user_ids:
        return {}
    rows = db.scalars(
        select(PushSubscription).where(PushSubscription.user_id.in_(user_ids))
    ).all()
    targets: dict[int, list[push.PushTarget]] = {}
    for row in rows:
        targets.setdefault(row.user_id, []).append(
            push.PushTarget(id=row.id, endpoint=row.endpoint, p256dh=row.p256dh, auth=row.auth)
        )
    return targets


def _deliver_pushes(
    db: Session, targets: dict[int, list[push.PushTarget]], title: str, body: str, url: str
) -> None:
    expired: list[int] = []
    for batch in targets.values():
        for target in batch:
            result = push.send_push(target, title, body, url)
            if result == push.PUSH_GONE:
                expired.append(target.id)
    if expired:
        db.execute(delete(PushSubscription).where(PushSubscription.id.in_(expired)))
        db.commit()


def notify_group_members(
    db: Session,
    group: Group,
    kind: str,
    title: str,
    body: str,
    url: str,
    *,
    event_kind: str | None = None,
    exclude_user_ids: set[int] | None = None,
) -> int:
    """Create in-app notifications for every eligible member and push them."""
    exclude = exclude_user_ids or set()
    # A user who never opened Settings still gets the defaults.
    preferences = {
        preference.user_id: preference
        for preference in db.scalars(select(NotificationPreference)).all()
    }

    recipient_ids: list[int] = []
    for membership in db.scalars(
        select(Membership).where(Membership.group_id == group.id)
    ).all():
        if membership.user_id in exclude:
            continue
        preference = preferences.get(membership.user_id) or default_preference()
        if kind == NOTIFY_NEW_EVENT:
            if not preference.wants_event(event_kind or ""):
                continue
        elif kind == NOTIFY_GROUP_REMINDER and not preference.group_reminders_enabled:
            continue
        recipient_ids.append(membership.user_id)

    if not recipient_ids:
        return 0

    for user_id in recipient_ids:
        db.add(
            Notification(
                user_id=user_id,
                kind=kind,
                title=title,
                body=body,
                url=url,
            )
        )
    db.commit()

    targets = {
        user_id: batch
        for user_id, batch in _push_targets(db, recipient_ids).items()
        if (preferences.get(user_id) or default_preference()).web_push_enabled
    }
    _deliver_pushes(db, targets, title, body, url)
    return len(recipient_ids)


def notify_new_event(
    db: Session, group: Group, dog: Dog, event_kind: str, actor: User
) -> None:
    label = event_kind.capitalize()
    notify_group_members(
        db,
        group,
        NOTIFY_NEW_EVENT,
        f"{label} {dog.name} with {actor.username}",
        f"{actor.username} logged: {label} {dog.name}",
        f"/groups/{group.id}/events?dog_id={dog.id}",
        event_kind=event_kind,
        exclude_user_ids={actor.id},
    )


def notify_group_reminder(db: Session, group: Group, reminder: Reminder) -> None:
    notify_group_members(
        db,
        group,
        NOTIFY_GROUP_REMINDER,
        reminder.title,
        reminder.body or f"Reminder from {group.name}",
        f"/groups/{group.id}",
    )


def due_reminders(db: Session) -> list[Reminder]:
    return list(
        db.scalars(
            select(Reminder).where(
                Reminder.sent_at.is_(None), Reminder.scheduled_for <= utcnow()
            )
        ).all()
    )