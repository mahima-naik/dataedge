import sys
import os

# Add backend to path
sys.path.append("/Users/surya/Downloads/VernikaAI Max profit/backend")

from prompts.priya import get_role_prompt_text, get_role_rag_source_text

for role in ["sellers", "buyers", "rfqs", "real_estate"]:
    p = get_role_prompt_text(role)
    r = get_role_rag_source_text(role)
    print(f"Role: {role}")
    print(f"Prompt length: {len(p)}")
    print(f"RAG length: {len(r)}")
    print("-" * 20)
