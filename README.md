# Vernika — bridge server

Thin FastAPI app: **Vobiz** `POST/GET /vobiz/answer` returns stream XML; **`WebSocket /ws/vobiz`** relays PCM to **Gemini Live**.

## Layout

```text
frontend/                 # Operator static page (optional)
  index.html
  static/theme.css

backend/
  main.py                 # Uvicorn entry → ``app`` from ``api.app``
  api/
    app.py                # ``create_app()`` — routers + static mount
    lifespan.py
    routes/
      health.py           # ``GET /health``
      vobiz.py            # Vobiz answer + ``/ws/vobiz``
      ui.py               # ``GET /`` → ``frontend/index.html``
  config.py
  core/                   # State, SQLite, opening-line helpers
  services/
    vobiz_bridge/         # Bridge split into small modules (see package docstrings)
      live_session.py     # Main Live ⇄ Vobiz loop
      audio.py, vobiz_client.py, gemini_protocol.py, …
    gemini_tts.py, call_recording.py, …
```

## Run

```bash
cd backend
pip install -r requirements.txt
# Repo-root .env is loaded by config.py
PYTHONPATH=. uvicorn main:app --host 0.0.0.0 --port 8000
```

Or from repo root: `./start.sh`

## Docker (any laptop, Linux host, cloud VM)

Build context is the **repository root**: the image installs `backend/`, serves `frontend/` from `/app`, and persists state in a volume at `/app/backend/data` (SQLite, recordings, logs).

**Recommended (creates `.env` from `.env.example` if missing, checks Docker is up):**

```bash
chmod +x docker-up.sh   # once
./docker-up.sh
```

Equivalent manual steps:

```bash
cp .env.example .env   # fill GEMINI_API_KEY, VOBIZ_*, etc.
docker compose up --build
```

- **Port on the host:** default `8000` — set `EXPORT_PORT=9000 docker compose up` to map host → container `8000`.
- **`docker compose up` fails on “env_file … .env”?** Compose requires a repo-root `.env`. Run `./docker-up.sh` or copy `.env.example` first.
- **Local Python + Docker both “not running”?** Only one stack can bind `8000`. Stop Docker (`docker compose down`) or use `PORT=8001 ./start.sh` for bare-metal.
- **Secrets:** keep a local `.env` (not committed); compose injects those variables into the container.
- **Vobiz callbacks:** `VOBIZ_PUBLIC_BASE_URL` must be a URL **Vobiz can reach on the internet** (HTTPS tunnel, reverse proxy, or public domain), not `http://localhost:8000` on your laptop.

Development with live reload (bind-mounts `backend/` and `frontend/`):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Multi-architecture images (for example AMD64 servers + ARM laptops): build with BuildKit `docker buildx build --platform linux/amd64,linux/arm64 -t your-registry/vernika-bridge:latest --push .`

## Endpoints

| Path | Purpose |
|------|--------|
| `GET /` | Small status page (serves `frontend/index.html` when present) |
| `GET /health` | JSON liveness |
| `POST/GET /vobiz/answer` | Vobiz answer URL (XML `<Stream>`) |
| `WS /ws/vobiz` | Media WebSocket |

Configure `.env` with `GEMINI_API_KEY`, `VOBIZ_PUBLIC_BASE_URL`, and Vobiz credentials.
