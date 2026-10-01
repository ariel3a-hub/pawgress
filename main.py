"""Entry point: start the Pawgress dog care server.

Run with:  .venv\\Scripts\\python.exe main.py
"""

from __future__ import annotations

import os

import uvicorn

if __name__ == "__main__":
    # Hosts that terminate TLS in front of the app (Render) pass $PORT and
    # forward the original scheme in X-Forwarded-Proto.
    uvicorn.run(
        "app.main:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        proxy_headers=True,
        forwarded_allow_ips=os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1"),
        reload=os.environ.get("RELOAD", "1") == "1",
    )
