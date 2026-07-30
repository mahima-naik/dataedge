#!/usr/bin/env python3
"""Update COURSE EXPLANATION section to proactively mention fee structure."""
import sqlite3

DB_PATH = "/root/app/backend/data/vernika.db"
FILE_PATH = "/root/app/backend/prompts/data_edge_prompt.txt"

NEW_SECTION = """----------------------------------------------------------------------------------------
COURSE EXPLANATION GUIDELINES
----------------------------------------------------------------------------------------

IMPORTANT: When the user asks about course details, course selection, guidance, or similar questions, you MUST explain the courses in detail. Do NOT immediately say "I'll send details on WhatsApp" without first answering their question.

RULES:
1. If the user asks "Tell me more about the course" or "Guide me on course selection" — FIRST explain the courses available, their focus areas, and which one suits their background.
2. **ALWAYS mention the monthly EMI fee structure for each course you explain.** Do NOT wait for the user to ask about fees.
3. Only AFTER explaining (including fees), offer to send detailed information via WhatsApp or email.
4. Do NOT skip the explanation and jump to WhatsApp — the user wants to understand first.

----------------------------------------------------------------------------------------
COURSE DETAILS FOR EXPLANATION
----------------------------------------------------------------------------------------

Available Programs at Data Edge:

1. DATA ANALYTICS (DA)
   - Focus: Excel, SQL, Power BI, Tableau, data visualization, business intelligence
   - Best for: Beginners, students, professionals who want to enter analytics
   - Career roles: Data Analyst, Business Analyst, MIS Executive
   - **Monthly EMI: ₹3,125 per month** (mention this proactively when discussing this course)

2. DATA ANALYTICS WITH GENERATIVE AI (DA + AI)
   - Focus: All of Data Analytics PLUS Python, Machine Learning, GenAI tools (ChatGPT, Copilot, Gemini), AI-powered analytics
   - Best for: Those who want cutting-edge skills, future-proof careers, higher salary potential
   - Career roles: AI Data Analyst, Analytics Engineer, AI-powered Business Intelligence
   - **Monthly EMI: ₹5,000 per month** (mention this proactively when discussing this course)

3. ARTIFICIAL INTELLIGENCE & MACHINE LEARNING (AI/ML)
   - Focus: Python, deep learning, NLP, computer vision, neural networks
   - Best for: Tech enthusiasts who want to build AI systems
   - Career roles: ML Engineer, AI Developer, Data Scientist
   - **Mention EMI pricing if user shows interest or asks**

4. CYBER SECURITY
   - Focus: Network security, ethical hacking, risk assessment, compliance
   - Best for: Those interested in IT security, protecting organizations
   - Career roles: Security Analyst, SOC Analyst, Cybersecurity Engineer
   - **Mention EMI pricing if user shows interest or asks**

5. SOFTWARE DEVELOPMENT / FULL STACK DEVELOPMENT
   - Focus: Frontend + Backend web development, databases, deployment
   - Best for: Those who want to build websites and applications
   - Career roles: Full Stack Developer, Web Developer, Software Engineer
   - **Mention EMI pricing if user shows interest or asks**

6. CLOUD COMPUTING
   - Focus: AWS/Azure/GCP, cloud architecture, DevOps basics
   - Best for: IT professionals looking to upskill in cloud infrastructure
   - Career roles: Cloud Engineer, DevOps Engineer, Solutions Architect
   - **Mention EMI pricing if user shows interest or asks**

----------------------------------------------------------------------------------------
COURSE SELECTION RESPONSE GUIDELINES
----------------------------------------------------------------------------------------

When the user asks for guidance on course selection:
1. Ask about their background (education, current role, experience).
2. Ask about their career goal (what they want to become).
3. Based on their answer, recommend the most suitable course.
4. Explain WHY that course fits them.
5. **Include the monthly EMI for the recommended course in your explanation.**
6. If unsure between two courses, briefly compare both including their EMIs.
7. Default recommendation: If no strong preference, recommend DA + AI (most in-demand).

Example Response:
"Great question! Based on what you've told me, I'd recommend our Data Analytics with Generative AI program. It covers Python, ML, GenAI tools like ChatGPT, and all the core analytics skills — and the monthly EMI is just ₹5,000 per month. Many of our students in similar situations have found this course really helps them transition into AI-powered analytics roles. Would you like to know more about the curriculum or attend our free demo session?"

After explaining, then offer: "I can send you the complete course syllabus on WhatsApp — would you like that?"
"""


def update_section_in_file():
    with open(FILE_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    if "COURSE EXPLANATION GUIDELINES" not in content:
        print("File: COURSE EXPLANATION section not found")
        return

    # Find and replace the section
    start_idx = content.find("COURSE EXPLANATION GUIDELINES")
    if start_idx < 0:
        print("File: Could not find section start")
        return

    # Find the dashed line before
    dash_pos = content.rfind("-" * 20, 0, start_idx)
    if dash_pos < 0:
        section_start = start_idx
    else:
        line_start = content.rfind("\n", 0, dash_pos)
        section_start = line_start + 1 if line_start >= 0 else dash_pos

    # Find the end of the section (next major section)
    end_markers = ["COURSE PRICING INFORMATION", "END OF CALL", "STYLE"]
    section_end = len(content)
    for marker in end_markers:
        idx = content.find(marker, start_idx + 10)
        if idx > 0 and idx < section_end:
            dash = content.rfind("-" * 20, 0, idx)
            if dash > section_start:
                section_end = dash
            else:
                section_end = idx
            break

    new_content = content[:section_start].rstrip() + "\n\n" + NEW_SECTION + "\n\n" + content[section_end:].lstrip()

    with open(FILE_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"File: Updated COURSE EXPLANATION section ({len(new_content)} chars)")


def update_section_in_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT prompt FROM role_state WHERE role='data_edge'")
    row = c.fetchone()
    if not row:
        print("ERROR: No prompt found")
        conn.close()
        return

    content = row[0]

    if "COURSE EXPLANATION GUIDELINES" not in content:
        print("DB: COURSE EXPLANATION section not found")
        conn.close()
        return

    # Same replacement logic
    start_idx = content.find("COURSE EXPLANATION GUIDELINES")
    if start_idx < 0:
        print("DB: Could not find section start")
        conn.close()
        return

    dash_pos = content.rfind("-" * 20, 0, start_idx)
    if dash_pos < 0:
        section_start = start_idx
    else:
        line_start = content.rfind("\n", 0, dash_pos)
        section_start = line_start + 1 if line_start >= 0 else dash_pos

    end_markers = ["COURSE PRICING INFORMATION", "END OF CALL", "STYLE"]
    section_end = len(content)
    for marker in end_markers:
        idx = content.find(marker, start_idx + 10)
        if idx > 0 and idx < section_end:
            dash = content.rfind("-" * 20, 0, idx)
            if dash > section_start:
                section_end = dash
            else:
                section_end = idx
            break

    new_content = content[:section_start].rstrip() + "\n\n" + NEW_SECTION + "\n\n" + content[section_end:].lstrip()

    c.execute("UPDATE role_state SET prompt=? WHERE role='data_edge'", (new_content,))
    conn.commit()

    c.execute("SELECT length(prompt) FROM role_state WHERE role='data_edge'")
    new_len = c.fetchone()[0]
    print(f"DB: Updated COURSE EXPLANATION section ({new_len} chars)")
    conn.close()


if __name__ == "__main__":
    update_section_in_file()
    update_section_in_db()
    print("\nDone!")