import sys
import os

# Add backend to path
sys.path.append(os.path.abspath('backend'))

from core.storage import init_db
from core.state import get_state
from prompts.priya import build_role_system_prompt

def run_test():
    init_db()
    
    # Mock lead data from CSV
    # campaign role is rfqs, but segment is seller
    campaign_role = "rfqs"
    camp_row = {
        "name": "Test Customer",
        "Segment": "seller",
        "role": "rfqs"
    }
    
    # Trace the logic inside live_session.py
    role = camp_row.get("role", "sellers")
    if role in ("sellers", "buyers", "rfqs") and camp_row.get("Segment"):
        seg = str(camp_row.get("Segment")).strip().lower()
        if seg == "seller":
            role = "sellers"
            
    print(f"Resolved role: {role} (Expected: sellers)")
    
    # Resolve prompt_role
    prompt_role = role
    
    # Load state and build prompt
    role_config = get_state(prompt_role)
    system_prompt = build_role_system_prompt(prompt_role, role_config, camp_row)
    
    # Trace name replacement logic
    is_rfq_context = (campaign_role == "rfqs")
    if is_rfq_context:
        system_prompt = system_prompt.replace("Devika", "Radhika").replace("devika", "radhika")
        
    print(f"Contains 'Radhika': {'Radhika' in system_prompt}")
    print(f"Contains 'Devika': {'Devika' in system_prompt}")
    
    # Print the first line of the prompt to verify persona
    first_line = system_prompt.split('\n')[0]
    print(f"First line: '{first_line}'")

if __name__ == '__main__':
    run_test()
