from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import ROLE_OWNER, Group, Membership, User

PBKDF2_ITERATIONS = 240_000
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITERATIONS
    ).hex()
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, digest = stored.split("$")
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations)
    ).hex()
    return hmac.compare_digest(candidate, digest)


def generate_join_code(length: int = 6) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def normalize_join_code(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.strip().upper())


def normalize_username(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "", value.strip().lower())


def find_user_by_credentials(db: Session, identifier: str) -> User | None:
    ident = identifier.strip()
    if not ident:
        return None
    return db.scalar(
        select(User).where(
            (User.username == normalize_username(ident)) | (User.email == ident.lower())
        )
    )


def get_current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get(User, user_id)


DbSession = Annotated[Session, Depends(get_db)]


def redirect_to_login() -> HTTPException:
    """A 303 with a Location header makes the browser navigate to the login page."""
    return HTTPException(status_code=303, headers={"Location": "/login"})


def require_user(request: Request, db: DbSession) -> User:
    user = get_current_user(request, db)
    if user is None:
        raise redirect_to_login()
    return user


CurrentUser = Annotated[User, Depends(require_user)]


def require_group_access(db: Session, user: User, group_id: int) -> tuple[Group, Membership]:
    found = load_group(db, user.id, group_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Group not found")
    return found


def require_group_owner(db: Session, user: User, group_id: int) -> tuple[Group, Membership]:
    group, membership = require_group_access(db, user, group_id)
    if not is_owner(membership):
        raise HTTPException(status_code=403, detail="Only the group owner can do that")
    return group, membership


def load_membership(db: Session, user_id: int, group_id: int) -> Membership | None:
    return db.scalar(
        select(Membership).where(
            Membership.user_id == user_id, Membership.group_id == group_id
        )
    )


def load_group(db: Session, user_id: int, group_id: int) -> tuple[Group, Membership] | None:
    membership = load_membership(db, user_id, group_id)
    if membership is None:
        return None
    return membership.group, membership


def is_owner(membership: Membership) -> bool:
    return membership.role == ROLE_OWNER