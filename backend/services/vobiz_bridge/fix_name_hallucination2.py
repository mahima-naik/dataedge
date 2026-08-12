import sys

p = "/root/app/backend/services/vobiz_bridge/live_session.py"
with open(p) as f:
    s = f.read()

# Add name hallucination rules after the existing anchor line
old = '            "If the user asks your name, **Priya**.\\n"'
# try matching the actual string
old = '            "If the user asks your name, say **Priya**.\\n"'
new = '            "If the user asks your name, say **Priya**.\\n"\n            "NEVER guess or invent the callee'"'"'s name from unclear audio.\\n"\n            "If STT returns garbled/unclear text that might be a name, say '"'"'Sorry, I didn'"'"'t catch that clearly'"'"' and ask them to repeat.\\n"\n            "Only use the caller'"'"'s name after they have clearly stated it and you have confirmed it.\\n"'

count = s.count(old)
print(f"Found {count} occurrences of anchor name line")
if count == 1:
    s = s.replace(old, new)
    with open(p, "w") as f:
        f.write(s)
    print("Name hallucination rules added")
else:
    print("ERROR: could not find anchor name line")
