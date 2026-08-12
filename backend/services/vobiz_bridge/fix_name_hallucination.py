import sys

p = "/root/app/backend/services/vobiz_bridge/live_session.py"
with open(p) as f:
    s = f.read()

# Add name hallucination rule to the anchor block (BRAND-SAFETY RULES section)
old_anchor_end = "[ANCHOR \u2014 BRAND-SAFETY RULES]"
new_anchor_end = """[ANCHOR \u2014 BRAND-SAFETY RULES]
CRITICAL NAME RULES:
- NEVER guess or invent the callee's name from unclear audio.
- If you are not 100% certain of the caller's name, do NOT use any name.
- If STT returns garbled/unclear text that might be a name, say "Sorry, I didn't catch that clearly" and ask them to repeat.
- Only use the caller's name after they have clearly stated it and you have confirmed it."""
count = s.count(old_anchor_end)
print(f"Found {count} anchor occurrences")
if count == 1:
    s = s.replace(old_anchor_end, new_anchor_end)
    with open(p, "w") as f:
        f.write(s)
    print("Name hallucination rules added to anchor block")
else:
    print("ERROR: anchor block not found or multiple matches")
