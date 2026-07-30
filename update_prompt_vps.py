#!/usr/bin/env python3
"""Update the data_edge prompt on VPS with new opening conversation flow. Non-interactive."""

import sqlite3

DB_PATH = "/root/app/backend/data/vernika.db"

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


def main():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT prompt FROM role_state WHERE role='data_edge'")
    row = c.fetchone()
    if not row:
        print("ERROR: No prompt found for role='data_edge'")
        conn.close()
        return

    current_prompt = row[0]
    print(f"Current prompt length: {len(current_prompt)} chars")

    # Find existing OPENING CONVERSATION FLOW section
    marker = "OPENING CONVERSATION FLOW"
    idx = current_prompt.find(marker)

    if idx >= 0:
        # Find the dashed line before it
        section_start = current_prompt.rfind("-" * 20, 0, idx)
        if section_start < 0:
            section_start = idx
        else:
            # Go to start of that dashed line
            line_start = current_prompt.rfind("\n", 0, section_start)
            section_start = line_start + 1 if line_start >= 0 else 0

        # Find next major section after the opening
        search_from = idx + len(marker)
        next_sections = ["CONVERSATION FLOW", "CORE PERSONA", "OBJECTION", "DEMO SESSION",
                         "COURSE INFO", "STYLE", "END OF CALL", "WHATSAPP"]
        section_end = len(current_prompt)
        for s in next_sections:
            sidx = current_prompt.find(s, search_from)
            if sidx > 0 and sidx < section_end:
                # Go back to the dashed line before it
                dash_pos = current_prompt.rfind("-" * 20, 0, sidx)
                if dash_pos > section_start:
                    section_end = dash_pos
                else:
                    section_end = sidx
                break

        old_section = current_prompt[section_start:section_end].strip()
        print(f"Found existing section to replace ({len(old_section)} chars)")

        new_prompt = (
            current_prompt[:section_start].rstrip()
            + "\n\n"
            + NEW_OPENING_SECTION
            + "\n\n"
            + current_prompt[section_end:].lstrip()
        )
    else:
        # No existing section found - look for any opening-related content
        # Try to find where conversation instructions start
        for pattern in ["Opening", "GREETING", "conversation flow"]:
            pidx = current_prompt.lower().find(pattern.lower())
            if pidx > 0:
                line_start = current_prompt.rfind("\n", 0, pidx)
                section_start = line_start + 1 if line_start >= 0 else 0
                new_prompt = (
                    current_prompt[:section_start].rstrip()
                    + "\n\n"
                    + NEW_OPENING_SECTION
                    + "\n\n"
                    + current_prompt[section_start:].lstrip()
                )
                print(f"Inserted before '{pattern}' at position {section_start}")
                break
        else:
            # Just prepend
            new_prompt = NEW_OPENING_SECTION + "\n\n" + current_prompt
            print("Prepended new opening section (no matching section found)")

    print(f"New prompt length: {len(new_prompt)} chars")

    # Show the new opening section
    print(f"\n--- NEW OPENING SECTION ---")
    print(NEW_OPENING_SECTION)
    print("--- END ---\n")

    # Update
    c.execute("UPDATE role_state SET prompt=? WHERE role='data_edge'", (new_prompt,))
    conn.commit()
    print(f"Prompt updated successfully! ({len(new_prompt)} chars)")

    # Verify
    c.execute("SELECT length(prompt) FROM role_state WHERE role='data_edge'")
    verify_len = c.fetchone()[0]
    print(f"Verified: {verify_len} chars in database")

    conn.close()


if __name__ == "__main__":
    main()
