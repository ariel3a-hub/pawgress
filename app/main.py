from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.templating import Jinja2Templates

from . import notifications
from .config import (
    REMINDER_POLL_SECONDS,
    SECRET_KEY,
    SESSION_COOKIE,
    SESSION_HTTPS_ONLY,
    SESSION_MAX_AGE,
    UPLOAD_DIR,
)
from .db import SessionLocal, init_db
from .models import utcnow
from .routers import auth, dogs, events, groups, push_api, settings
from .templating import TEMPLATES_DIR

logger = logging.getLogger("dogcare")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

STATIC_DIR = TEMPLATES_DIR.parent / "static"


async def _reminder_loop() -> None:
    """Wake up regularly and notify the group for any reminder that came due."""
    while True:
        try:
            due = await asyncio.to_thread(_dispatch_due_reminders)
            for reminder_id in due:
                logger.info("Sent reminder %s", reminder_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Reminder sweep failed")
        await asyncio.sleep(REMINDER_POLL_SECONDS)


def _dispatch_due_reminders() -> list[int]:
    db = SessionLocal()
    try:
        sent: list[int] = []
        for reminder in notifications.due_reminders(db):
            notifications.notify_group_reminder(db, reminder.group, reminder)
            reminder.sent_at = utcnow()
            sent.append(reminder.id)
        db.commit()
        return sent
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    task = asyncio.create_task(_reminder_loop())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="Pawgress", lifespan=lifespan, docs_url="/api/docs")

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie=SESSION_COOKIE,
    max_age=SESSION_MAX_AGE,
    same_site="lax",
    https_only=SESSION_HTTPS_ONLY,
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

app.include_router(auth.router)
app.include_router(groups.router)
app.include_router(dogs.router)
app.include_router(events.router)
app.include_router(settings.router)
app.include_router(push_api.router)

TEMPLATES = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.exception_handler(403)
async def forbidden(request: Request, _exc):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Forbidden"}, status_code=403)
    return TEMPLATES.TemplateResponse(
        request=request,
        name="errors/error.html",
        context={
            "code": 403,
            "detail": "You do not have permission to do that.",
            "hide_nav": True,
        },
        status_code=403,
    )


@app.exception_handler(404)
async def not_found(request: Request, _exc):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Not found"}, status_code=404)
    return TEMPLATES.TemplateResponse(
        request=request,
        name="errors/error.html",
        context={"code": 404, "detail": "That page does not exist.", "hide_nav": True},
        status_code=404,
    )


@app.get("/healthz")
def healthz():
    return {"status": "ok"}