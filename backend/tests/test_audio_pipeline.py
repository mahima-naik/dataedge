"""
Unit tests for the audio pipeline refactor (spec #9 / #11 / #12 / #16):

  - TurnTaggedJitterBuffer: turn-tagged pull, partial pop, stale-turn purge
  - InboundCaptureBuffer: bounded capture, replay drain, drop accounting
  - TickScheduler: monotonic 20 ms pacing with NO catch-up (no >1x playback)
  - resample_24k_to_16k_numpy: length + energy sanity
  - CallMetrics: Gemini gap accounting + finalize
"""

import base64
import math
import sys
import time
import unittest

sys.path.insert(0, "backend")

from services.vobiz_bridge.jitter_buffer import TurnTaggedJitterBuffer
from services.vobiz_bridge.capture_buffer import InboundCaptureBuffer
from services.vobiz_bridge.call_metrics import TickScheduler, CallMetrics
from services.vobiz_bridge import audio as A


def _b64(n_bytes: int) -> str:
    return base64.b64encode(b"x" * n_bytes).decode()


class TestTurnTaggedJitterBuffer(unittest.TestCase):
    def setUp(self):
        self.jb = TurnTaggedJitterBuffer()

    def test_append_pop_returns_turn_id(self):
        self.jb.append(3, b"abcd")
        tid, chunk = self.jb.pop_chunk(4)
        self.assertEqual(tid, 3)
        self.assertEqual(chunk, b"abcd")
        self.assertEqual(self.jb.byte_len(), 0)

    def test_pop_partial_returns_available_bytes(self):
        self.jb.append(1, b"abcd")
        # Not enough bytes for a full 10-byte chunk -> returns what is available.
        tid, chunk = self.jb.pop_chunk(10)
        self.assertEqual(tid, 1)
        self.assertEqual(chunk, b"abcd")
        self.assertEqual(self.jb.byte_len(), 0)

    def test_purge_before_drops_stale_turn(self):
        # Turn 1 (stale, interrupted) followed by turn 2 (current).
        self.jb.append(1, b"aaaa")
        self.jb.append(2, b"bbbb")
        dropped = self.jb.purge_before(1)
        self.assertEqual(dropped, 4)
        # Only turn 2 remains and is popped with its own id.
        tid, chunk = self.jb.pop_chunk(4)
        self.assertEqual(tid, 2)
        self.assertEqual(chunk, b"bbbb")

    def test_byte_len_across_segments(self):
        self.jb.append(1, b"abcd")
        self.jb.append(2, b"efgh")
        self.assertEqual(self.jb.byte_len(), 8)
        tid, chunk = self.jb.pop_chunk(8)
        self.assertEqual(tid, 1)
        self.assertEqual(chunk, b"abcdefgh")


class TestInboundCaptureBuffer(unittest.TestCase):
    def test_append_and_drain(self):
        cb = InboundCaptureBuffer(max_ms=2500)
        cb.append(0.0, _b64(100))
        cb.append(0.02, _b64(100))
        self.assertEqual(cb.captured_count(), 2)
        self.assertFalse(cb.is_empty())
        frames = cb.drain()
        self.assertEqual(len(frames), 2)
        self.assertTrue(cb.is_empty())

    def test_bounded_drop_when_over_max(self):
        # max_ms=50ms @16k*2 = 1600 bytes capacity.
        cb = InboundCaptureBuffer(max_ms=50)
        big = _b64(2000)  # ~1500 bytes decoded, exceeds capacity immediately
        cb.append(0.0, big)
        cb.append(0.02, big)
        # Once capacity is exceeded the oldest frames are dropped.
        self.assertGreater(cb.dropped_count(), 0)

    def test_empty_drain(self):
        cb = InboundCaptureBuffer()
        self.assertEqual(cb.drain(), [])


class TestTickScheduler(unittest.TestCase):
    def test_init_then_on_time_tick(self):
        ts = TickScheduler(period=0.020)
        t0 = 1000.0
        ts.init(t0)
        # Tick well before next_wake (t0+0.02): late negative, sleep ~0.02.
        late, sleep = ts.tick(t0)
        self.assertLess(abs(late), 25.0)
        self.assertAlmostEqual(sleep, 0.020, places=4)

    def test_no_catch_up_after_stall(self):
        ts = TickScheduler(period=0.020)
        t0 = 1000.0
        ts.init(t0)
        # Big stall: 3 periods late.
        late, sleep = ts.tick(t0 + 0.060)
        self.assertAlmostEqual(late, 40.0, places=1)
        self.assertEqual(sleep, 0.0)  # never try to catch up
        # next_wake resynced to wall clock + period, not sched + period.
        self.assertAlmostEqual(ts.next_wake, t0 + 0.060 + 0.020, places=6)

    def test_first_tick_initialises(self):
        ts = TickScheduler(period=0.020)
        late, sleep = ts.tick(500.0)
        self.assertEqual(late, 0.0)
        self.assertAlmostEqual(sleep, 0.020, places=6)


class TestResample(unittest.TestCase):
    def test_resample_length_and_energy(self):
        sr = 24000
        t = [math.sin(2 * math.pi * 440 * i / sr) for i in range(sr)]
        pcm24 = b"".join(int(x * 30000).to_bytes(2, "little", signed=True) for x in t)
        out, _state = A.resample_24k_to_16k_numpy(pcm24)
        # Expected ~ 2 * (16000/24000) * 24000 = 32000 bytes.
        self.assertAlmostEqual(len(out), 32000, delta=400)
        self.assertGreater(abs(sum(out[::200])), 0)


class TestCallMetrics(unittest.TestCase):
    def test_gemini_gap_accounting(self):
        m = CallMetrics(session_id="s", role="agent")
        m.note_gemini_audio(now=1000.0)
        time.sleep(0.03)
        m.note_gemini_audio(now=1000.030)
        self.assertEqual(m.gemini_gap_count, 1)
        self.assertGreater(m.gemini_gap_sum_ms, 25.0)

    def test_finalize_no_error(self):
        m = CallMetrics(session_id="s", role="agent")
        m.note_tick(1.0)
        m.note_underrun(20.0)
        m.note_jb_depth(640)
        # Should not raise even though no reporter was started.
        m.finalize()
        snap = m.snapshot()
        self.assertEqual(snap["session_id"], "s")


class TestCallRecorderTimelineBuilder(unittest.TestCase):
    """Tests for CallRecorder._build_timeline_from_chunks (gap-aware mixing)."""

    def test_empty_chunks_returns_empty(self):
        from services.call_recording import CallRecorder
        result = CallRecorder._build_timeline_from_chunks([], anchor=0.0)
        self.assertEqual(result, b"")

    def test_single_chunk_no_gap(self):
        from services.call_recording import CallRecorder
        # 1 chunk of 320 samples (640 bytes) at anchor time
        pcm = b"\x01\x00" * 320
        chunks = [(0, pcm, 100.0)]
        result = CallRecorder._build_timeline_from_chunks(chunks, anchor=100.0)
        # No lead-in, just the chunk
        self.assertEqual(result, pcm)

    def test_single_chunk_with_lead_in(self):
        from services.call_recording import CallRecorder
        pcm = b"\x01\x00" * 320
        chunks = [(0, pcm, 100.5)]  # arrives 0.5s after anchor
        result = CallRecorder._build_timeline_from_chunks(chunks, anchor=100.0)
        # Should have 0.5s of silence (8000 samples) then the chunk
        expected_lead_bytes = int(0.5 * 16000) * 2  # 16000 bytes
        self.assertEqual(len(result), expected_lead_bytes + len(pcm))
        # First 16000 bytes should be silence
        self.assertEqual(result[:expected_lead_bytes], b"\x00\x00" * (expected_lead_bytes // 2))
        # Then the chunk data
        self.assertEqual(result[expected_lead_bytes:], pcm)

    def test_two_chunks_with_real_gap(self):
        from services.call_recording import CallRecorder
        # Chunk 1: 1s of audio at T=100
        chunk1 = b"\x01\x00" * 16000
        # Chunk 2: 1s of audio at T=102 (1s gap after chunk1 ends)
        chunk2 = b"\x02\x00" * 16000
        chunks = [(0, chunk1, 100.0), (1, chunk2, 102.0)]
        result = CallRecorder._build_timeline_from_chunks(chunks, anchor=100.0)
        # chunk1 duration = 16000 samples / 16000 sr = 1s
        # gap = 102.0 - (100.0 + 1.0) = 1.0s
        # Total: 1s chunk1 + 1s gap + 1s chunk2 = 3s = 96000 bytes
        expected_len = 3 * 16000 * 2
        self.assertEqual(len(result), expected_len)
        # Verify chunk1 is at the start
        self.assertEqual(result[:len(chunk1)], chunk1)
        # Verify gap is silence
        gap_start = len(chunk1)
        gap_end = gap_start + 16000 * 2  # 1s of silence
        self.assertEqual(result[gap_start:gap_end], b"\x00\x00" * 16000)
        # Verify chunk2 is after the gap
        self.assertEqual(result[gap_end:], chunk2)

    def test_two_chunks_no_gap_when_close(self):
        from services.call_recording import CallRecorder
        # Chunk 1: 640 bytes (20ms) at T=100
        chunk1 = b"\x01\x00" * 320
        # Chunk 2: 640 bytes (20ms) at T=100.02 (20ms later, within threshold)
        chunk2 = b"\x02\x00" * 320
        chunks = [(0, chunk1, 100.0), (1, chunk2, 100.02)]
        result = CallRecorder._build_timeline_from_chunks(chunks, anchor=100.0)
        # Gap = 100.02 - (100.0 + 0.02) = 0.0s -> no gap inserted
        self.assertEqual(result, chunk1 + chunk2)

    def test_conversation_interleaving(self):
        from services.call_recording import CallRecorder
        """Simulate a real conversation and verify mixed output interleaves."""
        # T=0: anchor (stream start)
        # T=0.5s: AI greeting (2s of audio)
        greeting = b"\x01\x00" * 32000  # 2s
        # T=3s: user speaks (1s)
        user1 = b"\x02\x00" * 16000  # 1s
        # T=5s: AI responds (2s)
        ai_resp = b"\x03\x00" * 32000  # 2s
        # T=8s: user speaks again (1s)
        user2 = b"\x04\x00" * 16000  # 1s

        out_chunks = [(0, greeting, 0.5), (1, ai_resp, 5.0)]
        in_chunks = [(0, user1, 3.0), (1, user2, 8.0)]

        anchor = 0.0
        out_timeline = CallRecorder._build_timeline_from_chunks(out_chunks, anchor)
        in_timeline = CallRecorder._build_timeline_from_chunks(in_chunks, anchor)

        # Out timeline should be:
        # 0-0.5s: silence (lead-in)
        # 0.5-2.5s: greeting
        # 2.5-5.0s: silence (gap)
        # 5.0-7.0s: ai_resp
        expected_out_len = int(7.0 * 16000) * 2
        self.assertEqual(len(out_timeline), expected_out_len)

        # In timeline should be:
        # 0-3.0s: silence (lead-in)
        # 3.0-4.0s: user1
        # 4.0-8.0s: silence (gap)
        # 8.0-9.0s: user2
        expected_in_len = int(9.0 * 16000) * 2
        self.assertEqual(len(in_timeline), expected_in_len)

        # Verify user1 is NOT at the start (not all-user-first)
        user1_offset = int(3.0 * 16000) * 2
        self.assertEqual(in_timeline[user1_offset:user1_offset + len(user1)], user1)

        # Verify greeting IS at the start (not all-AI-first after user)
        greeting_offset = int(0.5 * 16000) * 2
        self.assertEqual(out_timeline[greeting_offset:greeting_offset + len(greeting)], greeting)


if __name__ == "__main__":
    unittest.main(verbosity=2)
