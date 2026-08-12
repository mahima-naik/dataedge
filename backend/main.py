"""Entry: ``uvicorn backend.main:app`` from project root."""

import gc
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# ── Memory optimization for small VPS (≤2 GB RAM) ────────────────────────
# Pre-allocate less memory for numpy's thread pool (default = CPU cores * 2).
# On a 1-core VPS this still wastes ~50MB on pthreads stacks.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

# Force gc.collect() aggressively — live_session creates many short-lived
# tasks and bytearrays that linger in gen-0/1 if we don't poke the collector.
gc.set_threshold(700, 10, 10)

from config import settings  # noqa: E402
from api.app import app  # noqa: E402, F401

__all__ = ["app"]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=settings.host,
        port=int(settings.port),
        log_level="info",
        workers=1,
        timeout_keep_alive=300,
    )
