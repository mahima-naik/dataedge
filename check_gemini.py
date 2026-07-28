import asyncio
import json
import urllib.request
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
from config import settings

print("=" * 60)
print("  CHECKING GEMINI API CONNECTION & LIVE MODELS")
print("=" * 60)

api_key = settings.gemini_api_key
print(f"API Key present: {bool(api_key)}")
if api_key:
    print(f"API Key prefix: {api_key[:8]}...")
else:
    print("❌ ERROR: GEMINI_API_KEY / GOOGLE_API_KEY is missing!")
    sys.exit(1)

live_model = settings.gemini_live_model
print(f"Configured Gemini Live Model: {live_model}")
analysis_model = settings.gemini_call_analysis_model
print(f"Configured Analysis Model: {analysis_model}")

print("\n--- 1. Testing Google AI Studio REST API (List Models) ---")
url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
try:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        models = data.get("models", [])
        print(f"✅ REST API OK! Total models available: {len(models)}")
        
        live_models = [m["name"] for m in models if "live" in m.get("name", "").lower() or "flash" in m.get("name", "").lower()]
        print("\nAvailable Flash / Live Models:")
        for lm in live_models[:10]:
            print(f"  - {lm}")
except Exception as e:
    print(f"❌ REST API Failure: {e}")

print("\n--- 2. Testing Text Generation (REST) ---")
gen_url = f"https://generativelanguage.googleapis.com/v1beta/models/{analysis_model}:generateContent?key={api_key}"
gen_body = {
    "contents": [{"parts": [{"text": "Hello! Reply with 'OK' if you can read this."}]}]
}
try:
    req = urllib.request.Request(
        gen_url,
        data=json.dumps(gen_body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        txt = res.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        print(f"✅ Text Generation OK! Model Response: {txt.strip()}")
except Exception as e:
    print(f"❌ Text Generation Failure with {analysis_model}: {e}")

print("\n--- 3. Testing Gemini Live WebSocket Handshake ---")
async def test_live_ws():
    try:
        import websockets
        ws_url = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerate?key={api_key}"
        headers = {"Content-Type": "application/json"}
        print(f"Connecting to Gemini Live WebSocket: {ws_url[:70]}...")
        async with websockets.connect(ws_url, additional_headers=headers, ping_interval=10) as ws:
            setup = {
                "setup": {
                    "model": live_model,
                    "generationConfig": {
                        "responseModalities": ["AUDIO"],
                        "speechConfig": {
                            "voiceConfig": {
                                "prebuiltVoiceConfig": {"voiceName": settings.gemini_live_voice}
                            }
                        }
                    }
                }
            }
            await ws.send(json.dumps(setup))
            print(f"✅ Setup sent for {live_model}! Awaiting setupComplete...")
            resp = await asyncio.wait_for(ws.recv(), timeout=5.0)
            data = json.loads(resp)
            if "setupComplete" in data:
                print("✅ GEMINI LIVE WEBSOCKET SUCCESS! Received setupComplete signal.")
            else:
                print(f"⚠️ Received response: {list(data.keys())}")
    except ImportError:
        print("ℹ️ websockets library not installed locally (run in venv or test via VPS)")
    except Exception as e:
        print(f"❌ Live WebSocket Test Error: {e}")

asyncio.run(test_live_ws())
print("\n" + "=" * 60)
