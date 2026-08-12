import sys

p = "/root/app/backend/services/vobiz_bridge/live_session.py"
with open(p) as f:
    s = f.read()

# Insert brevity rule BEFORE the anchor block
old = '    blocks = (anchor + pacing_rule + context_rules) if anchor else (pacing_rule + context_rules)'

new = '''    brevity_rule = (
        "\\n[HARD BREVITY RULE — OVERRIDES ALL SCRIPTS BELOW]\\n"
        "EVERY spoken reply MUST be 1-2 SHORT sentences only (under 5 seconds of speech).\\n"
        "NEVER read long script paragraphs. NEVER give detailed explanations on a phone call.\\n"
        "Adapt the scripts below into brief, natural phone conversation — not a rehearsed speech.\\n"
        "Ask ONE question at a time, then STOP talking and listen.\\n"
        "If a script paragraph below is longer than 2 sentences, condense it to 1 sentence.\\n\\n"
    )

    blocks = (anchor + brevity_rule + pacing_rule + context_rules) if anchor else (brevity_rule + pacing_rule + context_rules)'''

count = s.count(old)
print(f"Found {count} occurrences of blocks assembly")
if count == 1:
    s = s.replace(old, new)
    with open(p, "w") as f:
        f.write(s)
    print("Brevity rule injected before anchor")
else:
    print("ERROR: could not find blocks assembly")
