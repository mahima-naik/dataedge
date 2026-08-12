"""Bounded capture buffer for inbound (caller) audio during setup/greeting.

Problem solved (spec #11 / #12): the bridge used to *drop* caller audio while
Gemini's ``setupComplete`` had not arrived and while the scripted greeting was
playing. That lost the callee's first "hello?" / response and made the call
behave as if it were deaf.

This buffer accumulates a bounded amount of recent inbound audio and replays it
once the forwarding gates open (setupComplete received AND greeting finished),
so the callee's early speech is not lost. It is time-bounded so we never feed
Gemini an unbounded/ancient backlog (which would cause a barge-in storm).
"""

from __future__ import annotations

from collections import deque


class InboundCaptureBuffer:
    def __init__(self, max_ms: float = 2500.0, sr: int = 16000, bytes_per_sample: int = 2) -> None:
        self._max_bytes = int(max_ms / 1000.0 * sr * bytes_per_sample)
        self._buf: deque = deque()  # (perf_ts, b64_payload)
        self._total_bytes = 0
        self._dropped = 0
        self._captured = 0

    def append(self, ts: float, b64_payload: str) -> None:
        # estimate byte cost from base64 length (4 chars -> 3 bytes, ignore padding)
        n = max(0, (len(b64_payload) * 3) // 4 - 1)
        if n <= 0:
            return
        self._buf.append((ts, b64_payload))
        self._total_bytes += n
        self._captured += 1
        while self._total_bytes > self._max_bytes and self._buf:
            _, old = self._buf.popleft()
            old_n = max(0, (len(old) * 3) // 4 - 1)
            self._total_bytes -= old_n
            self._dropped += 1

    def is_empty(self) -> bool:
        return not self._buf

    def drain(self) -> list:
        """Return captured frames in order and reset the buffer."""
        out = [frame for _, frame in self._buf]
        self._buf.clear()
        self._total_bytes = 0
        return out

    def captured_count(self) -> int:
        return self._captured

    def dropped_count(self) -> int:
        return self._dropped
