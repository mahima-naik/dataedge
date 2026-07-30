#!/usr/bin/env python3
"""Add COURSE PRICING section to the data_edge prompt on VPS."""
import sqlite3

DB_PATH = "/root/app/backend/data/vernika.db"
FILE_PATH = "/root/app/backend/prompts/data_edge_prompt.txt"

NEW_PRICING_SECTION = """----------------------------------------------------------------------------------------
COURSE PRICING INFORMATION
----------------------------------------------------------------------------------------

IMPORTANT:
- When the user asks about course fees, pricing, EMI, or cost, ALWAYS mention the monthly EMI plan first.
- Do NOT mention the actual course fee or the annual/full payment amount unless the user specifically asks for it.
- Explain the pricing naturally, not like reading a brochure.
- After explaining the monthly EMI, ask if they would like to know more about the curriculum or attend the free demo session.

----------------------------------------------------------------------------------------
DATA ANALYTICS COURSE PRICING
----------------------------------------------------------------------------------------

Monthly EMI:
• ₹3,125 per month

Suggested Response:

"Our Data Analytics program is available with an easy monthly EMI of just ₹3,125 per month, making it convenient to learn without paying the entire amount upfront. Along with the course, you'll receive live online training, mentor support, hands-on projects, and placement assistance."

----------------------------------------------------------------------------------------
DATA ANALYTICS WITH GENERATIVE AI PRICING
----------------------------------------------------------------------------------------

Monthly EMI:
• ₹5,000 per month

Suggested Response:

"Our Data Analytics with Generative AI program is available with an easy monthly EMI of just ₹5,000 per month. The program includes live online training, Generative AI concepts, real-world projects, mentor guidance, and placement assistance."

----------------------------------------------------------------------------------------
RESPONSE GUIDELINES
----------------------------------------------------------------------------------------

- Always mention the monthly EMI first.
- Do NOT mention the full course fee unless the user explicitly asks for the total price.
- If the user asks, "How much does the course cost?", respond with the monthly EMI.
- If the user specifically asks, "What is the total course fee?" or "What is the full payment amount?", then provide the total course fee.
- After explaining the pricing, naturally continue the conversation by asking:
  "Would you like to know more about the curriculum, projects, or attend our free demo session this Saturday at 6:00 PM?"
"""


def add_pricing_to_file():
    with open(FILE_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    if "COURSE PRICING INFORMATION" in content:
        print("File: COURSE PRICING section already exists, skipping")
        return len(content)

    # Find a good insertion point — before END OF CALL or STYLE or at end
    insert_markers = ["END OF CALL", "STYLE", "---"]
    insert_pos = len(content)
    for marker in insert_markers:
        idx = content.find(marker)
        if idx > 0 and idx < insert_pos:
            # Go back to dashed line before
            dash = content.rfind("-" * 20, 0, idx)
            if dash > 0:
                line_start = content.rfind("\n", 0, dash)
                insert_pos = line_start + 1 if line_start >= 0 else dash
                break
            else:
                insert_pos = idx
                break

    new_content = content[:insert_pos].rstrip() + "\n\n" + NEW_PRICING_SECTION + "\n\n" + content[insert_pos:].lstrip()

    with open(FILE_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"File: Added COURSE PRICING section ({len(new_content)} chars)")
    return len(new_content)


def add_pricing_to_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT prompt FROM role_state WHERE role='data_edge'")
    row = c.fetchone()
    if not row:
        print("ERROR: No prompt found")
        conn.close()
        return

    content = row[0]

    if "COURSE PRICING INFORMATION" in content:
        print("DB: COURSE PRICING section already exists, skipping")
        conn.close()
        return len(content)

    # Find insertion point
    insert_markers = ["END OF CALL", "STYLE", "---"]
    insert_pos = len(content)
    for marker in insert_markers:
        idx = content.find(marker)
        if idx > 0 and idx < insert_pos:
            dash = content.rfind("-" * 20, 0, idx)
            if dash > 0:
                line_start = content.rfind("\n", 0, dash)
                insert_pos = line_start + 1 if line_start >= 0 else dash
                break
            else:
                insert_pos = idx
                break

    new_content = content[:insert_pos].rstrip() + "\n\n" + NEW_PRICING_SECTION + "\n\n" + content[insert_pos:].lstrip()

    c.execute("UPDATE role_state SET prompt=? WHERE role='data_edge'", (new_content,))
    conn.commit()

    c.execute("SELECT length(prompt) FROM role_state WHERE role='data_edge'")
    new_len = c.fetchone()[0]
    print(f"DB: Added COURSE PRICING section ({new_len} chars)")

    conn.close()
    return new_len


if __name__ == "__main__":
    add_pricing_to_file()
    add_pricing_to_db()
    print("\nDone!")
