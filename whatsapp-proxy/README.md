# WhatsApp Web proxy (whatsapp-web.js)

Unofficial sidecar — **ban risk**. Use a spare number.

## VPS (systemd)

```bash
cd /root/vernika/whatsapp-proxy && npm install
# Add to /root/vernika/backend/.env:
#   WHATSAPP_PROXY_ENABLED=1
#   WHATSAPP_PROXY_SECRET=your_random_secret
#   WHATSAPP_PROXY_URL=http://127.0.0.1:3001

cp /root/vernika/deploy/whatsapp-proxy.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now whatsapp-proxy
systemctl restart vernika
```

Open **http://YOUR_SERVER:8000/dariaan/whatsapp** → scan QR with WhatsApp → Linked devices.

## Docker

```bash
cd deploy
WHATSAPP_PROXY_ENABLED=1 WHATSAPP_PROXY_SECRET=secret docker compose up --build
```

## Flow

Phone scan → sidecar session → inbound message → `POST /api/whatsapp/proxy/message` → Dariaan lead → auto-dial Ananya.
