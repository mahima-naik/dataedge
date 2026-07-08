# Dariaan — Calendar + WhatsApp booking

When a **Dariaan** call ends with disposition **Interested**, the server can:

1. Create a **Google Calendar** event (30 min, Google Meet link)
2. Send the Meet link on **WhatsApp** (Meta Cloud API)

## Security

- **Do not** put Gmail passwords in `.env` or git. Google does not allow password-based Calendar API access.
- Use **OAuth** (one-time browser sign-in as `alok.b@dariaan.in`).
- **Rotate** any password that was shared in chat.

## 1. Google Calendar (OAuth)

**Full walkthrough:** [GOOGLE_CALENDAR_OAUTH_SETUP.md](./GOOGLE_CALENDAR_OAUTH_SETUP.md)

1. [Google Cloud Console](https://console.cloud.google.com/) → APIs → enable **Google Calendar API**.
2. Credentials → **OAuth client ID** → Desktop app → download JSON.
3. On your laptop:
   ```bash
   pip install google-auth-oauthlib
   cd backend && PYTHONPATH=. python3 ../scratch/setup_google_calendar_oauth.py \
     --client-secrets /path/to/client_secret.json
   ```
4. Browser opens → sign in as **alok.b@dariaan.in** → allow Calendar access.
5. Copy printed `GOOGLE_CALENDAR_*` lines into **VPS** `backend/.env` only.

## 2. WhatsApp Business (Meta)

1. [Meta for Developers](https://developers.facebook.com/) → WhatsApp → API setup.
2. Get **Phone number ID** and permanent **Access token**.
3. Add to VPS `.env`:
   ```
   WHATSAPP_ACCESS_TOKEN=...
   WHATSAPP_PHONE_NUMBER_ID=...
   ```
4. Recipient must have opted in / messaged your business number first (24h session rules for free-form text).

## 3. Enable on server

```env
DARIAAN_MEETING_BOOKING_ENABLED=1
GOOGLE_CALENDAR_CLIENT_ID=...
GOOGLE_CALENDAR_CLIENT_SECRET=...
GOOGLE_CALENDAR_REFRESH_TOKEN=...
GOOGLE_CALENDAR_ID=primary
GOOGLE_CALENDAR_ORGANIZER_EMAIL=alok.b@dariaan.in
WHATSAPP_ACCESS_TOKEN=...
WHATSAPP_PHONE_NUMBER_ID=...
```

Restart: `systemctl restart vernika`

## Meeting time

- Uses `requested_callback_datetime_iso` from call analysis when the founder agreed to a time.
- Otherwise defaults to **next weekday 11:00 IST**.

Booking result is stored on the lead under `analysis.meeting_booking`.
