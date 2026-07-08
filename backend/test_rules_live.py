import asyncio
import os
import sys
import json
import base64
import websockets
from typing import Any
from loguru import logger

# Add backend directory to sys.path so we can import modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import settings
from core.storage import init_db
from core.state import init_state, get_state
from core.role_sandbox import sync_all_role_sandboxes_on_startup
from prompts.priya import build_role_system_prompt
from services.vobiz_bridge.gemini_protocol import build_live_setup, GEMINI_LIVE_URL_TMPL

async def handle_tool_calls(gem: Any, obj: dict):
    tc = obj.get("toolCall") or {}
    fn_calls = tc.get("functionCalls") or tc.get("function_calls") or []
    if fn_calls:
        logger.info(f"Received function calls: {fn_calls}")
        for fc in fn_calls:
            tool_resp = {
                "toolResponse": {
                    "functionResponses": [
                        {
                            "name": fc.get("name"),
                            "id": fc.get("id"),
                            "response": {"output": "Mock success"}
                        }
                    ]
                }
            }
            await gem.send(json.dumps(tool_resp))
            logger.info(f"Sent tool response for {fc.get('name')}")

async def stream_silence_loop(gem: Any, stop_event: asyncio.Event):
    # 16kHz 16-bit mono PCM, 100ms = 1600 samples = 3200 bytes
    silent_chunk = b"\x00" * 3200
    b64_silence = base64.b64encode(silent_chunk).decode("ascii")
    payload = {
        "realtimeInput": {
            "audio": {
                "data": b64_silence,
                "mimeType": "audio/pcm;rate=16000",
            }
        }
    }
    while not stop_event.is_set():
        try:
            await gem.send(json.dumps(payload))
        except Exception:
            break
        await asyncio.sleep(0.1)

async def test_role_once(role: str, attempt: int) -> dict:
    logger.info(f"--- Testing {role} | Silence Nudge Attempt {attempt}/2 ---")
    
    # Compile prompt
    role_config = get_state(role)
    lead = {"segment": "rfq"}
    system_prompt = build_role_system_prompt(role, role_config, lead)
    
    # Build Gemini Live Setup
    voice = settings.gemini_live_voice
    model = settings.gemini_live_model
    language_code = settings.gemini_live_language_code
    api_key = settings.gemini_api_key
    
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in config/settings")
        
    setup = build_live_setup(
        model=model,
        system_instruction=system_prompt,
        voice=voice,
        language_code=language_code,
        vad_ultra=False
    )
    
    gemini_url = GEMINI_LIVE_URL_TMPL.format(api_key=api_key)
    
    silence_success = False
    silence_response_text = ""
    
    async with websockets.connect(gemini_url) as gem:
        # Send setup
        await gem.send(json.dumps(setup))
        
        # Start streaming PCM silence in the background
        stop_silence = asyncio.Event()
        silence_task = asyncio.create_task(stream_silence_loop(gem, stop_silence))
        
        # Send email confirmation request first to get a real session state
        user_turn_email = {
            "clientContent": {
                "turns": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": "Hello, my email is test_user@example.com. Please confirm it."}
                        ]
                    }
                ],
                "turnComplete": True
            }
        }
        await gem.send(json.dumps(user_turn_email))
        
        # Consume response for Turn 0 (email)
        try:
            async def read_email():
                async for raw in gem:
                    obj = json.loads(raw) if isinstance(raw, str) else json.loads(raw.decode("utf-8"))
                    await handle_tool_calls(gem, obj)
                    sc = obj.get("serverContent") or {}
                    if sc.get("turnComplete") or sc.get("generationComplete"):
                        break
            await asyncio.wait_for(read_email(), timeout=12.0)
        except Exception:
            pass
            
        # Drain residual messages
        while True:
            try:
                raw = await asyncio.wait_for(gem.recv(), timeout=0.25)
                obj = json.loads(raw) if isinstance(raw, str) else json.loads(raw.decode("utf-8"))
                await handle_tool_calls(gem, obj)
            except Exception:
                break
                
        # Wait 3 seconds of silence
        await asyncio.sleep(3.0)
                
        # Send silence nudge text using clientContent
        logger.info("Sending simple silence nudge...")
        silence_nudge = {
            "clientContent": {
                "turns": [
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": "Hello?"
                            }
                        ]
                    }
                ],
                "turnComplete": True
            }
        }
        await gem.send(json.dumps(silence_nudge))
        
        # Read response for Turn 1 (silence)
        try:
            async def read_silence():
                nonlocal silence_response_text
                async for raw in gem:
                    logger.info(f"Raw silence message: {raw[:300]}")
                    obj = json.loads(raw) if isinstance(raw, str) else json.loads(raw.decode("utf-8"))
                    await handle_tool_calls(gem, obj)
                    sc = obj.get("serverContent") or {}
                    out_tx = sc.get("outputTranscription") or obj.get("outputTranscription") or {}
                    if out_tx.get("text"):
                        txt = out_tx.get("text")
                        silence_response_text += txt
                        logger.info(f"Silence response chunk: {txt!r}")
                    if sc.get("turnComplete") or sc.get("generationComplete"):
                        logger.info("Silence turn complete detected in read_silence loop")
                        break
            
            await asyncio.wait_for(read_silence(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("Timeout waiting for silence response")
            
        # Stop background silence task
        stop_silence.set()
        await silence_task
        
        # Verify Silence Nudge Response
        low_text = silence_response_text.lower()
        if "hello" in low_text or "there" in low_text or "hear" in low_text or "सुन" in low_text or "आवाज़" in low_text or "वहाँ" in low_text:
            silence_success = True
            logger.info("SUCCESS: Silence nudge response detected!")
            
    return {
        "silence_success": silence_success,
        "silence_response": silence_response_text
    }

async def main():
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(backend_dir, "data")
    
    init_db(data_dir)
    init_state()
    sync_all_role_sandboxes_on_startup()
    
    roles = ["sellers", "buyers", "rfqs"]
    report = {}
    
    for role in roles:
        role_results = []
        for attempt in range(1, 3):  # Only test 2 times per role as requested
            try:
                res = await test_role_once(role, attempt)
                role_results.append(res)
            except Exception as e:
                logger.error(f"Error testing {role} on attempt {attempt}: {e}")
                role_results.append({
                    "silence_success": False,
                    "error": str(e)
                })
            await asyncio.sleep(2)
        report[role] = role_results
        
    print("\n" + "="*50)
    print("VERIFICATION REPORT")
    print("="*50)
    for role, results in report.items():
        print(f"\nRole: {role.upper()}")
        for i, res in enumerate(results, 1):
            silence_status = "PASSED" if res.get("silence_success") else "FAILED"
            err = f" (Error: {res['error']})" if "error" in res else ""
            print(f"  Attempt {i}: Silence Rule={silence_status}{err}")
            if "error" not in res:
                print(f"    - Silence Output: {res['silence_response'].strip() or '[Empty]'}")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(main())
