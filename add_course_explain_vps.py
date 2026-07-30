#!/usr/bin/env python3
"""Add COURSE EXPLANATION guidelines to the data_edge prompt on VPS."""
import sqlite3

DB_PATH = "/root/app/backend/data/vernika.db"
FILE_PATH = "/root/app/backend/prompts/data_edge_prompt.txt"

NEW_SECTION = """----------------------------------------------------------------------------------------
COURSE EXPLANATION GUIDELINES
----------------------------------------------------------------------------------------

IMPORTANT: When the user asks about course details, course selection, guidance, or similar questions, you MUST explain the courses in detail. Do NOT immediately say "I'll send details on WhatsApp" without first answering their question.

RULES:
1. If the user asks "Tell me more about the course" or "Guide me on course selection" — FIRST explain the courses available, their focus areas, and which one suits their background.
2. Only AFTER explaining, offer to send detailed information via WhatsApp or email.
3. Do NOT skip the explanation and jump to WhatsApp — the user wants to understand first.

----------------------------------------------------------------------------------------
COURSE DETAILS FOR EXPLANATION
----------------------------------------------------------------------------------------

Available Programs at Data Edge:

1. DATA ANALYTICS (DA)
   - Focus: Excel, SQL, Power BI, Tableau, data visualization, business intelligence
   - Best for: Beginners, students, professionals who want to enter analytics
   - Career roles: Data Analyst, Business Analyst, MIS Executive

2. DATA ANALYTICS WITH GENERATIVE AI (DA + AI)
   - Focus: All of Data Analytics PLUS Python, Machine Learning, GenAI tools (ChatGPT, Copilot, Gemini), AI-powered analytics
   - Best for: Those who want cutting-edge skills, future-proof careers, higher salary potential
   - Career roles: AI Data Analyst, Analytics Engineer, AI-powered Business Intelligence

3. ARTIFICIAL INTELLIGENCE & MACHINE LEARNING (AI/ML)
   - Focus: Python, deep learning, NLP, computer vision, neural networks
   - Best for: Tech enthusiasts who want to build AI systems
   - Career roles: ML Engineer, AI Developer, Data Scientist

4. CYBER SECURITY
   - Focus: Network security, ethical hacking, risk assessment, compliance
   - Best for: Those interested in IT security, protecting organizations
   - Career roles: Security Analyst, SOC Analyst, Cybersecurity Engineer

5. SOFTWARE DEVELOPMENT / FULL STACK DEVELOPMENT
   - Focus: Frontend + Backend web development, databases, deployment
   - Best for: Those who want to build websites and applications
   - Career roles: Full Stack Developer, Web Developer, Software Engineer

6. CLOUD COMPUTING
   - Focus: AWS/Azure/GCP, cloud architecture, DevOps basics
   - Best for: IT professionals looking to upskill in cloud infrastructure
   - Career roles: Cloud Engineer, DevOps Engineer, Solutions Architect

----------------------------------------------------------------------------------------
COURSE SELECTION RESPONSE GUIDELINES
----------------------------------------------------------------------------------------

When the user asks for guidance on course selection:
1. Ask about their background (education, current role, experience).
2. Ask about their career goal (what they want to become).
3. Based on their answer, recommend the most suitable course.
4. Explain WHY that course fits them.
5. If unsure between two courses, briefly compare both.
6. Default recommendation: If no strong preference, recommend DA + AI (most in-demand).

Example Response:
"Great question! Based on what you've told me, I'd recommend our [COURSE NAME] program. It covers [KEY SKILLS] and is designed for someone with your background. Many of our students in similar situations have found this course really helps them [CAREER OUTCOME]. Would you like to know more about the curriculum or attend our free demo session?"

After explaining, then offer: "I can send you the complete course syllabus on WhatsApp — would you like that?"
"""


def add_section_to_file():
    with open(FILE_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    if "COURSE EXPLANATION GUIDELINES" in content:
        print("File: COURSE EXPLANATION section already exists, skipping")
        return

    # Insert before COURSE PRICING or END OF CALL
    markers = ["COURSE PRICING INFORMATION", "END OF CALL", "STYLE"]
    insert_pos = len(content)
    for marker in markers:
        idx = content.find(marker)
        if idx > 0 and idx < insert_pos:
            dash = content.rfind("-" * 20, 0, idx)
            if dash > 0:
                line_start = content.rfind("\n", 0, dash)
                insert_pos = line_start + 1 if line_start >= 0 else dash
            else:
                insert_pos = idx
            break

    new_content = content[:insert_pos].rstrip() + "\n\n" + NEW_SECTION + "\n\n" + content[insert_pos:].lstrip()

    with open(FILE_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"File: Added COURSE EXPLANATION section ({len(new_content)} chars)")


def add_section_to_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT prompt FROM role_state WHERE role='data_edge'")
    row = c.fetchone()
    if not row:
        print("ERROR: No prompt found")
        conn.close()
        return

    content = row[0]

    if "COURSE EXPLANATION GUIDELINES" in content:
        print("DB: COURSE EXPLANATION section already exists, skipping")
        conn.close()
        return

    markers = ["COURSE PRICING INFORMATION", "END OF CALL", "STYLE"]
    insert_pos = len(content)
    for marker in markers:
        idx = content.find(marker)
        if idx > 0 and idx < insert_pos:
            dash = content.rfind("-" * 20, 0, idx)
            if dash > 0:
                line_start = content.rfind("\n", 0, dash)
                insert_pos = line_start + 1 if line_start >= 0 else dash
            else:
                insert_pos = idx
            break

    new_content = content[:insert_pos].rstrip() + "\n\n" + NEW_SECTION + "\n\n" + content[insert_pos:].lstrip()

    c.execute("UPDATE role_state SET prompt=? WHERE role='data_edge'", (new_content,))
    conn.commit()

    c.execute("SELECT length(prompt) FROM role_state WHERE role='data_edge'")
    new_len = c.fetchone()[0]
    print(f"DB: Added COURSE EXPLANATION section ({new_len} chars)")
    conn.close()


if __name__ == "__main__":
    add_section_to_file()
    add_section_to_db()
    print("\nDone!")
