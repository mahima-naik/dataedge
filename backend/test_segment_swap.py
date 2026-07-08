import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.state import get_state, resolved_greeting_text
from prompts.priya import build_role_system_prompt

def test_swap(segment: str):
    role = "rfqs"
    camp_row = {"name": "Test User", "segment": segment}
    
    # Emulate live_session.py logic
    prompt_role = role
    if role == "rfqs" and isinstance(camp_row, dict):
        if str(camp_row.get("segment", "")).strip().lower() == "seller":
            prompt_role = "sellers"
            print(f"Dynamic role swap: rfqs -> sellers for segment=seller")

    role_config = get_state(prompt_role)
    system_prompt = build_role_system_prompt(prompt_role, role_config, camp_row)
    greeting_text = resolved_greeting_text(prompt_role)

    is_rfq_context = (role == "rfqs")

    if is_rfq_context:
        if greeting_text:
            greeting_text = greeting_text.replace("Devika", "Radhika").replace("devika", "radhika")
        system_prompt = system_prompt.replace("Devika", "Radhika").replace("devika", "radhika")

    print(f"\n=== TEST WITH SEGMENT: {segment.upper()} ===")
    print(f"Prompt Role Selected: {prompt_role}")
    print(f"Greeting Text: {greeting_text}")
    print("Contains 'Devika':", "Devika" in system_prompt)
    print("Contains 'Radhika':", "Radhika" in system_prompt)
    if "HOW TO USE RFQ CONTEXT" in system_prompt:
        print("Has RFQ Context Block: YES")
    else:
        print("Has RFQ Context Block: NO")

    if prompt_role == "sellers":
        print("Is it pitching as a seller?: YES (loaded sellers prompt)")
        print("Does the prompt use Radhika?: YES (replaced Devika)")
    else:
        print("Is it pitching as an RFQ?: YES (loaded rfqs prompt)")

if __name__ == "__main__":
    print("Starting tests...")
    test_swap("rfq")
    test_swap("seller")
