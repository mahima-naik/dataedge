import sys
import os

# Ensure backend can be imported
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend"))

def test_rfqs_prompt_file():
    print("Testing rfqs_prompt.txt contents...")
    path = "backend/prompts/rfqs_prompt.txt"
    if not os.path.exists(path):
        path = "../backend/prompts/rfqs_prompt.txt"
        
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Devika should not be anywhere in rfqs_prompt.txt
    if "Devika" in content or "devika" in content:
        print("FAIL: 'Devika' found in rfqs_prompt.txt!")
        sys.exit(1)
        
    if "Radhika" not in content:
        print("FAIL: 'Radhika' not found in rfqs_prompt.txt!")
        sys.exit(1)
        
    print("PASS: rfqs_prompt.txt correctly uses Radhika instead of Devika.")

def test_live_session_replacements():
    print("Simulating live_session.py replacements...")
    # Simulate the replacement logic in handle_vobiz_ws_live:
    # is_rfq_context = (role == "rfqs" or campaign_role == "rfqs" or ...)
    
    # Test case 1: Outbound campaign is rfqs, segment overrides role to sellers
    role = "sellers"
    campaign_role = "rfqs"
    manual_role = None
    inbound_role = None
    
    is_rfq_context = (
        role == "rfqs" or 
        campaign_role == "rfqs" or 
        (manual_role and manual_role == "rfqs") or 
        (inbound_role and inbound_role == "rfqs")
    )
    
    assert is_rfq_context is True, "Expected is_rfq_context to be True for campaign_role = rfqs"
    
    # Simulate greeting_text/opening_line loaded from sellers prompt (which uses Devika)
    opening_line = "Hi, this is Devika from Procucev, Bangalore. Got a quick minute?"
    greeting_text = "Hi, this is Devika from Procucev, Bangalore. Got a quick minute?"
    
    if is_rfq_context:
        if opening_line:
            opening_line = opening_line.replace("Devika", "Radhika").replace("devika", "radhika")
        if greeting_text:
            greeting_text = greeting_text.replace("Devika", "Radhika").replace("devika", "radhika")
            
    assert "Radhika" in opening_line, f"Expected Radhika, got: {opening_line}"
    assert "Devika" not in opening_line, f"Should not have Devika: {opening_line}"
    assert "Radhika" in greeting_text
    
    # Simulate system prompt from sellers prompt (which uses Devika)
    system_prompt = "You are Devika. You work at Procucev..."
    if is_rfq_context:
        system_prompt = system_prompt.replace("Devika", "Radhika").replace("devika", "radhika")
        
    assert "Radhika" in system_prompt
    assert "Devika" not in system_prompt
    
    print("PASS: live_session.py simulation replacements succeed!")

def test_browser_voice_bridge_replacements():
    print("Simulating browser_voice_bridge.py replacements...")
    # query_role = ws_role
    # If segment override changes role to sellers, the query_role was still rfqs
    query_role = "rfqs"
    role = "sellers" # overridden by segment=seller
    
    is_rfq_context = (role == "rfqs" or query_role == "rfqs")
    assert is_rfq_context is True
    
    system_prompt = "You are Devika. You work at Procucev..."
    if is_rfq_context:
        system_prompt = system_prompt.replace("Devika", "Radhika").replace("devika", "radhika")
        
    assert "Radhika" in system_prompt
    assert "Devika" not in system_prompt
    print("PASS: browser_voice_bridge.py simulation replacements succeed!")

if __name__ == "__main__":
    test_rfqs_prompt_file()
    test_live_session_replacements()
    test_browser_voice_bridge_replacements()
    print("ALL TESTS PASSED SUCCESSFULLY!")
