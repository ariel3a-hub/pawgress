from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EVENT_KINDS: tuple[str, ...] = ("fed", "walked", "pooped", "peed")

EVENT_LABELS: dict[str, str] = {
    "fed": "Fed",
    "walked": "Walked",
    "pooped": "Pooped",
    "peed": "Peed",
}

EVENT_ICONS: dict[str, str] = {
    "fed": "\U0001f95a",
    "walked": "\U0001f415",
    "pooped": "\U0001f4a9",
    "peed": "\U0001f6bd",
}

ROLE_OWNER = "owner"
ROLE_MEMBER = "member"

NOTIFY_NEW_EVENT = "new_event"
NOTIFY_GROUP_REMINDER = "group_reminder"


def utcnow() -> datetime:
    """Naive UTC timestamp, matching what SQLite stores."""
    return datetime.now(UTC).replace(tzinfo=None)


def local_wallclock_to_utc(naive: datetime) -> datetime:
    """Convert a local wall-clock time (from <input type="datetime-local">) to UTC."""
    if naive.tzinfo is not None:
        return naive.astimezone(UTC).replace(tzinfo=None)
    return naive.astimezone().astimezone(UTC).replace(tzinfo=None)


def utc_to_local(naive: datetime | None) -> datetime | None:
    """Convert a stored UTC timestamp back to local wall-clock time for display."""
    if naive is None:
        return None
    return naive.replace(tzinfo=UTC).astimezone().replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    memberships: Mapped[list[Membership]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    notifications: Mapped[list[Notification]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    join_code: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    owner: Mapped[User] = relationship()
    memberships: Mapped[list[Membership]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    dogs: Mapped[list[Dog]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    reminders: Mapped[list[Reminder]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "group_id", name="uq_membership"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16), default=ROLE_MEMBER)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship(back_populates="memberships")
    group: Mapped[Group] = relationship(back_populates="memberships")


class Dog(Base):
    __tablename__ = "dogs"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    birthday: Mapped[date | None] = mapped_column(Date, nullable=True)
    photo_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    group: Mapped[Group] = relationship(back_populates="dogs")
    events: Mapped[list[Event]] = relationship(
        back_populates="dog", cascade="all, delete-orphan"
    )

    @property
    def age_label(self) -> str:
        if self.birthday is None:
            return "Birthday not set"
        days = (date.today() - self.birthday).days
        if days < 0:
            return "Birthday upcoming"
        years, remainder = divmod(days, 365)
        months = remainder // 30
        if years and months:
            return f"{years}y {months}m old"
        if years:
            return f"{years} year{'s' if years != 1 else ''} old"
        if days <= 0:
            return "Born today"
        return f"{months} month{'s' if months != 1 else ''} old"


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    dog_id: Mapped[int] = mapped_column(ForeignKey("dogs.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    dog: Mapped[Dog] = relationship(back_populates="events")
    user: Mapped[User] = relationship()

    @property
    def label(self) -> str:
        return EVENT_LABELS.get(self.kind, self.kind.title())

    @property
    def icon(self) -> str:
        return EVENT_ICONS.get(self.kind, "\u2022")

    @property
    def title(self) -> str:
        return f"{self.label} with {self.user.username}"


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    new_events_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    event_kinds: Mapped[list] = mapped_column(JSON, default=lambda: list(EVENT_KINDS))
    group_reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    web_push_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[User] = relationship()

    def wants_event(self, kind: str) -> bool:
        return self.new_events_enabled and kind in (self.event_kinds or [])


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(String(400), default="")
    url: Mapped[str] = mapped_column(String(255), default="/")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    user: Mapped[User] = relationship(back_populates="notifications")


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(String(400), default="")
    scheduled_for: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    group: Mapped[Group] = relationship(back_populates="reminders")
    author: Mapped[User] = relationship()

    @property
    def is_sent(self) -> bool:
        return self.sent_at is not None


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    endpoint: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(255))
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)