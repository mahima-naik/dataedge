"""Per-call turn-tagged jitter/playout buffer.

The resampled 16 kHz Gemini audio is fed into this buffer tagged with the
model-turn id it belongs to. The mixer pops fixed 20 ms (640 byte) chunks from
the front at the playout rate. On a barge-in the current turn is marked
invalid and *only* audio belonging to that turn (and any older, unplayed turn)
is purged — the next turn's audio stays queued, so there is no global queue
wipe and no ghost syllables from stale old-turn packets.
"""

from __future__ import annotations

from collections import deque


class TurnTaggedJitterBuffer:
    """A FIFO of ``(turn_id, bytearray)`` segments consumed at a fixed rate.

    Internal representation keeps whole segments but the public ``pop_chunk``
    consumes a continuous stream of bytes across segment boundaries, so the
    mixer always gets exactly ``n`` bytes regardless of how Gemini framed them.
    """

    def __init__(self, sr: int = 16000, bytes_per_sample: int = 2) -> None:
        self._sr = sr
        self._bps = bytes_per_sample
        self._segments: deque = deque()
        self._total_bytes = 0
        self._min_depth = 0
        self._max_depth = 0

    # -- writers --

    def append(self, turn_id: int, data: bytes) -> None:
        if not data:
            return
        self._segments.append((turn_id, bytearray(data)))
        self._total_bytes += len(data)
        if self._total_bytes > self._max_depth:
            self._max_depth = self._total_bytes

    # -- readers --

    def byte_len(self) -> int:
        return self._total_bytes

    def depth_ms(self) -> float:
        return self._total_bytes / (self._sr * self._bps) * 1000.0

    def min_depth(self) -> int:
        return self._min_depth

    def max_depth(self) -> int:
        return self._max_depth

    def _track_depth(self) -> None:
        if self._min_depth == 0 or self._total_bytes < self._min_depth:
            self._min_depth = self._total_bytes

    def pop_chunk(self, n_bytes: int) -> tuple:
        """Pop exactly ``n_bytes`` from the front, returning ``(turn_id, pcm)``.

        ``turn_id`` is the id of the front-most segment consumed. If the buffer
        is empty, returns ``(-1, b"")``.
        """
        if self._total_bytes == 0:
            return -1, b""
        out = bytearray()
        front_turn = self._segments[0][0]
        while len(out) < n_bytes and self._segments:
            turn, seg = self._segments[0]
            need = n_bytes - len(out)
            if len(seg) <= need:
                out.extend(seg)
                self._segments.popleft()
            else:
                out.extend(seg[:need])
                del seg[:need]
                front_turn = turn
        self._total_bytes -= len(out)
        self._track_depth()
        return front_turn, bytes(out)

    # -- invalidation --

    def purge_before(self, turn_id: int) -> int:
        """Remove all segments whose turn_id is <= ``turn_id`` (the interrupted/

        stale turn and anything older). Returns the number of bytes dropped so
        the caller can count discarded audio and attribute it to a turn.
        """
        dropped = 0
        while self._segments and self._segments[0][0] <= turn_id:
            _, seg = self._segments.popleft()
            dropped += len(seg)
        self._total_bytes -= dropped
        self._track_depth()
        return dropped

    def clear(self) -> None:
        self._segments.clear()
        self._total_bytes = 0
        self._track_depth()

    def __len__(self) -> int:
        return self._total_bytes
