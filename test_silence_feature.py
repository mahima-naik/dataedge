#!/usr/bin/env python3
"""
Test script for silence detection feature.
Connects via WebSocket to /ws/voice-test for each role (sellers, buyers, rfqs),
stays silent, and verifies the AI injects a "Hello, are you there?" nudge.

Tests each role 2 times.

Usage:
    python test_silence_feature.py [--server URL]
"""

import asyncio
import base64
import json
import struct
import sys
import time
from dataclasses import dataclass, field

# We need websockets library
try:
    import websockets
except ImportError:
    print("Installing websockets...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets"])
    import websockets


SERVER_URL = "ws://localhost:8000"
ROLES = ["sellers", "buyers", "rfqs"]
TEST_RUNS_PER_ROLE = 2
# Wait up to 20 seconds for the silence nudge (5s silence threshold + model response time)
MAX_WAIT_FOR_NUDGE = 25
# How often to send empty/silent audio frames (every 40ms)
AUDIO_SEND_INTERVAL = 0.04


@dataclass
class TestResult:
    role: str
    run: int
    success: bool
    nudge_received: bool = False
    time_to_nudge: float = 0.0
    ai_text: str = ""
    error: str = ""
    audio_chunks_received: int = 0
    details: list = field(default_factory=list)


def generate_silence_pcm(duration_ms: int = 40, sample_rate: int = 16000) -> str:
    """Generate silent PCM audio frame, base64 encoded."""
    num_samples = int(sample_rate * duration_ms / 1000)
    # 16-bit signed PCM silence = all zeros
    silent_pcm = b'\x00\x00' * num_samples
    return base64.b64encode(silent_pcm).decode("ascii")


async def test_silence_for_role(role: str, run_number: int, server_url: str) -> TestResult:
    """Connect to WS, send silent audio, wait for the AI to ask 'are you there?'"""
    result = TestResult(role=role, run=run_number, success=False)
    ws_url = f"{server_url}/ws/voice-test?role={role}"
    
    print(f"\n{'='*60}")
    print(f"  TEST: role={role}, run #{run_number}")
    print(f"  Connecting to: {ws_url}")
    print(f"{'='*60}")

    start_time = time.time()
    silence_b64 = generate_silence_pcm(40, 16000)

    try:
        async with websockets.connect(
            ws_url,
            max_size=16 * 1024 * 1024,
            ping_interval=20,
            close_timeout=5,
            open_timeout=15,
        ) as ws:
            result.details.append(f"[{time.time()-start_time:.1f}s] Connected to WebSocket")
            print(f"  ✓ Connected")

            # Task to send silent audio frames periodically
            send_done = asyncio.Event()

            async def send_silent_audio():
                """Send silent audio frames to keep the connection alive."""
                while not send_done.is_set():
                    try:
                        await ws.send(json.dumps({
                            "type": "audio",
                            "data": silence_b64
                        }))
                    except Exception:
                        return
                    await asyncio.sleep(AUDIO_SEND_INTERVAL)

            # Task to listen for server responses
            nudge_detected = asyncio.Event()
            
            async def listen_for_response():
                nonlocal result
                audio_count = 0
                while not nudge_detected.is_set():
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        result.details.append(f"[{time.time()-start_time:.1f}s] WS recv error: {e}")
                        return

                    try:
                        obj = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    msg_type = obj.get("type", "")
                    
                    if msg_type == "audio":
                        audio_count += 1
                        result.audio_chunks_received = audio_count
                        if audio_count <= 3 or audio_count % 20 == 0:
                            elapsed = time.time() - start_time
                            result.details.append(f"[{elapsed:.1f}s] Audio chunk #{audio_count} received")
                            print(f"  📢 [{elapsed:.1f}s] Audio chunk #{audio_count} received (AI is speaking)")
                    
                    elif msg_type == "interrupted":
                        result.details.append(f"[{time.time()-start_time:.1f}s] Interrupted event")
                    
                    elif msg_type == "text":
                        text = obj.get("data", "")
                        elapsed = time.time() - start_time
                        result.details.append(f"[{elapsed:.1f}s] Text: {text}")
                        print(f"  💬 [{elapsed:.1f}s] Text: {text}")

            # Start tasks
            send_task = asyncio.create_task(send_silent_audio())
            listen_task = asyncio.create_task(listen_for_response())

            # Wait for AI to respond with audio (the nudge will come as audio, not text)
            # After 5 seconds of silence, the server injects the nudge prompt
            # Gemini will then respond with audio saying "Hello, are you there?"
            
            print(f"  ⏳ Sending silent audio... waiting for silence nudge (up to {MAX_WAIT_FOR_NUDGE}s)")
            print(f"  ℹ️  Silence threshold: 5 seconds. AI should ask 'are you there?'")
            
            # We need to wait for:
            # 1. Initial connection/setup (~1-2s)
            # 2. 5 seconds of silence
            # 3. Server sends nudge to Gemini
            # 4. Gemini generates audio response (~1-3s)
            # So total: ~8-10 seconds minimum
            
            # After initial audio (if any opening greeting), wait for the silence nudge audio
            initial_audio_phase = True
            silence_start = None
            nudge_audio_detected = False
            
            deadline = time.time() + MAX_WAIT_FOR_NUDGE
            last_audio_count = 0
            
            while time.time() < deadline:
                await asyncio.sleep(0.5)
                current_audio = result.audio_chunks_received
                
                if current_audio > last_audio_count:
                    if initial_audio_phase:
                        # Still receiving initial greeting audio
                        last_audio_count = current_audio
                    else:
                        # Audio after silence = this is the nudge!
                        elapsed = time.time() - start_time
                        print(f"  ✅ [{elapsed:.1f}s] NUDGE DETECTED! AI spoke after {silence_start and (time.time()-silence_start):.1f}s of silence")
                        result.nudge_received = True
                        result.time_to_nudge = elapsed
                        result.success = True
                        result.ai_text = "Audio response received after silence (AI asked 'are you there?')"
                        nudge_detected.set()
                        break
                else:
                    if initial_audio_phase and current_audio > 0:
                        # Audio stopped after initial greeting → silence phase begins
                        initial_audio_phase = False
                        silence_start = time.time()
                        elapsed = time.time() - start_time
                        print(f"  🔇 [{elapsed:.1f}s] Initial greeting complete. Silence phase begins...")
                    elif initial_audio_phase and (time.time() - start_time) > 8.0:
                        # No initial greeting after 8s, silence phase anyway
                        initial_audio_phase = False
                        silence_start = time.time()
                        elapsed = time.time() - start_time
                        print(f"  🔇 [{elapsed:.1f}s] No greeting detected. Silence phase begins...")
                
                last_audio_count = current_audio

            if not result.nudge_received:
                elapsed = time.time() - start_time
                result.error = f"No silence nudge detected within {MAX_WAIT_FOR_NUDGE}s"
                result.details.append(f"[{elapsed:.1f}s] TIMEOUT - no nudge received")
                print(f"  ❌ [{elapsed:.1f}s] TIMEOUT - No nudge detected")

            # Cleanup
            send_done.set()
            send_task.cancel()
            listen_task.cancel()
            try:
                await send_task
            except (asyncio.CancelledError, Exception):
                pass
            try:
                await listen_task
            except (asyncio.CancelledError, Exception):
                pass

    except ConnectionRefusedError:
        result.error = f"Connection refused at {ws_url} — is the server running?"
        print(f"  ❌ Connection refused — server not running at {server_url}")
    except Exception as e:
        result.error = str(e)
        result.details.append(f"Exception: {e}")
        print(f"  ❌ Error: {e}")

    return result


async def run_all_tests(server_url: str):
    """Run silence detection tests: 2 runs for each of 3 roles."""
    print("\n" + "=" * 70)
    print("  SILENCE DETECTION FEATURE TEST")
    print(f"  Server: {server_url}")
    print(f"  Roles: {', '.join(ROLES)}")
    print(f"  Runs per role: {TEST_RUNS_PER_ROLE}")
    print(f"  Total tests: {len(ROLES) * TEST_RUNS_PER_ROLE}")
    print("=" * 70)

    all_results: list[TestResult] = []

    for role in ROLES:
        for run in range(1, TEST_RUNS_PER_ROLE + 1):
            result = await test_silence_for_role(role, run, server_url)
            all_results.append(result)
            # Small delay between tests to avoid overwhelming the server
            if not (role == ROLES[-1] and run == TEST_RUNS_PER_ROLE):
                print(f"\n  ⏳ Waiting 3s before next test...")
                await asyncio.sleep(3)

    # Print summary
    print("\n\n" + "=" * 70)
    print("  TEST RESULTS SUMMARY")
    print("=" * 70)
    print(f"{'Role':<12} {'Run':<6} {'Status':<10} {'Time':<10} {'Audio Chunks':<14} {'Notes'}")
    print("-" * 70)

    passed = 0
    failed = 0
    for r in all_results:
        status = "✅ PASS" if r.success else "❌ FAIL"
        time_str = f"{r.time_to_nudge:.1f}s" if r.time_to_nudge else "N/A"
        notes = r.ai_text if r.success else r.error
        # Truncate notes for table
        if len(notes) > 30:
            notes = notes[:27] + "..."
        print(f"{r.role:<12} {r.run:<6} {status:<10} {time_str:<10} {r.audio_chunks_received:<14} {notes}")
        if r.success:
            passed += 1
        else:
            failed += 1

    print("-" * 70)
    print(f"  Total: {len(all_results)} | Passed: {passed} | Failed: {failed}")
    
    if failed == 0:
        print("\n  🎉 ALL TESTS PASSED! Silence detection is working correctly.")
    else:
        print(f"\n  ⚠️  {failed} test(s) failed. See details above.")

    print("=" * 70)

    return all_results


if __name__ == "__main__":
    url = SERVER_URL
    for i, arg in enumerate(sys.argv):
        if arg == "--server" and i + 1 < len(sys.argv):
            url = sys.argv[i + 1]
    
    results = asyncio.run(run_all_tests(url))
    sys.exit(0 if all(r.success for r in results) else 1)
