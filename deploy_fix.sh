#!/bin/bash
# Deploy script: Fixes summary generation errors
# Creates backups for easy rollback

BACKEND="/root/DataEdge/backend"
BACKUP_DIR="$BACKEND/.backup_fix_$(date +%Y%m%d_%H%M%S)"

echo "=== Creating backup at $BACKUP_DIR ==="
mkdir -p "$BACKUP_DIR"
cp "$BACKEND/services/local_analyzer.py" "$BACKUP_DIR/local_analyzer.py.bak"
cp "$BACKEND/config.py" "$BACKUP_DIR/config.py.bak"
echo "Backup saved: local_analyzer.py, config.py"

echo ""
echo "=== Fix 1: Clearing stale __pycache__ ==="
find "$BACKEND" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
echo "All __pycache__ cleared."

echo ""
echo "=== Fix 2: Replacing local_analyzer.py with lazy import version ==="
cat > "$BACKEND/services/local_analyzer.py" << 'PYEOF'
from __future__ import annotations

import time

from loguru import logger

from services.analysis_prompt import (
    build_analysis_prompt,
    empty_transcript_result,
    parse_json_from_text,
    result_from_json,
)


_MODEL = None
_TOKENIZER = None
_MODEL_PATH = "models/LFM2.5-1.2B-Instruct"


def _get_model():
    global _MODEL, _TOKENIZER
    if _MODEL is None:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        t0 = time.time()
        logger.info("Loading LFM2.5-1.2B-Instruct model...")
        _TOKENIZER = AutoTokenizer.from_pretrained(_MODEL_PATH)
        _MODEL = AutoModelForCausalLM.from_pretrained(_MODEL_PATH)
        logger.info(f"Model loaded in {time.time()-t0:.1f}s")
    return _MODEL, _TOKENIZER


async def analyze_local(transcript_text: str) -> dict:
    if not transcript_text.strip():
        return empty_transcript_result(
            summary="No transcript available",
            rationale="",
        )

    prompt = build_analysis_prompt(transcript_text)
    if not prompt:
        return empty_transcript_result(
            summary="Call ended early / No conversation",
            rationale="No conversational turns in transcript.",
        )

    try:
        model, tokenizer = _get_model()

        messages = [
            {
                "role": "system",
                "content": "You are a QA analyst reviewing sales call transcripts. Return only valid JSON.",
            },
            {"role": "user", "content": prompt},
        ]
        input_text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = tokenizer(input_text, return_tensors="pt")
        t0 = time.time()
        out = model.generate(
            **inputs,
            max_new_tokens=512,
            do_sample=True,
            temperature=0.1,
            top_p=0.9,
        )
        dt = time.time() - t0
        raw_output = tokenizer.decode(
            out[0][inputs.input_ids.shape[1] :], skip_special_tokens=True
        )
        logger.info(f"Local analysis completed in {dt:.1f}s ({len(raw_output)} chars)")

        parsed = parse_json_from_text(raw_output)
        if parsed:
            return result_from_json(parsed)
        logger.warning(f"Could not parse JSON from model output: {raw_output[:200]}")
        return {
            "summary": "Analysis parsing failed",
            "rating": 0,
            "next_steps": "Retry later",
            "disposition": "Answered",
            "emotion_label": "Unknown",
            "emotion_rationale": "",
            "emotion_confidence": None,
            "requested_callback_datetime_iso": None,
        }
    except Exception as e:
        logger.error(f"Local analysis failed: {e}")
        return {
            "summary": f"Analysis failed: {e}",
            "rating": 0,
            "next_steps": "Retry later",
            "disposition": "Answered",
            "emotion_label": "Unknown",
            "emotion_rationale": "",
            "emotion_confidence": None,
            "requested_callback_datetime_iso": None,
        }
PYEOF
echo "local_analyzer.py replaced."

echo ""
echo "=== Restarting dataedge service ==="
systemctl restart dataedge.service
echo "Service restarted."

echo ""
echo "=== DEPLOY COMPLETE ==="
echo "Backup location: $BACKUP_DIR"
echo "To rollback, run: bash $BACKEND/rollback_fix.sh"
