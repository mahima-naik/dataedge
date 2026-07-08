# Google OAuth for Dariaan calendar invites

Use this to let VernikaAI create **Google Calendar events** and send **email invites** as **alok.b@dariaan.in** (via Calendar API — not Gmail password).

**Time:** ~15 minutes, one-time.

---

## Part A — Google Cloud project

### 1. Open Google Cloud Console

Go to: **https://console.cloud.google.com/**

Sign in with **alok.b@dariaan.in** (or a Workspace admin who can grant Calendar access to that mailbox).

### 2. Create or pick a project

- Top bar → **Select a project** → **New Project**
- Name: e.g. `Dariaan VernikaAI`
- Click **Create**

### 3. Enable Calendar API

- Menu → **APIs & Services** → **Library**
- Search: `Google Calendar API`
- Open it → **Enable**

---

## Part B — OAuth consent screen

Menu → **APIs & Services** → **OAuth consent screen**

| Step | What to choose |
|------|----------------|
| User type | **Internal** if `@dariaan.in` is Google Workspace. Otherwise **External** (you must add test users while in “Testing”). |
| App name | `Dariaan Meeting Booker` |
| User support email | `alok.b@dariaan.in` |
| Developer contact | `alok.b@dariaan.in` |

**Scopes** → **Add or remove scopes** → add:

- `https://www.googleapis.com/auth/calendar`
- `https://www.googleapis.com/auth/calendar.events`

Save.

If **External** and status is **Testing**: under **Test users**, add `alok.b@dariaan.in`.

---

## Part C — OAuth client (Desktop)

1. **APIs & Services** → **Credentials**
2. **+ Create credentials** → **OAuth client ID**
3. Application type: **Desktop app**
4. Name: `Dariaan Desktop OAuth`
5. **Create**
6. Click **Download JSON** (file looks like `client_secret_123....json`)

Keep this file private. Do not commit it to git.

---

## Part D — Get refresh token (on your Mac)

In Terminal:

```bash
cd "/Users/surya/Downloads/VernikaAI/VernikaAI Max profit"

pip install google-auth-oauthlib google-auth-httplib2

cd backend
PYTHONPATH=. python3 ../scratch/setup_google_calendar_oauth.py \
  --client-secrets "/path/to/your/client_secret_XXXXX.json"
```

- A browser opens → choose **alok.b@dariaan.in**
- Click **Allow** for Calendar access
- Terminal prints lines like:

```env
GOOGLE_CALENDAR_CLIENT_ID=123456789-xxxx.apps.googleusercontent.com
GOOGLE_CALENDAR_CLIENT_SECRET=GOCSPX-xxxxx
GOOGLE_CALENDAR_REFRESH_TOKEN=1//0gxxxxx
GOOGLE_CALENDAR_ID=primary
GOOGLE_CALENDAR_ORGANIZER_EMAIL=alok.b@dariaan.in
DARIAAN_MEETING_BOOKING_ENABLED=1
```

Optional: save to a local snippet (not in git):

```bash
# same command, writes scratch/google_calendar.env.snippet (gitignored)
PYTHONPATH=. python3 ../scratch/setup_google_calendar_oauth.py \
  --client-secrets "/path/to/client_secret.json" \
  --write-env-snippet
```

---

## Part E — Put secrets on the VPS only

SSH to the server and edit **only** `/root/vernika/backend/.env`:

```bash
ssh root@31.97.186.20
nano /root/vernika/backend/.env
```

Paste the five `GOOGLE_CALENDAR_*` lines + set:

```env
DARIAAN_MEETING_BOOKING_ENABLED=1
```

Then:

```bash
systemctl restart vernika
```

Test import:

```bash
cd /root/vernika/backend && PYTHONPATH=. /root/vernika/venv/bin/python3 -c \
  "from services.dariaan_meeting_booking import dariaan_meeting_booking_configured; print(dariaan_meeting_booking_configured())"
```

Should print `True` once Client ID, Secret, and Refresh token are set.

---

## What OAuth does on each Interested call

1. Server uses **refresh token** → short-lived access token (no password).
2. Creates event on calendar `primary` for **alok.b@dariaan.in**.
3. Adds **Google Meet** link.
4. If the lead has **email** in CSV, Google sends a normal **calendar invite email** to that address (`sendUpdates=all`).
5. If WhatsApp is configured, also sends Meet link on WhatsApp.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `access_denied` / app not verified | Add `alok.b@dariaan.in` as **Test user** on consent screen, or publish app (Internal Workspace skips this). |
| No `refresh_token` printed | Run script again; browser must show consent again. Delete old token at https://myaccount.google.com/permissions if needed. |
| `invalid_grant` on server | Refresh token revoked — re-run Part D and update VPS `.env`. |
| Events created but no email invite | Lead row has no valid **email** in CSV; add email column. |
| `booking configured False` on VPS | Missing any of CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN in `.env`. |

---

## Security

- Never put **Gmail password** in `.env`.
- Never commit `client_secret*.json` or refresh token to GitHub.
- Rotate password if it was shared in chat.

---

## Quick links

- Cloud Console: https://console.cloud.google.com/
- Calendar API library: https://console.cloud.google.com/apis/library/calendar-json.googleapis.com
- Credentials: https://console.cloud.google.com/apis/credentials
- OAuth consent: https://console.cloud.google.com/apis/credentials/consent
- Account permissions (revoke): https://myaccount.google.com/permissions
