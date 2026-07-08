import httpx
from loguru import logger
from core.phone_norm import norm_phone_str as _norm_phone_str
from core.state import _CAMPAIGN_DATA

_TTS_HTTP_CLIENT: httpx.AsyncClient = None

async def get_tts_client():
    global _TTS_HTTP_CLIENT
    if _TTS_HTTP_CLIENT is None or _TTS_HTTP_CLIENT.is_closed:
        _TTS_HTTP_CLIENT = httpx.AsyncClient(timeout=15.0)
    return _TTS_HTTP_CLIENT

async def _prewarm_opening(call_id: str, text: str, voice: str):
    try:
        from config import settings

        if settings.gemini_live_first_opening:
            logger.debug(
                "Skip REST TTS prewarm for {} — Gemini Live speaks opening",
                call_id,
            )
            return
        if call_id in _CAMPAIGN_DATA and _CAMPAIGN_DATA[call_id].get("opening_pcm"):
            logger.info("Skip TTS prewarm for {} — recorded opening already primed", call_id)
            return
        from services.gemini_tts import gemini_synthesize_pcm
        client = await get_tts_client()
        pcm, sr = await gemini_synthesize_pcm(client, text=text, voice=voice, style_mode="opening")
        if call_id in _CAMPAIGN_DATA:
            _CAMPAIGN_DATA[call_id]["opening_pcm"] = (pcm, sr)
            logger.info(f"Pre-warmed opening for {call_id}: {len(pcm)} bytes")
    except Exception as e:
        logger.warning(f"Pre-warm failed for {call_id}: {e}")


def _build_opening_line(row_data: dict, role: str = "sellers") -> str:
    from core.opening_line import build_opening_line

    return build_opening_line(row_data, role)
