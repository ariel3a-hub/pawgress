from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import notifications
from ..db import get_db
from ..models import User
from ..security import hash_password, normalize_username, verify_password
from ..templating import render

router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
USERNAME_PATTERN = re.compile(r"^[a-z0-9_]{3,32}$")


@router.get("/signup")
def signup_form(request: Request, db: DbSession):
    return render(request, "auth/signup.html", db, form={}, hide_nav=True)


@router.post("/signup")
def signup(
    request: Request,
    db: DbSession,
    username: str = Form(""),
    email: str = Form(""),
    password: str = Form(""),
    password_confirm: str = Form(""),
):
    errors: list[str] = []
    clean_username = normalize_username(username)
    clean_email = email.strip().lower()

    if not USERNAME_PATTERN.match(clean_username):
        errors.append("Username must be 3-32 characters: letters, numbers or underscores.")
    if not EMAIL_PATTERN.match(clean_email):
        errors.append("Enter a valid email address.")
    if len(password) < 8:
        errors.append("Password must be at least 8 characters long.")
    if password != password_confirm:
        errors.append("The two passwords do not match.")

    if not errors:
        clash = db.scalar(
            select(User).where((User.username == clean_username) | (User.email == clean_email))
        )
        if clash is not None:
            if clash.username == clean_username:
                errors.append("That username is already taken.")
            else:
                errors.append("An account with that email already exists.")

    if errors:
        return render(
            request,
            "auth/signup.html",
            db,
            status_code=400,
            errors=errors,
            form={"username": username, "email": email},
            hide_nav=True,
        )

    user = User(username=clean_username, email=clean_email, password_hash=hash_password(password))
    db.add(user)
    db.flush()
    preference = notifications.default_preference()
    preference.user_id = user.id
    db.add(preference)
    db.commit()

    request.session["user_id"] = user.id
    return RedirectResponse("/groups", status_code=303)


@router.get("/login")
def login_form(request: Request, db: DbSession):
    return render(request, "auth/login.html", db, form={}, hide_nav=True)


@router.post("/login")
def login(
    request: Request,
    db: DbSession,
    identifier: str = Form(""),
    password: str = Form(""),
):
    user = None
    ident = identifier.strip()
    if ident:
        user = db.scalar(
            select(User).where(
                (User.username == normalize_username(ident)) | (User.email == ident.lower())
            )
        )

    if user is None or not verify_password(password, user.password_hash):
        return render(
            request,
            "auth/login.html",
            db,
            status_code=401,
            errors=["Incorrect username/email or password."],
            form={"identifier": identifier},
            hide_nav=True,
        )

    request.session["user_id"] = user.id
    return RedirectResponse("/groups", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/")
def home(request: Request, db: DbSession):
    target = "/groups" if "user_id" in request.session else "/login"
    return RedirectResponse(target, status_code=303)