"""Role sandbox checks (run: cd backend && PYTHONPATH=. python3 ../scratch/test_role_sandbox.py)."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from core.state import parse_manual_camp_role_suffix
from core.role_sandbox import (
    coerce_role_prompt,
    coerce_stored_greeting,
    detect_foreign_role,
    validate_role_tuning,
    matches_sellers_content,
    matches_vernikaai_content,
)
from prompts.priya import _resolved_prompt_and_rag


def test_manual_camp_legacy_hyphen():
    role, token = parse_manual_camp_role_suffix("rfqs-20260504T08572")
    assert role == "rfqs", role
    assert token == "20260504T08572", token


def test_rfqs_rejects_sellers_greeting():
    g = "Hi, this is Devika from Procucev, Bangalore. Got a quick minute?"
    assert coerce_stored_greeting("rfqs", g) == ""


def test_sellers_rejects_dariaan_greeting():
    g = "Hello, this is Ananya calling from Dariaan. You recently showed interest through our Meta ad?"
    assert coerce_stored_greeting("sellers", g) == ""


def test_sellers_rejects_vernikaai_greeting():
    g = "Hi, this is Priya from Dhyeya IAS — got a quick minute to talk about your UPSC?"
    assert coerce_stored_greeting("sellers", g) == ""


def test_real_estate_rejects_sellers_prompt():
    sellers = "You call sellers to discuss GMT (Get My Quote)"
    foreign = detect_foreign_role(sellers, "real_estate")
    assert foreign == "sellers", foreign
    out = coerce_role_prompt("real_estate", sellers, "You are Priya, property consultant.")
    assert "Priya" in out


def test_vernikaai_rejects_legacy_dhyeya_db():
    dhyeya = "You are Priya, academic counselor at Dhyeya IAS for UPSC coaching."
    dariaan = "You are Ananya at Dariaan fashion accelerator."
    assert coerce_role_prompt("vernikaai", dhyeya, dariaan) == dariaan


def test_vernikaai_rejects_procucev_sellers():
    assert detect_foreign_role("You call sellers about GMT", "vernikaai") == "sellers"


def test_validate_tuning_blocks_cross_save():
    err = validate_role_tuning(
        "buyers",
        prompt="You call sellers to discuss GMT (Get My Quote)",
        rag="",
        greeting="",
    )
    assert err and "Sellers" in err


def test_resolved_prompt_sandbox_rfqs():
    polluted = {"prompt": "You call sellers to discuss GMT (Get My Quote)", "rag": ""}
    p, _ = _resolved_prompt_and_rag("rfqs", polluted)
    assert "Radhika" in p or "RFQ" in p


if __name__ == "__main__":
    test_manual_camp_legacy_hyphen()
    test_rfqs_rejects_sellers_greeting()
    test_sellers_rejects_dariaan_greeting()
    test_sellers_rejects_vernikaai_greeting()
    test_real_estate_rejects_sellers_prompt()
    test_vernikaai_rejects_legacy_dhyeya_db()
    test_vernikaai_rejects_procucev_sellers()
    test_validate_tuning_blocks_cross_save()
    test_resolved_prompt_sandbox_rfqs()
    print("OK — all role sandbox checks passed")
