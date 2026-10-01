from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid
from pywebpush import WebPushException, webpush

from .config import DATA_DIR

logger = logging.getLogger(__name__)

_PRIVATE_KEY_FILE = DATA_DIR / "vapid_private.pem"
_PUBLIC_KEY_FILE = DATA_DIR / "vapid_public.pem"
VAPID_SUBJECT = "mailto:dogcare@example.com"

_vapid: Vapid | None = None


def _load_or_create_vapid() -> Vapid:
    global _vapid
    if _vapid is not None:
        return _vapid
    if _PRIVATE_KEY_FILE.exists():
        keys = Vapid.from_file(str(_PRIVATE_KEY_FILE))
    else:
        keys = Vapid()
        keys.generate_keys()
        keys.save_key(str(_PRIVATE_KEY_FILE))
        keys.save_public_key(str(_PUBLIC_KEY_FILE))
    _vapid = keys
    return keys


def public_key_urlsafe() -> str:
    keys = _load_or_create_vapid()
    raw = keys.public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _private_key_pem() -> str:
    return _load_or_create_vapid().private_pem().decode("ascii")


PUSH_SENT = "sent"
PUSH_GONE = "gone"
PUSH_FAILED = "failed"


@dataclass(slots=True)
class PushTarget:
    id: int
    endpoint: str
    p256dh: str
    auth: str


def send_push(target: PushTarget, title: str, body: str, url: str) -> str:
    """Deliver one web push message. Returns PUSH_SENT, PUSH_GONE or PUSH_FAILED."""
    payload = json.dumps({"title": title, "body": body, "url": url})
    try:
        webpush(
            subscription_info={
                "endpoint": target.endpoint,
                "keys": {"p256dh": target.p256dh, "auth": target.auth},
            },
            data=payload,
            vapid_private_key=_private_key_pem(),
            vapid_claims={"sub": VAPID_SUBJECT, "exp": int(time.time()) + 3600},
            timeout=10,
        )
        return PUSH_SENT
    except WebPushException as exc:
        status = getattr(exc.response, "status_code", None)
        if status in (404, 410):
            return PUSH_GONE
        logger.warning("Web push failed with status %s: %s", status, exc)
        return PUSH_FAILED
    except Exception:
        logger.exception("Unexpected web push error")
        return PUSH_FAILED