"""Fix WebSocket audio flow for Vobiz ↔ Gemini Live calls.

Run on the VPS server:
    cd /root/DataEdge/backend
    python fix_websocket.py

Fixes:
  1. Updates DB role public_url to match .env
  2. Ensures VOBIZ_STREAM_PUBLIC_BASE_URL bypasses Hostinger proxy (which blocks WS)
  3. Validates Gemini Live model name
  4. Recommends correct .env settings
"""

import json
import os
import sys
from pathlib import Path


def section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def check(label: str, ok: bool, detail: str = "") -> None:
    icon = "✓" if ok else "✗"
    print(f"  [{icon}] {label}")
    if detail:
        print(f"       {detail}")


def fix_env_file(env_path: Path) -> bool:
    """Fix the .env file with correct WebSocket-friendly settings."""
    if not env_path.exists():
        check(".env file found", False, f"Not found at {env_path}")
        return False

    content = env_path.read_text(encoding="utf-8")
    original = content
    changes = []

    # --- Fix VOBIZ_STREAM_PUBLIC_BASE_URL ---
    # Must use HTTP (not HTTPS) direct to VPS IP:port to bypass Hostinger WS block
    old_stream = ""
    for line in content.splitlines():
        if line.strip().startswith("VOBIZ_STREAM_PUBLIC_BASE_URL"):
            old_stream = line.strip()
            break

    correct_stream = 'VOBIZ_STREAM_PUBLIC_BASE_URL=http://89.116.122.41:8001'
    new_content = []
    found_stream = False
    for line in content.splitlines():
        if line.strip().startswith("VOBIZ_STREAM_PUBLIC_BASE_URL"):
            new_content.append(correct_stream)
            found_stream = True
            if line.strip() != correct_stream:
                changes.append(f"  VOBIZ_STREAM_PUBLIC_BASE_URL: {line.strip()} → {correct_stream}")
        else:
            new_content.append(line)
    if not found_stream:
        new_content.append("")
        new_content.append(correct_stream)
        changes.append(f"  Added VOBIZ_STREAM_PUBLIC_BASE_URL={correct_stream}")

    # --- Fix VOBIZ_PUBLIC_BASE_URL to keep Hostinger for HTTP callbacks ---
    correct_pub = 'VOBIZ_PUBLIC_BASE_URL=https://dataedge.srv1003582.hstgr.cloud'
    found_pub = False
    final_lines = []
    for line in new_content:
        if line.strip().startswith("VOBIZ_PUBLIC_BASE_URL"):
            final_lines.append(correct_pub)
            found_pub = True
            if line.strip() != correct_pub:
                changes.append(f"  VOBIZ_PUBLIC_BASE_URL: {line.strip()} → {correct_pub}")
        else:
            final_lines.append(line)
    if not found_pub:
        final_lines.append("")
        final_lines.append(correct_pub)
        changes.append(f"  Added VOBIZ_PUBLIC_BASE_URL={correct_pub}")

    new_content_str = "\n".join(final_lines) + "\n"

    if new_content_str != original:
        env_path.write_text(new_content_str, encoding="utf-8")
        check(".env updated", True, "; ".join(changes) if changes else "No changes needed")
        return True
    else:
        check(".env already correct", True)
        return False


def fix_db_public_url():
    """Update the role's public_url in SQLite to match current settings."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from config import settings
        from core.storage import _get_role_state_sync, _save_role_state_sync

        s = _get_role_state_sync("data_edge")
        v = dict(s.get("vobiz") or {})
        old_url = v.get("public_url", "")

        # Use the Hostinger domain for HTTP callbacks (works fine)
        # The WebSocket/stream URL is handled by VOBIZ_STREAM_PUBLIC_BASE_URL env var
        correct_url = "https://dataedge.srv1003582.hstgr.cloud"

        if old_url != correct_url:
            v["public_url"] = correct_url
            _save_role_state_sync("data_edge", vobiz_config=v)
            check("DB public_url updated", True, f"{old_url} → {correct_url}")
        else:
            check("DB public_url already correct", True, correct_url)

        # Also update greeting_text if needed
        from core.greeting_text_utils import coerce_stored_greeting
        text = coerce_stored_greeting("data_edge", s.get("greeting_text") or "")
        if text:
            check("Greeting text OK", True, text[:60] + "...")

    except Exception as e:
        check("DB update", False, f"Error: {e}")
        print("       (Run on the VPS where the DB exists)")


def check_gemini_model():
    """Check if the Gemini Live model name is valid."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from config import settings

    model = settings.gemini_live_model
    known_good = [
        "models/gemini-2.0-flash-exp",
        "models/gemini-2.0-flash-live",
        "models/gemini-2.5-flash-live",
    ]
    if model in known_good:
        check(f"Gemini Live model: {model}", True)
    elif "live" in model.lower():
        check(f"Gemini Live model: {model}", True,
              "Custom model — verify it supports BidiGenerateContent (Gemini Live API)")
    else:
        check(f"Gemini Live model: {model}", False,
              "Model name may not support Gemini Live API. "
              "Try: models/gemini-2.0-flash-exp")


def check_stream_url():
    """Verify the stream URL uses HTTP (not HTTPS) to bypass Hostinger WS block."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from config import settings

    stream = (settings.vobiz_stream_public_base_url or "").strip()
    pub = (settings.vobiz_public_base_url or "").strip()

    if not stream:
        check("VOBIZ_STREAM_PUBLIC_BASE_URL", False,
              "NOT SET — WSS URL will use VOBIZ_PUBLIC_BASE_URL which goes through "
              "Hostinger proxy (BLOCKS WebSocket).")
        return

    if "hstgr.cloud" in stream.lower():
        check("VOBIZ_STREAM_PUBLIC_BASE_URL", False,
              f"Uses Hostinger domain ({stream}) — WebSocket upgrades will be BLOCKED. "
              "Change to http://89.116.122.41:8001")
        return

    if stream.startswith("https://"):
        check("VOBIZ_STREAM_PUBLIC_BASE_URL", False,
              f"Uses HTTPS ({stream}) — unless nginx with SSL is configured for this domain, "
              "WebSocket will fail. Use http://89.116.122.41:8001 instead.")
        return

    if stream.startswith("http://"):
        check("VOBIZ_STREAM_PUBLIC_BASE_URL", True, stream)
        return

    check("VOBIZ_STREAM_PUBLIC_BASE_URL", False, f"Unknown format: {stream}")


def main():
    section("1. CHECKING STREAM URL CONFIG")
    check_stream_url()

    section("2. CHECKING GEMINI LIVE MODEL")
    check_gemini_model()

    section("3. UPDATING .ENV FILE")
    # Check local and possible VPS paths
    env_fixed = False
    for env_path in [
        Path(__file__).resolve().parent.parent / ".env",
        Path("/root/DataEdge/.env"),
        Path("/root/DataEdge/backend/.env"),
    ]:
        if env_path.exists():
            if fix_env_file(env_path):
                env_fixed = True
    if not env_fixed:
        check(".env fix skipped", False,
              "No .env found at expected paths. Edit manually.")

    section("4. UPDATING DATABASE PUBLIC_URL")
    fix_db_public_url()

    section("5. SUMMARY")
    print(f"""
  ROOT CAUSE: Hostinger shared hosting at dataedge.srv1003582.hstgr.cloud
  blocks WebSocket upgrade requests (101 Switching Protocols).

  FIX APPLIED:
  - VOBIZ_STREAM_PUBLIC_BASE_URL → http://89.116.122.41:8001
    (direct VPS connection bypassing Hostinger for media WebSocket)
  - VOBIZ_PUBLIC_BASE_URL → https://dataedge.srv1003582.hstgr.cloud
    (Hostinger domain for HTTP callbacks — works fine)
  - DB public_url synced to match

  AFTER FIX: Restart the server:
    systemctl restart dataedge.service

  OR if running locally:
    (restart your uvicorn process)

  IMPORTANT: Verify port 8001 is accessible on the VPS firewall:
    sudo ufw allow 8001/tcp
    # or if using iptables:
    # sudo iptables -A INPUT -p tcp --dport 8001 -j ACCEPT

  If calls still have no audio, run:
    python backend/diagnose_calls.py
""")


if __name__ == "__main__":
    main()
