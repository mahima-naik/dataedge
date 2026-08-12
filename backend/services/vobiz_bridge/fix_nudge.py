import sys

p = "/root/app/backend/services/vobiz_bridge/live_session.py"
with open(p) as f:
    s = f.read()

old = "introduce yourself and start the conversation as instructed."
new = "Do NOT repeat the introduction or your name. Ask ONE short natural follow-up question, then STOP and listen. Max 1 sentence, under 8 seconds."
count = s.count(old)
print(f"Found {count} occurrences of old nudge text")
s = s.replace(old, new)
with open(p, "w") as f:
    f.write(s)
print("Nudge text updated")
