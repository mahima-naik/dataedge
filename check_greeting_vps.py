#!/usr/bin/env python3
"""Check greeting text on VPS."""
import sys
sys.path.insert(0, "/root/app/backend")

from core.state import resolved_greeting_text, get_state

# Check resolved greeting
g = resolved_greeting_text("data_edge")
print(f"resolved_greeting_text: {repr(g)}")

# Check state
state = get_state("data_edge")
gt = (state.get("greeting_text") or "").strip()
print(f"state greeting_text: {repr(gt)}")

# Check opening line from prompt
from prompts.priya import get_role_prompt_text
fp = get_role_prompt_text("data_edge")
# Find "Opening Greeting:" section
idx = fp.find("Opening Greeting:")
if idx >= 0:
    snippet = fp[idx:idx+300]
    print(f"\nPrompt opening section:\n{snippet}")
