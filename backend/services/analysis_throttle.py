"""Global rate limiter for Gemini analysis API calls.

Ensures we never exceed ~20 requests/minute on the free-tier quota by
enforcing a minimum gap between consecutive Gemini generateContent calls.
"""

from __future__ import annotations

import asyncio
import time

from loguru import logger

_last_gemini_call: float = 0.0
_gemini_lock: asyncio.Lock | None = None

# Minimum seconds between consecutive Gemini analysis API calls.
# 3.0s gap → max ~20 calls/minute, safely under the free-tier 20 RPM limit.
MIN_GAP_SECONDS: float = 3.0


def _get_lock() -> asyncio.Lock:
    global _gemini_lock
    if _gemini_lock is None:
        _gemini_lock = asyncio.Lock()
    return _gemini_lock


async def throttled_gemini_call(coro_fn):
    """Execute an async Gemini API call with rate limiting.

    *Acquires a global lock* so only one analysis runs at a time, and
    ensures at least ``MIN_GAP_SECONDS`` elapse between consecutive calls.
    """
    global _last_gemini_call

    lock = _get_lock()
    async with lock:
        elapsed = time.time() - _last_gemini_call
        if elapsed < MIN_GAP_SECONDS:
            wait = MIN_GAP_SECONDS - elapsed
            logger.debug("Gemini throttle: waiting {:.1f}s before next call", wait)
            await asyncio.sleep(wait)
        _last_gemini_call = time.time()
        return await coro_fn()
