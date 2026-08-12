"""Structured per-call diagnostics for the Vernika voice bridge.

This module is intentionally dependency-light (stdlib only) and is updated
exclusively from the asyncio event loop thread, so no locking is required.

It provides:

* ``CallMetrics`` — a per-call metrics accumulator matching the diagnostic
  contract in the optimisation spec (mixer tick lateness, underruns, send
  latency, queue depth/drops, Gemini gaps, VAD events, recording, plus the
  global event-loop lag / CPU / memory read from the shared monitors).
* ``TickScheduler`` — a monotonic-clock 20 ms pacing helper that measures
  lateness and resyncs after stalls *without* emitting catch-up audio (which
  would otherwise play the call at >1x speed).
* Global monitors for event-loop lag and CPU/RAM.

Diagnostics log aggregated values only — never audio content.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import Optional


_logger = None


def _log():
    global _logger
    if _logger is None:
        from loguru import logger as _l

        _logger = _l
    return _logger


# ---------------------------------------------------------------------------
# Global monitors (event-loop lag + CPU/RAM). Started once per event loop.
# ---------------------------------------------------------------------------

_loop_lag_ms: float = 0.0  # decaying max loop lag
_cpu_usage: Optional[float] = None
_mem_usage_mb: Optional[float] = None

_LOOP_LAG_DECAY = 0.92
_MONITOR_STARTED: set[int] = set()  # keyed by id(asyncio.get_event_loop())


def _try_psutil():
    try:
        import psutil  # type: ignore

        return psutil
    except Exception:
        return None


def loop_lag_ms() -> float:
    """Return the current decaying-max event-loop lag (ms)."""
    return _loop_lag_ms


def ensure_monitors() -> None:
    """Start the loop-lag and CPU/RAM probes exactly once per event loop."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return
    key = id(loop)
    if key in _MONITOR_STARTED:
        return
    _MONITOR_STARTED.add(key)

    def _schedule_probe() -> None:
        try:
            target = loop.time() + 0.05

            def _probe() -> None:
                global _loop_lag_ms
                lag = (loop.time() - target) * 1000.0
                # Decaying max: keeps a recent worst-case visible without a
                # single ancient spike dominating forever.
                _loop_lag_ms = max(_loop_lag_ms * _LOOP_LAG_DECAY, lag)
                _schedule_probe()

            loop.call_later(0.05, _probe)
        except Exception:
            pass

    _schedule_probe()

    psutil = _try_psutil()

    async def _resource_monitor() -> None:
        while True:
            try:
                await asyncio.sleep(1.0)
                if psutil is not None:
                    global _cpu_usage, _mem_usage_mb
                    _cpu_usage = float(psutil.cpu_percent(interval=None))
                    proc = psutil.Process(os.getpid())
                    _mem_usage_mb = float(proc.memory_info().rss) / (1024.0 * 1024.0)
            except asyncio.CancelledError:
                return
            except Exception:
                pass

    loop.create_task(_resource_monitor())


# ---------------------------------------------------------------------------
# Pacing
# ---------------------------------------------------------------------------


class TickScheduler:
    """Monotonic 20 ms wall-clock pacing.

    Each ``tick`` returns ``(lateness_ms, sleep_seconds)``. The caller always
    emits exactly *one* 20 ms audio chunk and then sleeps for ``sleep_seconds``.

    After a stall (``now`` past the scheduled time) we resync ``next_wake`` to
    ``now + period`` rather than trying to catch up by emitting extra chunks.
    Emitting extra chunks would compress time and play the call faster than
    real-time (the 1.5x / 1.7x bug the spec explicitly forbids). The unavoidable
    consequence of a stall is a brief gap at the caller side — the real fix is to
    stop the stall (loop isolation), which is handled elsewhere.
    """

    def __init__(self, period: float = 0.020) -> None:
        self.period = period
        self.next_wake: Optional[float] = None
        self.late_count: int = 0
        self.max_late_ms: float = 0.0
        self.sum_late_ms: float = 0.0
        self.total_ticks: int = 0

    def init(self, now: Optional[float] = None) -> None:
        if now is None:
            now = time.perf_counter()
        self.next_wake = now + self.period

    def tick(self, now: Optional[float] = None) -> tuple[float, float]:
        if now is None:
            now = time.perf_counter()
        if self.next_wake is None:
            self.init(now)
            return 0.0, self.period
        sched = self.next_wake
        late = (now - sched) * 1000.0
        if late > 2.0:
            self.late_count += 1
            if late > self.max_late_ms:
                self.max_late_ms = late
            self.sum_late_ms += late
        self.total_ticks += 1
        if now <= sched:
            sleep = sched - now
            self.next_wake = sched + self.period
        else:
            # Stalled: resync to wall clock, no catch-up emission.
            sleep = 0.0
            self.next_wake = now + self.period
        return late, sleep


# ---------------------------------------------------------------------------
# Per-call metrics
# ---------------------------------------------------------------------------


@dataclass
class CallMetrics:
    session_id: str = ""
    role: str = ""
    camp_id: Optional[str] = None

    # Mixer pacing
    mixer_late_count: int = 0
    mixer_max_late_ms: float = 0.0
    mixer_sum_late_ms: float = 0.0
    mixer_total_ticks: int = 0

    # Underruns
    underrun_count: int = 0
    underrun_duration_ms: float = 0.0

    # Vobiz send
    send_count: int = 0
    send_latency_sum_ms: float = 0.0
    send_latency_max_ms: float = 0.0
    send_failures: int = 0

    # Outbound queue
    out_queue_depth: int = 0
    out_queue_max_depth: int = 0
    out_queue_drop_count: int = 0

    # Jitter buffer depth (bytes)
    jb_depth_min_bytes: int = 0
    jb_depth_max_bytes: int = 0

    # Gemini delivery
    gemini_gap_sum_ms: float = 0.0
    gemini_gap_max_ms: float = 0.0
    gemini_gap_count: int = 0
    _last_gemini_audio_t: float = 0.0

    # VAD / turn
    vad_activity_start: int = 0
    vad_activity_end: int = 0
    vad_interruption_count: int = 0
    vad_false_interruption_count: int = 0

    # Recording
    recording_queue_depth: int = 0
    recording_drop_count: int = 0

    started_at: float = field(default_factory=time.perf_counter)
    _reporter_task: Optional[asyncio.Task] = field(default=None, repr=False)

    # ----- mutators -----

    def note_tick(self, late_ms: float) -> None:
        self.mixer_total_ticks += 1
        if late_ms > 2.0:
            self.mixer_late_count += 1
            if late_ms > self.mixer_max_late_ms:
                self.mixer_max_late_ms = late_ms
            self.mixer_sum_late_ms += late_ms

    def note_underrun(self, duration_ms: float) -> None:
        self.underrun_count += 1
        self.underrun_duration_ms += duration_ms

    def note_send(self, latency_ms: float, ok: bool) -> None:
        self.send_count += 1
        if ok:
            self.send_latency_sum_ms += latency_ms
            if latency_ms > self.send_latency_max_ms:
                self.send_latency_max_ms = latency_ms
        else:
            self.send_failures += 1

    def note_out_queue_depth(self, depth: int) -> None:
        self.out_queue_depth = depth
        if depth > self.out_queue_max_depth:
            self.out_queue_max_depth = depth

    def note_out_queue_drop(self, count: int = 1) -> None:
        self.out_queue_drop_count += count

    def note_jb_depth(self, depth_bytes: int) -> None:
        if self.jb_depth_min_bytes == 0 or depth_bytes < self.jb_depth_min_bytes:
            self.jb_depth_min_bytes = depth_bytes
        if depth_bytes > self.jb_depth_max_bytes:
            self.jb_depth_max_bytes = depth_bytes

    def note_gemini_audio(self, now: Optional[float] = None) -> None:
        now = time.perf_counter() if now is None else now
        if self._last_gemini_audio_t > 0.0:
            gap = (now - self._last_gemini_audio_t) * 1000.0
            if gap >= 25.0:
                self.gemini_gap_sum_ms += gap
                if gap > self.gemini_gap_max_ms:
                    self.gemini_gap_max_ms = gap
                self.gemini_gap_count += 1
        self._last_gemini_audio_t = now

    def note_vad_start(self) -> None:
        self.vad_activity_start += 1

    def note_vad_end(self) -> None:
        self.vad_activity_end += 1

    def note_interruption(self, is_false: bool = False) -> None:
        self.vad_interruption_count += 1
        if is_false:
            self.vad_false_interruption_count += 1

    def set_recording_depth(self, depth: int) -> None:
        self.recording_queue_depth = depth

    def note_recording_drop(self, count: int = 1) -> None:
        self.recording_drop_count += count

    # ----- reporting -----

    def snapshot(self) -> dict:
        avg_late = (self.mixer_sum_late_ms / self.mixer_late_count) if self.mixer_late_count else 0.0
        avg_send = (self.send_latency_sum_ms / self.send_count) if self.send_count else 0.0
        avg_gap = (self.gemini_gap_sum_ms / self.gemini_gap_count) if self.gemini_gap_count else 0.0
        return {
            "session_id": self.session_id,
            "role": self.role,
            "camp_id": self.camp_id,
            "mixer_tick_late_count": self.mixer_late_count,
            "mixer_max_tick_lateness_ms": round(self.mixer_max_late_ms, 1),
            "mixer_avg_tick_lateness_ms": round(avg_late, 1),
            "mixer_total_ticks": self.mixer_total_ticks,
            "audio_underrun_count": self.underrun_count,
            "audio_underrun_duration_ms": round(self.underrun_duration_ms, 0),
            "vobiz_send_count": self.send_count,
            "vobiz_send_latency_avg_ms": round(avg_send, 1),
            "vobiz_send_latency_max_ms": round(self.send_latency_max_ms, 1),
            "vobiz_send_failures": self.send_failures,
            "outbound_queue_depth": self.out_queue_depth,
            "outbound_queue_max_depth": self.out_queue_max_depth,
            "outbound_queue_drop_count": self.out_queue_drop_count,
            "jb_depth_min_bytes": self.jb_depth_min_bytes,
            "jb_depth_max_bytes": self.jb_depth_max_bytes,
            "gemini_audio_gap_avg_ms": round(avg_gap, 1),
            "gemini_audio_gap_max_ms": round(self.gemini_gap_max_ms, 1),
            "vad_activity_start": self.vad_activity_start,
            "vad_activity_end": self.vad_activity_end,
            "vad_interruption_count": self.vad_interruption_count,
            "vad_false_interruption_count": self.vad_false_interruption_count,
            "recording_queue_depth": self.recording_queue_depth,
            "recording_drop_count": self.recording_drop_count,
            "event_loop_lag_ms": round(_loop_lag_ms, 1),
            "cpu_usage": _cpu_usage,
            "memory_usage_mb": round(_mem_usage_mb, 1) if _mem_usage_mb else None,
        }

    def summary_line(self) -> str:
        s = self.snapshot()
        return (
            "METRICS session={} role={} camp={} | "
            "tick_late={}(max {}/avg {}) total={} | "
            "underrun={}({:.0f}ms) | "
            "send={}(avg {}/max {}/fail {}) | "
            "outq depth={}/max={}/drop={} | "
            "jb min={}/max={}B | "
            "gemini_gap avg {}/max {} | "
            "vad start={}/end={}/interrupt={}(false {}) | "
            "rec drop={} | loop_lag={}ms cpu={} mem={}MB"
        ).format(
            s["session_id"], s["role"], s["camp_id"],
            s["mixer_tick_late_count"], s["mixer_max_tick_lateness_ms"],
            s["mixer_avg_tick_lateness_ms"], s["mixer_total_ticks"],
            s["audio_underrun_count"], s["audio_underrun_duration_ms"],
            s["vobiz_send_count"], s["vobiz_send_latency_avg_ms"],
            s["vobiz_send_latency_max_ms"], s["vobiz_send_failures"],
            s["outbound_queue_depth"], s["outbound_queue_max_depth"], s["outbound_queue_drop_count"],
            s["jb_depth_min_bytes"], s["jb_depth_max_bytes"],
            s["gemini_audio_gap_avg_ms"], s["gemini_audio_gap_max_ms"],
            s["vad_activity_start"], s["vad_activity_end"],
            s["vad_interruption_count"], s["vad_false_interruption_count"],
            s["recording_drop_count"], s["event_loop_lag_ms"],
            s["cpu_usage"], s["memory_usage_mb"],
        )

    def start_reporter(self, interval: float = 10.0) -> None:
        ensure_monitors()

        async def _report() -> None:
            while True:
                try:
                    await asyncio.sleep(interval)
                    _log().info("CALL-METRICS " + self.summary_line())
                except asyncio.CancelledError:
                    return
                except Exception as exc:  # noqa: BLE001
                    _log().debug("metrics reporter error: {}", exc)

        try:
            self._reporter_task = asyncio.create_task(_report(), name="metrics_reporter")
        except RuntimeError:
            self._reporter_task = None

    def stop_reporter(self) -> None:
        if self._reporter_task is not None and not self._reporter_task.done():
            self._reporter_task.cancel()

    def finalize(self) -> None:
        self.stop_reporter()
        _log().info("CALL-METRICS-END " + self.summary_line())
