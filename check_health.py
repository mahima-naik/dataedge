"""Quick health check — run this from your LOCAL machine.
Tests:
  1. Gemini Live WebSocket connect + setup (with AQ. Bearer key support)
  2. VPS server reachability (HTTP)
  3. Config sanity
"""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

def section(t):
    print(f"\n{'='*60}\n  {t}\n{'='*60}")

def ok(label, passed, detail=""):
    icon = "✓" if passed else "✗"
    print(f"  [{icon}] {label}" + (f"\n       {detail}" if detail else ""))

async def main():
    try:
        from config import settings
    except Exception as e:
        print(f"[✗] Could not load config: {e}")
        return

    api_key   = settings.gemini_api_key
    model     = settings.gemini_live_model
    base_url  = settings.vobiz_public_base_url

    section("1. CONFIG SNAPSHOT")
    ok("GEMINI_API_KEY set",  bool(api_key), (api_key[:12] + "...") if api_key else "(empty)")
    ok("Key type",            True,          "AQ. Bearer key (new format)" if (api_key or "").startswith("AQ.") else "Legacy AIza key")
    ok("GEMINI_LIVE_MODEL",   bool(model),   model)
    ok("VPS public base URL", bool(base_url), base_url)

    section("2. GEMINI LIVE WEBSOCKET")
    try:
        import websockets
        ak = (api_key or "").strip()
        ws_url = (
            "wss://generativelanguage.googleapis.com/ws/"
            "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
            f"?key={ak}"
        )
        headers = {}

        print(f"  Connecting to Gemini Live as model '{model}' ...")
        async with websockets.connect(
            ws_url,
            additional_headers=headers,
            open_timeout=10,
            ping_interval=None,
        ) as ws:
            setup = {
                "setup": {
                    "model": model if model.startswith("models/") else f"models/{model}",
                    "generationConfig": {"responseModalities": ["audio"]},
                    "systemInstruction": {"parts": [{"text": "You are a test assistant."}]},
                }
            }
            await ws.send(json.dumps(setup))
            try:
                resp = await asyncio.wait_for(ws.recv(), timeout=8)
                data = json.loads(resp)
                if "setupComplete" in data:
                    ok("Gemini Live WebSocket", True, f"Setup complete ✓  model={model}")
                elif "error" in data:
                    err = data["error"]
                    ok("Gemini Live WebSocket", False, f"API error {err.get('code')}: {err.get('message','?')}")
                else:
                    ok("Gemini Live WebSocket", True, f"Got response keys: {list(data.keys())}")
            except asyncio.TimeoutError:
                ok("Gemini Live WebSocket", False, "Timeout — model may be invalid or key rejected")
    except Exception as e:
        ok("Gemini Live WebSocket", False, str(e))

    section("3. VPS SERVER REACHABILITY")
    if base_url:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
                r = await c.get(f"{base_url.rstrip('/')}/health")
                ok("VPS /health endpoint", r.status_code < 500, f"HTTP {r.status_code}")
        except Exception as e:
            ok("VPS /health endpoint", False, str(e))

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
                r = await c.get(f"{base_url.rstrip('/')}/vobiz/answer")
                ok("VPS /vobiz/answer", r.status_code < 500, f"HTTP {r.status_code}")
        except Exception as e:
            ok("VPS /vobiz/answer", False, str(e))
    else:
        ok("VPS reachability", False, "VOBIZ_PUBLIC_BASE_URL not set")

    section("DONE — next step")
    print("  If all ✓ → trigger a test call with:  python trigger_test_call.py\n")

if __name__ == "__main__":
    asyncio.run(main())
