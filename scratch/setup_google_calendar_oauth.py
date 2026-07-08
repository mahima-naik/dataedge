#!/usr/bin/env python3
"""One-time setup: sign in as alok.b@dariaan.in and print GOOGLE_CALENDAR_REFRESH_TOKEN.

Do NOT use Gmail password in .env — Google blocks that for Calendar API.

Prerequisites:
  1. Google Cloud project with Calendar API enabled.
  2. OAuth 2.0 Client ID (Desktop app) → download client_secret JSON.
  3. Run from repo root:
       cd backend && PYTHONPATH=. python3 ../scratch/setup_google_calendar_oauth.py \\
         --client-secrets /path/to/client_secret.json

Paste the printed refresh token into server .env as GOOGLE_CALENDAR_REFRESH_TOKEN.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print(
        "Install: pip install google-auth-oauthlib google-auth-httplib2",
        file=sys.stderr,
    )
    sys.exit(1)

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar",
]


def main() -> None:
    p = argparse.ArgumentParser(
        description="One-time OAuth for alok.b@dariaan.in Google Calendar (see GOOGLE_CALENDAR_OAUTH_SETUP.md)",
    )
    p.add_argument("--client-secrets", required=True, help="OAuth client JSON from Google Cloud")
    p.add_argument(
        "--write-env-snippet",
        action="store_true",
        help="Also write scratch/google_calendar.env.snippet (gitignored)",
    )
    p.add_argument(
        "--organizer-email",
        default="alok.b@dariaan.in",
        help="Calendar owner email (default: alok.b@dariaan.in)",
    )
    args = p.parse_args()
    path = Path(args.client_secrets)
    if not path.is_file():
        print(f"Missing file: {path}", file=sys.stderr)
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(str(path), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    if not creds.refresh_token:
        print(
            "ERROR: No refresh_token returned. Revoke app at https://myaccount.google.com/permissions "
            "and run again with prompt=consent.",
            file=sys.stderr,
        )
        sys.exit(1)

    data = json.loads(path.read_text())
    web = data.get("installed") or data.get("web") or {}
    lines = [
        "GOOGLE_CALENDAR_CLIENT_ID=" + str(web.get("client_id", "")),
        "GOOGLE_CALENDAR_CLIENT_SECRET=" + str(web.get("client_secret", "")),
        "GOOGLE_CALENDAR_REFRESH_TOKEN=" + str(creds.refresh_token),
        "GOOGLE_CALENDAR_ID=primary",
        "GOOGLE_CALENDAR_ORGANIZER_EMAIL=" + args.organizer_email.strip(),
        "DARIAAN_MEETING_BOOKING_ENABLED=1",
    ]
    body = "\n".join(lines) + "\n"

    print("\n--- Add these to /root/vernika/backend/.env on the VPS (never commit) ---\n")
    print(body)
    print("Sign-in must use the calendar owner:", args.organizer_email)
    print("Full guide: scratch/GOOGLE_CALENDAR_OAUTH_SETUP.md")

    if args.write_env_snippet:
        out = Path(__file__).resolve().parent / "google_calendar.env.snippet"
        out.write_text(body, encoding="utf-8")
        print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
