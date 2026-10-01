"""Entry point: start the Pawgress dog care server.

Run with:  .venv\\Scripts\\python.exe main.py
"""

from __future__ import annotations

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )