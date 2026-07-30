#!/usr/bin/env python3
"""Update both file prompt AND database prompt on VPS with new opening flow."""

import os

DB_PATH = "/root/app/backend/data/vernika.db"
FILE_PATH = "/root/app/backend/prompts/data_edge_prompt.txt"

NEW_OPENING_SECTION = """----------------------------------------------------------------------------------------
OPENING CONVERSATION FLOW (REPLACE THE EXISTING OPENING SECTION)
----------------------------------------------------------------------------------------

IMPORTANT:
- Do NOT ask "Are you studying or working?" immediately after the greeting.
- First, briefly introduce Data Edge and why you're calling.
- Mention the popular courses naturally without sounding like you're reading a list.
- Keep the introduction within 2-3 short sentences.
- After the user acknowledges or responds, THEN ask whether they are studying or working.
- Ask only ONE question at a time.

Opening Greeting:

"Hi, I'm Priya, a career counselor from Data Edge. You had recently shown interest in building a career in technology, so I just wanted to take two minutes to explain how we can help. Is this a good time to talk?"

If the user says yes:

"Thank you! At Data Edge, we provide industry-focused training designed to help students and working professionals build job-ready skills. We offer programs in Data Analytics, Data Analytics with Generative AI, Artificial Intelligence, Machine Learning, Data Science, Cybersecurity, Software Development, Full Stack Development, and Cloud Computing, along with hands-on projects, mentor support, and placement assistance."

Pause and allow the user to respond naturally.

Then ask:

"So, just to guide you better, may I know if you're currently studying or working?"

If they say they are studying:

"That's great. Which course or career field are you most interested in exploring?"

If they say they are working:

"That's great. Are you looking to upskill for career growth, switch your career, or simply explore new opportunities?"

RULES:
- Never ask "Are you studying or working?" immediately after saying hello.
- Always give a brief introduction about Data Edge before asking any qualification questions.
- Mention the available courses naturally in one sentence; do not explain every course unless the user asks.
- Keep the tone friendly and conversational.
- Pause after introducing Data Edge so the caller can respond.
- Ask only one question at a time.
- Continue with the existing conversation flow after this."""


def update_file_prompt():
    """Update the file prompt with the new opening section."""
    with open(FILE_PATH, "r", encoding="utf-8") as f:
        current = f.read()
    
    print(f"File prompt length: {len(current)} chars")
    
    # Find and replace the opening section in the file
    marker = "OPENING CONVERSATION FLOW"
    idx = current.find(marker)
    
    if idx >= 0:
        # Find dashed line before
        section_start = current.rfind("-" * 20, 0, idx)
        if section_start < 0:
            section_start = idx
        else:
            line_start = current.rfind("\n", 0, section_start)
            section_start = line_start + 1 if line_start >= 0 else 0
        
        # Find next section
        search_from = idx + len(marker)
        next_sections = ["CONVERSATION FLOW", "CORE PERSONA", "OBJECTION", "DEMO SESSION",
                         "COURSE INFO", "STYLE", "END OF CALL", "WHATSAPP"]
        section_end = len(current)
        for s in next_sections:
            sidx = current.find(s, search_from)
            if sidx > 0 and sidx < section_end:
                dash_pos = current.rfind("-" * 20, 0, sidx)
                if dash_pos > section_start:
                    section_end = dash_pos
                else:
                    section_end = sidx
                break
        
        new_prompt = (
            current[:section_start].rstrip()
            + "\n\n"
            + NEW_OPENING_SECTION
            + "\n\n"
            + current[section_end:].lstrip()
        )
        print(f"Replaced existing opening section in file")
    else:
        # Insert before first major section
        for pattern in ["Opening", "GREETING", "CONVERSATION"]:
            pidx = current.lower().find(pattern.lower())
            if pidx > 0:
                line_start = current.rfind("\n", 0, pidx)
                section_start = line_start + 1 if line_start >= 0 else 0
                new_prompt = (
                    current[:section_start].rstrip()
                    + "\n\n"
                    + NEW_OPENING_SECTION
                    + "\n\n"
                    + current[section_start:].lstrip()
                )
                print(f"Inserted before '{pattern}' in file")
                break
        else:
            new_prompt = NEW_OPENING_SECTION + "\n\n" + current
            print("Prepended to file")
    
    with open(FILE_PATH, "w", encoding="utf-8") as f:
        f.write(new_prompt)
    
    print(f"File prompt updated: {len(new_prompt)} chars")
    return new_prompt


def update_db_prompt(prompt):
    """Update the database prompt."""
    import sqlite3
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("UPDATE role_state SET prompt=? WHERE role='data_edge'", (prompt,))
    conn.commit()
    
    c.execute("SELECT length(prompt) FROM role_state WHERE role='data_edge'")
    new_len = c.fetchone()[0]
    print(f"Database prompt updated: {new_len} chars")
    
    conn.close()


if __name__ == "__main__":
    new_prompt = update_file_prompt()
    update_db_prompt(new_prompt)
    print("\nDone! Both file and database prompts updated.")
    print("Service restart will now use the new prompt.")
