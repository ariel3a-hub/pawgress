# Pawgress 🐾

A web app for taking care of dogs together. Sign up, create or join a **group**, add your
dogs, and log every **fed / walked / pooped / peed** event so everyone who cares for the
dog can see what happened and who did it.

## Features

| Area | What it does |
| --- | --- |
| Accounts | Sign up with username + email + password, log in, log out. Passwords are hashed with PBKDF2-SHA256. |
| Groups | Create a group or join one with a 6-character code. Every member can log events. |
| Ownership | The creator is the owner. The owner can hand ownership to another member, add/remove dogs, and delete group reminders. |
| Dogs | Name, birthday and photo (JPEG/PNG/WebP/GIF up to 5 MB). The owner's only. |
| Events page | Full timeline grouped by day. With more than one dog a dropdown switches between each dog's events. |
| Add event page | Buttons with each dog's photo and name; press a dog, then press fed / walked / pooped / peed. Events show up as "Walked with ariel". |
| Settings | Toggle notifications for new events, pick **which event types** you care about, and toggle group reminders. |
| Group reminders | Any member can schedule a reminder; it raises a notification for **everyone** in the group when it comes due. |
| Notifications | In-app bell with unread badge + a notifications page, plus optional Web Push (system notifications when the tab is closed). |

## Requirements

- Python 3.11 or newer
- (works on Python 3.14)

## Setup

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Run it

```powershell
.venv\Scripts\python.exe main.py
```

Then open <http://127.0.0.1:8000>.

Alternative:

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Web Push needs a secure context, so system notifications only fire over
`https://` or on `http://localhost`. On `127.0.0.1` everything else still works.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest tests -q
```

The smoke test walks the whole flow: signup → create group → add dogs → log events →
second user joins → owner transfer → notification preferences → group reminders → push
endpoints → auth guards. It uses a throwaway database in a temp folder.

Lint:

```powershell
.venv\Scripts\python.exe -m ruff check app main.py tests
```

## Project layout

```
main.py                     entry point (runs uvicorn)
app/
  main.py                   FastAPI app, middleware, lifespan, reminder scheduler
  config.py                 paths, secret key, upload limits
  db.py                     SQLAlchemy engine/session, SQLite pragmas
  models.py                 User, Group, Membership, Dog, Event, Reminder,
                            Notification, NotificationPreference, PushSubscription
  security.py               password hashing, session user, group access guards
  notifications.py          preference handling + in-app/web push delivery
  push.py                   VAPID keys and the Web Push sender
  templating.py             shared Jinja2 setup and render helper
  routers/
    auth.py                 signup / login / logout
    groups.py               groups, join, ownership, reminders
    dogs.py                 dog CRUD + photo upload
    events.py               timeline and event logging
    settings.py             notification preferences + notifications page
    push_api.py             push subscribe/unsubscribe, unread count, service worker
  templates/                Jinja2 pages
  static/                   css, js, service worker, icon
data/                       created at runtime: SQLite db, uploads, secret key, VAPID keys
tests/test_app.py           end-to-end smoke test
```

## Notes

- `data/` is created on first run: `dogcare.db` (SQLite), `uploads/` (dog photos),
  `secret_key` (session signing), `vapid_*.pem` (Web Push keys). Delete `data/dogcare.db`
  to reset everything.
- Session cookies are signed with the auto-generated key in `data/secret_key`.
- If you run it on a server other than localhost, set a strong `SECRET_KEY` there and put
  it behind HTTPS.