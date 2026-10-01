from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from . import notifications
from .models import EVENT_ICONS, EVENT_KINDS, EVENT_LABELS, User, utc_to_local
from .security import get_current_user

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def _strftime(value, fmt: str) -> str:
    return value.strftime(fmt) if value else ""


templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
# Timestamps are stored in UTC; show them in the browser's own timezone.
templates.env.filters["localtime"] = utc_to_local
templates.env.filters["strftime"] = _strftime


def render(
    request: Request,
    template: str,
    db: Session,
    *,
    user: User | None = None,
    status_code: int = 200,
    **context,
):
    """Render a template with the context every page needs."""
    if user is None:
        user = get_current_user(request, db)
    context.setdefault("current_user", user)
    context.setdefault("unread_count", notifications.unread_count(db, user.id) if user else 0)
    context.setdefault("event_kinds", EVENT_KINDS)
    context.setdefault("event_labels", EVENT_LABELS)
    context.setdefault("event_icons", EVENT_ICONS)
    context.setdefault("flash", request.session.pop("flash", None))
    return templates.TemplateResponse(
        request=request, name=template, context=context, status_code=status_code
    )


def flash_redirect(request: Request, url: str, message: str, category: str = "success"):
    request.session["flash"] = {"message": message, "category": category}
    return RedirectResponse(url, status_code=303)