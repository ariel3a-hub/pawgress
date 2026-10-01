from __future__ import annotations

import secrets
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import ALLOWED_IMAGE_TYPES, MAX_UPLOAD_BYTES, UPLOAD_DIR
from ..db import get_db
from ..models import Dog, Event
from ..security import CurrentUser, require_group_access, require_group_owner
from ..templating import flash_redirect, render

router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]


def _store_upload(upload: UploadFile) -> str | None:
    if upload is None or not upload.filename:
        return None
    content_type = (upload.content_type or "").split(";")[0].strip().lower()
    extension = ALLOWED_IMAGE_TYPES.get(content_type)
    if extension is None:
        raise HTTPException(status_code=400, detail="Photo must be a JPEG, PNG, WebP or GIF image.")

    payload = upload.file.read(MAX_UPLOAD_BYTES + 1)
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Photo must be smaller than 5 MB.")
    if not payload:
        return None

    filename = f"{secrets.token_hex(12)}{extension}"
    (UPLOAD_DIR / filename).write_bytes(payload)
    return f"/uploads/{filename}"


def _parse_birthday(raw: str) -> date | None:
    clean = raw.strip()
    if not clean:
        return None
    try:
        return date.fromisoformat(clean)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Birthday must be a valid date.") from exc


@router.get("/groups/{group_id}/dogs/new")
def dog_form(request: Request, db: DbSession, user: CurrentUser, group_id: int):
    group, _ = require_group_owner(db, user, group_id)
    return render(
        request, "dogs/form.html", db, user=user, group=group, dog=None, form={}, errors=[]
    )


@router.post("/groups/{group_id}/dogs")
def create_dog(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    group_id: int,
    name: str = Form(""),
    birthday: str = Form(""),
    photo: UploadFile | None = File(default=None),
):
    group, _ = require_group_owner(db, user, group_id)
    clean_name = name.strip()[:60]
    errors: list[str] = []
    if not clean_name:
        errors.append("The dog needs a name.")
    try:
        parsed_birthday = _parse_birthday(birthday)
    except HTTPException as exc:
        errors.append(exc.detail)
        parsed_birthday = None
    if errors:
        return render(
            request,
            "dogs/form.html",
            db,
            user=user,
            group=group,
            dog=None,
            form={"name": name, "birthday": birthday},
            errors=errors,
            status_code=400,
        )

    dog = Dog(
        group_id=group.id,
        name=clean_name,
        birthday=parsed_birthday,
        photo_path=_store_upload(photo),
    )
    db.add(dog)
    db.commit()
    return flash_redirect(
        request, f"/groups/{group.id}", f'{dog.name} joined {group.name}.'
    )


@router.get("/dogs/{dog_id}/edit")
def edit_dog_form(request: Request, db: DbSession, user: CurrentUser, dog_id: int):
    dog = db.get(Dog, dog_id)
    if dog is None:
        raise HTTPException(status_code=404, detail="Dog not found")
    group, _ = require_group_owner(db, user, dog.group_id)
    return render(
        request,
        "dogs/form.html",
        db,
        user=user,
        group=group,
        dog=dog,
        form={"name": dog.name, "birthday": dog.birthday.isoformat() if dog.birthday else ""},
        errors=[],
    )


@router.post("/dogs/{dog_id}/edit")
def update_dog(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    dog_id: int,
    name: str = Form(""),
    birthday: str = Form(""),
    photo: UploadFile | None = File(default=None),
):
    dog = db.get(Dog, dog_id)
    if dog is None:
        raise HTTPException(status_code=404, detail="Dog not found")
    group, _ = require_group_owner(db, user, dog.group_id)
    clean_name = name.strip()[:60]
    errors: list[str] = []
    if not clean_name:
        errors.append("The dog needs a name.")
    try:
        parsed_birthday = _parse_birthday(birthday)
    except HTTPException as exc:
        errors.append(exc.detail)
        parsed_birthday = dog.birthday

    if errors:
        return render(
            request,
            "dogs/form.html",
            db,
            user=user,
            group=group,
            dog=dog,
            form={"name": name, "birthday": birthday},
            errors=errors,
            status_code=400,
        )

    dog.name = clean_name
    dog.birthday = parsed_birthday
    new_photo = _store_upload(photo)
    if new_photo:
        dog.photo_path = new_photo
    db.commit()
    return flash_redirect(request, f"/groups/{group.id}", f"{dog.name} updated.")


@router.post("/dogs/{dog_id}/delete")
def delete_dog(request: Request, db: DbSession, user: CurrentUser, dog_id: int):
    dog = db.get(Dog, dog_id)
    if dog is None:
        raise HTTPException(status_code=404, detail="Dog not found")
    group, _ = require_group_owner(db, user, dog.group_id)
    name = dog.name
    db.delete(dog)
    db.commit()
    return flash_redirect(request, f"/groups/{group.id}", f"{name} was removed from the group.")


@router.get("/dogs/{dog_id}")
def dog_profile(request: Request, db: DbSession, user: CurrentUser, dog_id: int):
    dog = db.get(Dog, dog_id)
    if dog is None:
        raise HTTPException(status_code=404, detail="Dog not found")
    group, membership = require_group_access(db, user, dog.group_id)
    events = db.scalars(
        select(Event).where(Event.dog_id == dog.id).order_by(Event.created_at.desc()).limit(50)
    ).all()
    return render(
        request,
        "dogs/profile.html",
        db,
        user=user,
        group=group,
        membership=membership,
        dog=dog,
        events=events,
    )