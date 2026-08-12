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


if __name__ == "__main__":
    unittest.main(verbosity=2)
