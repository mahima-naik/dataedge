import sys

p = "/root/app/backend/services/vobiz_bridge/turn_taking_addon.py"
with open(p) as f:
    s = f.read()

old = """Speak in clear 1\u20132 sentence turns. Complete your question or thought before yielding."""
new = """Speak in 1 short sentence (under 8 seconds of speech). Complete your question or thought before yielding. Do NOT give long monologues or read paragraphs."""
count = s.count(old)
print(f"Found {count} occurrences of old turn text")
if count == 1:
    s = s.replace(old, new)
    with open(p, "w") as f:
        f.write(s)
    print("Turn addon updated")
else:
    print("ERROR: turn text not found or multiple matches")
