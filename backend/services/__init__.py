# Lazy imports to avoid pipecat Python 3.10+ syntax errors on Python 3.9

def __getattr__(name: str):
    if name == "GeminiHttpTTSService":
        from .gemini_tts import GeminiHttpTTSService
        return GeminiHttpTTSService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["GeminiHttpTTSService"]
