#!/usr/bin/env python3
"""Robust startup wrapper — catches import/startup errors and writes them to a
visible log file before the process exits.

Usage (systemd ExecStart):
    ExecStart=/opt/dataedge/venv/bin/python startup_wrapper.py

On crash, writes the full traceback to /var/log/dataedge/startup_error.log
so `journalctl -u dataedge` and `cat /var/log/dataedge/startup_error.log`
both show the real reason.
"""

import logging
import os
import sys
import traceback
from datetime import datetime, timezone

LOG_DIR = os.environ.get("DATAEDGE_LOG_DIR", "/var/log/dataedge")
ERROR_LOG = os.path.join(LOG_DIR, "startup_error.log")


def _setup_logging():
    """Configure loguru + stdlib logging so ALL output goes to stdout/stderr
    (captured by systemd StandardOutput/Error) AND to our error log."""
    os.makedirs(LOG_DIR, exist_ok=True)

    # Redirect all uncaught exceptions to a file
    sys.stderr = open(os.path.join(LOG_DIR, "stderr_wrapper.log"), "a", buffering=1)

    # Set up basic logging as fallback
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def _write_startup_error(exc: Exception):
    """Write crash traceback to a dedicated log file."""
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(ERROR_LOG, "a") as f:
        f.write(f"\n{'='*80}\n")
        f.write(f"STARTUP CRASH at {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"Python: {sys.version}\n")
        f.write(f"CWD: {os.getcwd()}\n")
        f.write(f"PID: {os.getpid()}\n")
        f.write(f"{'='*80}\n")
        traceback.print_exc(file=f)
        f.write(f"{'='*80}\n\n")
    # Also write to stderr so systemd journal captures it
    traceback.print_exc(file=sys.stderr)
    sys.stderr.flush()


def main():
    _setup_logging()

    # Validate critical env vars BEFORE importing the app (which is heavy).
    # This catches the most common VPS deployment mistake: missing .env file.
    critical = {
        "GEMINI_API_KEY": "Gemini Live / TTS will fail",
        "VOBIZ_PUBLIC_BASE_URL": "Vobiz cannot reach this host",
    }
    missing = [k for k in critical if not os.environ.get(k)]
    if missing:
        msg = f"CRITICAL: Missing env vars: {', '.join(missing)}"
        logging.error(msg)
        with open(ERROR_LOG, "a") as f:
            f.write(f"\n{datetime.now(timezone.utc).isoformat()} — {msg}\n")
        # Don't exit — let the app start so diagnostics endpoint is available.

    try:
        # Add backend to path
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

        # Import the app — this is where most crash-loop errors happen
        # (missing numpy, miniaudio, websockets, etc.)
        from main import app  # noqa: E402

        import uvicorn

        port = int(os.environ.get("PORT", "8001"))
        host = os.environ.get("HOST", "0.0.0.0")

        logging.info(
            "Data Edge AI Agent starting — host=%s port=%s PID=%s",
            host, port, os.getpid(),
        )

        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            timeout_keep_alive=300,
            # Single worker for small VPS. Increase only if RAM > 4GB.
            workers=1,
        )

    except ImportError as exc:
        _write_startup_error(exc)
        logging.error(
            "IMPORT FAILED — a required Python package is missing: %s\n"
            "Run: pip install -r requirements.txt\n"
            "Or: pip install %s",
            exc, exc.name or "",
        )
        sys.exit(1)

    except Exception as exc:
        _write_startup_error(exc)
        logging.error("STARTUP CRASHED: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
