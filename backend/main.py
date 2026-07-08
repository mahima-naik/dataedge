"""Entry: ``uvicorn backend.main:app`` from project root."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import settings
from api.app import app

__all__ = ["app"]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.host, port=int(settings.port), log_level="info")
