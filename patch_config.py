import pathlib

p = pathlib.Path("/root/DataEdge/backend/config.py")
content = p.read_text()

old = """    gemini_call_analysis_model: str = os.getenv(
        "GEMINI_CALL_ANALYSIS_MODEL", "gemini-2.5-flash"
    ).strip()
    # Separate API key for TTS pre-warm"""

new = """    gemini_call_analysis_model: str = os.getenv(
        "GEMINI_CALL_ANALYSIS_MODEL", "gemini-2.5-flash"
    ).strip()
    # Separate API key for call analysis — isolates its quota from Live / TTS.
    gemini_call_analysis_api_key: str = (
        os.getenv("GEMINI_CALL_ANALYSIS_API_KEY")
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or ""
    ).strip()
    # Separate API key for TTS pre-warm"""

if old in content:
    content = content.replace(old, new)
    p.write_text(content)
    print("DONE: gemini_call_analysis_api_key added")
else:
    print("ERROR: pattern not found in config.py")
