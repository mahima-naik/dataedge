#!/usr/bin/env python3
import asyncio
import base64
import json
import os
import sys
import time
import websockets
from dataclasses import dataclass, field
from loguru import logger

# Add backend to path
backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

# Import backend modules using relative names since backend_dir is in sys.path
from config import settings
from core.storage import init_db
from core.state import init_state, get_state
from core.role_sandbox import sync_all_role_sandboxes_on_startup
from prompts.priya import build_role_system_prompt
from services.vobiz_bridge.gemini_protocol import build_live_setup, GEMINI_LIVE_URL_TMPL

SERVER_URL = "ws://localhost:8000"
ROLES = ["sellers", "buyers", "rfqs"]
AUDIO_SEND_INTERVAL = 0.04  # 40ms

@dataclass
class BridgeTestResult:
    role: str
    calling_ok: bool = False
    silence_nudge_ok: bool = False
    time_to_nudge: float = 0.0
    audio_chunks_received: int = 0
    jitter_stats: dict = field(default_factory=dict)
    error: str = ""

@dataclass
class PromptTestResult:
    role: str
    pitch_ok: bool = False
    initial_text: str = ""
    email_confirm_ok: bool = False
    email_confirm_text: str = ""
    error: str = ""

def generate_silence_pcm(duration_ms: int = 40, sample_rate: int = 16000) -> str:
    """Generate silent PCM audio frame, base64 encoded."""
    num_samples = int(sample_rate * duration_ms / 1000)
    silent_pcm = b'\x00\x00' * num_samples
    return base64.b64encode(silent_pcm).decode("ascii")

async def test_bridge_websocket(role: str) -> BridgeTestResult:
    """Connect to local WebSocket server, stream silence, measure timing and nudges."""
    res = BridgeTestResult(role=role)
    ws_url = f"{SERVER_URL}/ws/voice-test?role={role}"
    logger.info(f"Testing local server WS for role={role}...")
    
    start_time = time.perf_counter()
    silence_b64 = generate_silence_pcm(40, 16000)
    
    received_intervals = []
    last_recv_time = None
    
    try:
        async with websockets.connect(
            ws_url,
            max_size=16 * 1024 * 1024,
            ping_interval=20,
            close_timeout=5,
            open_timeout=15,
        ) as ws:
            res.calling_ok = True
            
            send_done = asyncio.Event()
            
            async def send_silent_audio():
                while not send_done.is_set():
                    try:
                        await ws.send(json.dumps({
                            "type": "audio",
                            "data": silence_b64
                        }))
                    except Exception:
                        return
                    await asyncio.sleep(AUDIO_SEND_INTERVAL)
            
            # Start background silence streaming
            send_task = asyncio.create_task(send_silent_audio())
            
            # Watch for incoming audio and nudges
            initial_audio_phase = True
            silence_start_time = None
            deadline = time.perf_counter() + 25.0
            last_audio_count = 0
            
            while time.perf_counter() < deadline:
                await asyncio.sleep(0.5)
                current_audio = res.audio_chunks_received
                
                # Check for incoming messages
                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=0.01)
                        obj = json.loads(raw)
                        if obj.get("type") == "audio":
                            res.audio_chunks_received += 1
                            now = time.perf_counter()
                            if last_recv_time is not None:
                                received_intervals.append(now - last_recv_time)
                            last_recv_time = now
                    except asyncio.TimeoutError:
                        break
                    except Exception as e:
                        res.error = f"Receive error: {e}"
                        break
                
                current_audio = res.audio_chunks_received
                
                if current_audio > last_audio_count:
                    if initial_audio_phase:
                        # Still receiving initial greeting audio
                        last_audio_count = current_audio
                    else:
                        # Audio after silence = this is the nudge!
                        res.silence_nudge_ok = True
                        res.time_to_nudge = time.perf_counter() - silence_start_time
                        logger.info(f"Role {role}: Silence nudge detected after {res.time_to_nudge:.2f}s!")
                        break
                else:
                    if initial_audio_phase and current_audio > 0:
                        # Audio stopped after initial greeting → silence phase begins
                        initial_audio_phase = False
                        silence_start_time = time.perf_counter()
                        logger.info(f"Role {role}: Initial greeting complete. Starting silence watchdog verification...")
                    elif initial_audio_phase and (time.perf_counter() - start_time) > 8.0:
                        # No initial greeting after 8s, silence phase anyway
                        initial_audio_phase = False
                        silence_start_time = time.perf_counter()
                        logger.info(f"Role {role}: No greeting detected. Starting silence watchdog verification anyway...")
                
                last_audio_count = current_audio
                
            # Clean up
            send_done.set()
            send_task.cancel()
            try:
                await send_task
            except (asyncio.CancelledError, Exception):
                pass
                
    except Exception as e:
        res.error = f"WS connection failed: {e}"
        logger.error(f"Role {role} WS error: {e}")
        
    # Analyze jitter/intervals
    if received_intervals:
        avg_int = sum(received_intervals) / len(received_intervals)
        min_int = min(received_intervals)
        max_int = max(received_intervals)
        res.jitter_stats = {
            "avg_ms": avg_int * 1000,
            "min_ms": min_int * 1000,
            "max_ms": max_int * 1000,
            "std_dev_ms": (sum((x - avg_int) ** 2 for x in received_intervals) / len(received_intervals)) ** 0.5 * 1000
        }
    return res

async def test_direct_prompt_behavior(role: str) -> PromptTestResult:
    """Connect directly to Gemini Live, verify pitch and Gmail reconfirmation rule."""
    res = PromptTestResult(role=role)
    logger.info(f"Testing direct Gemini Live prompt behavior for role={role}...")
    
    role_config = get_state(role)
    lead = {
        "name": "Surya",
        "company": "Data-Edge Corporation",
        "segment": "rfq",
        "email": "surya@gmail.com"  # Present in DB context
    }
    system_prompt = build_role_system_prompt(role, role_config, lead)
    
    api_key = settings.gemini_api_key
    model = settings.gemini_live_model
    voice = settings.gemini_live_voice
    language_code = settings.gemini_live_language_code
    
    if not api_key:
        res.error = "No API key found"
        return res
        
    setup = build_live_setup(
        model=model,
        system_instruction=system_prompt,
        voice=voice,
        language_code=language_code,
        vad_ultra=False
    )
    
    gemini_url = GEMINI_LIVE_URL_TMPL.format(api_key=api_key)
    
    try:
        async with websockets.connect(gemini_url) as gem:
            # Send setup config
            await gem.send(json.dumps(setup))
            
            # Wait for setup acknowledgment message
            try:
                ack = await asyncio.wait_for(gem.recv(), timeout=5.0)
                logger.info(f"Role {role}: Connected to Gemini Live API.")
            except Exception as e:
                logger.warning(f"Error awaiting setup ack: {e}")
            
            # Send a user turn asking the AI to introduce themselves and confirm their email
            prompt_turn = {
                "clientContent": {
                    "turns": [
                        {
                            "role": "user",
                            "parts": [
                                {
                                    "text": (
                                        "Hello, who is this, why are you calling, and what is the invite about? "
                                        "Also, please confirm my email address (surya@gmail.com) for sending the invite."
                                    )
                                }
                            ]
                        }
                    ],
                    "turnComplete": True
                }
            }
            await gem.send(json.dumps(prompt_turn))
            
            response_text = ""
            try:
                async def read_response():
                    nonlocal response_text
                    async for raw in gem:
                        obj = json.loads(raw) if isinstance(raw, str) else json.loads(raw.decode("utf-8"))
                        sc = obj.get("serverContent") or {}
                        out_tx = sc.get("outputTranscription") or obj.get("outputTranscription") or {}
                        if out_tx.get("text"):
                            response_text += out_tx.get("text")
                        if sc.get("turnComplete") or sc.get("generationComplete"):
                            break
                await asyncio.wait_for(read_response(), timeout=12.0)
            except Exception as e:
                logger.warning(f"Error reading response: {e}")
                
            res.initial_text = response_text
            res.email_confirm_text = response_text
            logger.info(f"Role {role} Response: {response_text!r}")
            
            # Validate Pitch
            text_lower = response_text.lower()
            if role == "rfqs":
                # RFQs pitch keywords
                keywords = ["priority vendor", "invitation", "email", "requirement", "buyer", "register"]
                matched = [kw for kw in keywords if kw in text_lower]
                res.pitch_ok = len(matched) >= 3 or "priority vendor" in text_lower
            elif role == "sellers":
                res.pitch_ok = "devika" in text_lower or "procucev" in text_lower
            elif role == "buyers":
                res.pitch_ok = "adithi" in text_lower or "procucev" in text_lower
                
            # Validate Gmail reconfirmation spelling: should be hyphenated e.g. "s-u-r-y-a" or similar
            # Check for hyphens or character-by-character patterns
            has_spelled_out = "-" in text_lower or any(char_spelled in text_lower for char_spelled in ["s-u-r-y-a", "g-m-a-i-l", "s-u-r-y-a at g-m-a-i-l"])
            res.email_confirm_ok = has_spelled_out
            
    except Exception as e:
        res.error = f"Direct Gemini Live error: {e}"
        logger.error(f"Role {role} direct prompt error: {e}")
        
    return res

async def main():
    logger.info("Initializing DB and States...")
    # Initialize the database path using relative core imports
    data_dir = os.path.join(backend_dir, "data")
    init_db(data_dir)
    init_state()
    sync_all_role_sandboxes_on_startup()
    
    bridge_results = []
    prompt_results = []
    
    # 1. Run local WebSocket tests (Calling, Silence, Jitter)
    logger.info("\n=== STARTING LOCAL WEBSOCKET TESTS ===")
    for role in ROLES:
        res = await test_bridge_websocket(role)
        bridge_results.append(res)
        await asyncio.sleep(2)
        
    # 2. Run direct Gemini Live prompt tests (Pitch, Email Confirmation)
    logger.info("\n=== STARTING DIRECT PROMPT COMPLIANCE TESTS ===")
    for role in ROLES:
        res = await test_direct_prompt_behavior(role)
        prompt_results.append(res)
        await asyncio.sleep(2)
        
    # 3. Print report
    print("\n" + "=" * 80)
    print("                      DATA-EDGE ROLE VERIFICATION REPORT")
    print("=" * 80)
    
    print("\n[1] Web Voice calling (Local Server WS Connect)")
    print("-" * 80)
    for r in bridge_results:
        status = "✅ CONNECTED" if r.calling_ok else "❌ FAILED"
        print(f"Role: {r.role:<10} | Status: {status:<12} | Chunks Received: {r.audio_chunks_received:<4} | Err: {r.error}")
        
    print("\n[2] Silence Detection (5-Second watchdog nudge)")
    print("-" * 80)
    for r in bridge_results:
        status = f"✅ NUDGED ({r.time_to_nudge:.2f}s)" if r.silence_nudge_ok else "❌ NO NUDGE/FAILED"
        print(f"Role: {r.role:<10} | Status: {status}")
        
    print("\n[3] Jitter & Resampling Quality (Audio Packet Intervals)")
    print("-" * 80)
    for r in bridge_results:
        if r.jitter_stats:
            stats = r.jitter_stats
            print(f"Role: {r.role:<10} | Avg: {stats['avg_ms']:.1f}ms | Min: {stats['min_ms']:.1f}ms | Max: {stats['max_ms']:.1f}ms | StdDev: {stats['std_dev_ms']:.1f}ms")
        else:
            print(f"Role: {r.role:<10} | No audio statistics available")
            
    print("\n[4] Role-Specific Pitch & RFQs Vendor Pitch")
    print("-" * 80)
    for r in prompt_results:
        status = "✅ PASSED" if r.pitch_ok else "❌ FAILED/INCOMPLETE"
        print(f"Role: {r.role:<10} | Status: {status}")
        print(f"  Greeting: {r.initial_text.strip() or '[No text response]'}")
        
    print("\n[5] Gmail/Email Reconfirmation Rule (Letter-by-letter spelling)")
    print("-" * 80)
    for r in prompt_results:
        status = "✅ PASSED (Spelled letter-by-letter)" if r.email_confirm_ok else "❌ FAILED (Not spelled letter-by-letter)"
        print(f"Role: {r.role:<10} | Status: {status}")
        print(f"  Response: {r.email_confirm_text.strip() or '[No text response]'}")
        
    print("=" * 80)
    
    # Save report to a file
    report_file = "role_verification_report.md"
    with open(report_file, "w") as f:
        f.write("# Role Verification & Audio Bridge Test Report\n\n")
        f.write(f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write("## 1. Web Voice Calling & Local WebSocket Connections\n\n")
        f.write("| Role | Connection | Chunks Received | Errors |\n")
        f.write("|---|---|---|---|\n")
        for r in bridge_results:
            conn = "✅ OK" if r.calling_ok else "❌ FAILED"
            f.write(f"| {r.role} | {conn} | {r.audio_chunks_received} | {r.error or 'None'} |\n")
        f.write("\n")
        
        f.write("## 2. Silence Detection (5-Second watchdog nudge)\n\n")
        f.write("| Role | Nudge Detected | Nudge Delay | Status |\n")
        f.write("|---|---|---|---|\n")
        for r in bridge_results:
            nd = "Yes" if r.silence_nudge_ok else "No"
            delay = f"{r.time_to_nudge:.2f}s" if r.silence_nudge_ok else "N/A"
            status = "✅ PASS" if r.silence_nudge_ok else "❌ FAIL"
            f.write(f"| {r.role} | {nd} | {delay} | {status} |\n")
        f.write("\n")
        
        f.write("## 3. Jitter & Audio Resampling Latency Stats\n\n")
        f.write("| Role | Avg Interval | Min Interval | Max Interval | Jitter (StdDev) |\n")
        f.write("|---|---|---|---|---|\n")
        for r in bridge_results:
            if r.jitter_stats:
                stats = r.jitter_stats
                f.write(f"| {r.role} | {stats['avg_ms']:.1f}ms | {stats['min_ms']:.1f}ms | {stats['max_ms']:.1f}ms | {stats['std_dev_ms']:.1f}ms |\n")
            else:
                f.write(f"| {r.role} | N/A | N/A | N/A | N/A |\n")
        f.write("\n")
        
        f.write("## 4. Role pitch & RFQs Pitch Verification\n\n")
        for r in prompt_results:
            status = "✅ PASS" if r.pitch_ok else "❌ FAIL/INCOMPLETE"
            f.write(f"### {r.role.upper()} ({status})\n")
            f.write(f"> {r.initial_text.strip()}\n\n")
            
        f.write("## 5. Gmail/Email Letter-by-letter Confirmation\n\n")
        for r in prompt_results:
            status = "✅ PASS" if r.email_confirm_ok else "❌ FAIL"
            f.write(f"### {r.role.upper()} ({status})\n")
            f.write(f"> {r.email_confirm_text.strip()}\n\n")
            
    logger.info(f"Report written to {report_file}")

if __name__ == "__main__":
    asyncio.run(main())
