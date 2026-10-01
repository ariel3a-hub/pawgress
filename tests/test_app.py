"""End-to-end smoke test for the dog care app.

Run with:  .venv\\Scripts\\python.exe -m pytest tests -q
or simply: .venv\\Scripts\\python.exe tests\\test_app.py
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

TMP_DIR = tempfile.mkdtemp(prefix="dogcare-test-")
os.environ["DOGCARE_DB_PATH"] = str(Path(TMP_DIR) / "test.db")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Dog  # noqa: E402

PNG_PIXELS = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753"
    "de0000000c4944415408d76360000002000154a24f7f0000000049454e44ae426082"
)


def signup(client: TestClient, username: str, email: str) -> None:
    response = client.post(
        "/signup",
        data={
            "username": username,
            "email": email,
            "password": "password123",
            "password_confirm": "password123",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text


def add_dog(client: TestClient, group_id: int, name: str, birthday: str = "2021-04-01") -> int:
    response = client.post(
        f"/groups/{group_id}/dogs",
        data={"name": name, "birthday": birthday},
        files={"photo": (f"{name}.png", PNG_PIXELS, "image/png")},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    # The redirect points back at the group, so read the new dog's id from the database.
    with SessionLocal() as db:
        dog = db.scalar(select(Dog).where(Dog.group_id == group_id, Dog.name == name))
        assert dog is not None, f"{name} was not created"
        return dog.id


def extract_group_id(location: str) -> int:
    for part in location.split("/"):
        if part.isdigit():
            return int(part)
    raise AssertionError(f"No id in {location}")


def add_event(client: TestClient, group_id: int, dog_id: int, kind: str, note: str = "") -> None:
    response = client.post(
        f"/groups/{group_id}/events",
        data={"dog_id": str(dog_id), "kind": kind, "note": note},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    # Guard against a 303 that is really a redirect to the login page.
    assert response.headers["location"].startswith(f"/groups/{group_id}/"), response.headers[
        "location"
    ]


def main() -> int:
    with TestClient(app) as client:
        # --- signup ---------------------------------------------------
        # Note: ariel never visits /settings here, so the notification
        # assertions below also cover the "default preferences" path.
        signup(client, "ariel", "ariel@example.com")

        # duplicate username is rejected
        second = TestClient(app)
        response = second.post(
            "/signup",
            data={
                "username": "ariel",
                "email": "other@example.com",
                "password": "password123",
                "password_confirm": "password123",
            },
        )
        assert response.status_code == 400 and "already taken" in response.text

        # --- create group --------------------------------------------
        response = client.post("/groups", data={"name": "Park crew"}, follow_redirects=False)
        assert response.status_code == 303
        group_id = extract_group_id(response.headers["location"])

        detail = client.get(f"/groups/{group_id}")
        assert "Park crew" in detail.text and "Transfer ownership" not in detail.text

        code_match = re.search(r"<code>([A-Za-z0-9]{6})</code>", detail.text)
        assert code_match, "join code missing from group page"
        join_code = code_match.group(1)

        # --- add dogs --------------------------------------------------
        rex_id = add_dog(client, group_id, "Rex", "2021-04-01")
        luna_id = add_dog(client, group_id, "Luna", "2023-11-15")
        assert client.get(f"/dogs/{rex_id}").status_code == 200
        assert "/uploads/" in client.get(f"/dogs/{rex_id}").text

        # --- log events ------------------------------------------------
        add_event(client, group_id, rex_id, "fed", "one cup of kibble")
        add_event(client, group_id, rex_id, "walked")
        add_event(client, group_id, luna_id, "pooped")

        timeline = client.get(f"/groups/{group_id}/events")
        assert "Walked with ariel" in timeline.text
        assert "Fed with ariel" in timeline.text
        assert "Pooped with ariel" in timeline.text
        assert "Show events for" in timeline.text, "dropdown should appear with 2+ dogs"

        filtered = client.get(f"/groups/{group_id}/events?dog_id={luna_id}")
        assert "Pooped with ariel" in filtered.text
        assert "Walked with ariel" not in filtered.text

        add_page = client.get(f"/groups/{group_id}/events/new")
        assert set(re.findall(r'name="kind" value="(\w+)"', add_page.text)) == {
            "fed",
            "walked",
            "pooped",
            "peed",
        }
        # one step (pick an event type) per dog
        assert add_page.text.count('name="dog_id"') == 2
        # with no ?dog_id the page asks you to choose first
        assert "Choose a dog above" in add_page.text

        chosen = client.get(f"/groups/{group_id}/events/new?dog_id={luna_id}")
        assert f'name="dog_id" value="{luna_id}"' in chosen.text

        # --- second user joins ------------------------------------------
        with TestClient(app) as friend:
            signup(friend, "noa", "noa@example.com")
            response = friend.post(
                "/groups/join", data={"code": join_code}, follow_redirects=False
            )
            assert response.status_code == 303
            assert response.headers["location"].endswith(str(group_id))

            # members cannot add dogs
            denied = friend.post(
                f"/groups/{group_id}/dogs",
                data={"name": "Sneaky", "birthday": ""},
                files={"photo": ("x.png", PNG_PIXELS, "image/png")},
            )
            assert denied.status_code == 403, denied.text

            # members can log events, and ariel gets notified
            add_event(friend, group_id, rex_id, "peed")
            unread = client.get("/api/notifications/unread-count").json()["count"]
            assert unread >= 1, "expected ariel to have unread notifications"
            notifications = client.get("/notifications")
            assert "Peed Rex with noa" in notifications.text, notifications.text
            # visiting the page marks everything as read
            assert client.get("/api/notifications/unread-count").json()["count"] == 0

            # --- owner transfer -----------------------------------------
            detail = client.get(f"/groups/{group_id}").text
            option_match = re.search(r'<option value="(\d+)">\s*noa\s*</option>', detail)
            assert option_match, "noa should be listed as a new-owner option"

            response = client.post(
                f"/groups/{group_id}/transfer",
                data={"member_id": option_match.group(1)},
                follow_redirects=False,
            )
            assert response.status_code == 303
            assert "Ownership transferred" in client.get(f"/groups/{group_id}").text

            # ariel is no longer the owner and cannot add dogs
            assert (
                client.post(
                    f"/groups/{group_id}/dogs",
                    data={"name": "Nope", "birthday": ""},
                    files={"photo": ("x.png", PNG_PIXELS, "image/png")},
                ).status_code
                == 403
            )

            # --- notification preferences -------------------------------
            settings = client.get("/settings")
            assert "Notify me about new events" in settings.text
            assert settings.text.count('name="kinds" value=') == 4
            assert "Notify me about group reminders" in settings.text
            assert "Browser notifications" in settings.text

            saved = client.post(
                "/settings/notifications",
                data={
                    "new_events_enabled": "on",
                    "kinds": ["fed"],
                    "group_reminders_enabled": "on",
                    "web_push_enabled": "on",
                },
                follow_redirects=False,
            )
            assert saved.status_code == 303, saved.text

            # only "fed" should now raise a notification
            add_event(friend, group_id, rex_id, "walked")
            add_event(friend, group_id, rex_id, "fed")

        feed = client.get("/notifications").text
        items = re.findall(r"<strong>([^<]+)</strong>", feed)
        assert "Fed Rex with noa" in items, items
        assert "Walked Rex with noa" not in items, items

        # --- group reminders ------------------------------------------------
        response = client.post(
            f"/groups/{group_id}/reminders",
            data={
                "title": "Vet appointment",
                "body": "Bring the papers",
                "scheduled_for": "2020-01-01T10:00",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        group_page = client.get(f"/groups/{group_id}")
        assert "Vet appointment" in group_page.text and "Sent" in group_page.text
        assert "Vet appointment" in client.get("/notifications").text

        # --- push plumbing ----------------------------------------------------
        key = client.get("/api/push/key")
        assert key.status_code == 200 and len(key.json()["public_key"]) > 80
        assert client.get("/sw.js").status_code == 200
        assert client.post(
            "/api/push/subscribe",
            json={
                "endpoint": "https://fcm.googleapis.com/fcm/send/fake-endpoint",
                "keys": {"p256dh": "abc", "auth": "def"},
            },
        ).json() == {"status": "subscribed"}

        # --- auth guard --------------------------------------------------------
        anonymous = TestClient(app)
        assert anonymous.get("/groups", follow_redirects=False).status_code == 303
        assert anonymous.get("/settings", follow_redirects=False).headers["location"] == "/login"

        # --- logout -------------------------------------------------------------
        client.post("/logout")
        assert client.get("/groups", follow_redirects=False).status_code == 303

    print("all smoke tests passed")
    return 0


def test_smoke() -> None:
    """Full flow: signup, group, dogs, events, notifications, reminders."""
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())