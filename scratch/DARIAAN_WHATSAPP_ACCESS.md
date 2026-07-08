# Dariaan — WhatsApp → AI calls

Connect **your** WhatsApp Business to Meta. When someone messages you, they become a Dariaan lead and **Ananya calls them automatically**.

## Flow

```
Person messages your WhatsApp
    → Meta sends webhook to our server
    → New number saved in Dariaan lead list (pending)
    → Dariaan campaign starts (if not already running)
    → AI outbound call (Ananya)
```

You do **not** share WhatsApp password. You share **Meta API access** only.

---

## What you give us (from Meta Developers)

1. Open https://developers.facebook.com → your app → **WhatsApp** → **API Setup**

| Copy from Meta | Put in server `.env` |
|----------------|----------------------|
| **Phone number ID** | `WHATSAPP_PHONE_NUMBER_ID=` |
| **Access token** (permanent) | `WHATSAPP_ACCESS_TOKEN=` |

2. **Webhook** (Configuration tab):

| Field | Value |
|-------|--------|
| Callback URL | `https://YOUR-PUBLIC-URL/api/whatsapp/webhook` |
| Verify token | `dariaan_wa_2026_secure` (must match `WHATSAPP_VERIFY_TOKEN` on server) |

Subscribe to: **messages**

3. Tell us your **WhatsApp Business phone number** (e.g. `+91XXXXXXXXXX`) → we set `DARIAAN_WHATSAPP_NUMBER`

---

## Server flags (already set)

```env
WHATSAPP_INBOUND_LEADS_ENABLED=1
WHATSAPP_AUTO_DIAL_DARIAAN=1
WHATSAPP_VERIFY_TOKEN=dariaan_wa_2026_secure
```

- **Auto-dial on** = new WhatsApp message → AI calls (150s gap between calls, same as Dariaan campaign)
- Turn off auto-dial: `WHATSAPP_AUTO_DIAL_DARIAAN=0` (leads still added; you press Start manually)

---

## Personal WhatsApp vs Business API

| | Works? |
|--|--------|
| **WhatsApp Business API** (Meta Cloud) | Yes — this is what we use |
| Personal WhatsApp login / password | No — not supported |
| WhatsApp Web QR scan on your phone | No — Meta API only |

Your existing WhatsApp number can be migrated to **WhatsApp Business** in Meta Business Manager.

---

## After you send access

Paste here (or add to VPS `.env`):

```
WHATSAPP_PHONE_NUMBER_ID=...
WHATSAPP_ACCESS_TOKEN=...
DARIAAN_WHATSAPP_NUMBER=+91...
```

We restart the server and test with a message to your number.
