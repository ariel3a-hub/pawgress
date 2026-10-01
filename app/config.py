from __future__ import annotations

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_db_override = os.environ.get("DOGCARE_DB_PATH")
DATABASE_URL = (
    f"sqlite:///{Path(_db_override).as_posix()}"
    if _db_override
    else f"sqlite:///{(DATA_DIR / 'dogcare.db').as_posix()}"
)

_SECRET_KEY_FILE = DATA_DIR / "secret_key"


def _load_secret_key() -> str:
    if _SECRET_KEY_FILE.exists():
        stored = _SECRET_KEY_FILE.read_text(encoding="utf-8").strip()
        if stored:
            return stored
    key = secrets.token_urlsafe(48)
    _SECRET_KEY_FILE.write_text(key, encoding="utf-8")
    return key


SECRET_KEY = _load_secret_key()

SESSION_COOKIE = "dogcare_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30
REMINDER_POLL_SECONDS = 30
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}