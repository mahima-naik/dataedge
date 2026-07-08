from core.state import get_state
state = get_state('buyers')
print("Greeting:", state.get("greeting_text"))
