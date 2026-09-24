from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from personal_ai_companion.action_tools import ActionToolRegistry
from personal_ai_companion.aggregation import AggregateEngine
from personal_ai_companion.claude_bridge import ClaudeBridge
from personal_ai_companion.companion import PersonalCompanion
from personal_ai_companion.consolidation import WeeklyConsolidator
from personal_ai_companion.curation import HumanCurationEngine
from personal_ai_companion.indexer import MemoryIndexer
from personal_ai_companion.interpreter import Interpreter
from personal_ai_companion.vault import VaultManager


def test_interpreter_mode_detects_project_query():
    interpretation = Interpreter.interpret("I need help planning my project deadline and roadmap")
    assert interpretation["mode_suggestion"] == "project"
    assert "planning" in interpretation["needs"]


def test_vault_manager_creates_scaffold(tmp_path):
    manager = VaultManager(tmp_path)
    vault_root = manager.ensure_scaffold()

    assert (vault_root / "daily").exists()
    assert (vault_root / "people").exists()
    assert (vault_root / "core").exists()
    assert (vault_root / "_meta" / "predictions_log.jsonl").exists()


def test_write_and_recall(tmp_path):
    manager = VaultManager(tmp_path)
    manager.ensure_scaffold()
    manager.write_daily_entry("I am working on a book draft and need to remember this later.")

    results = manager.search("book draft")
    assert len(results) >= 1
    assert "book draft".lower() in results[0].chunk_text.lower()


def test_vault_notes_use_yaml_frontmatter_and_inline_meta(tmp_path):
    manager = VaultManager(tmp_path)
    manager.ensure_scaffold()

    daily_path = manager.write_daily_entry("I am working on a book draft and need to remember this later.")
    daily_text = daily_path.read_text(encoding="utf-8")
    assert daily_text.startswith("---\n")
    assert "type: daily" in daily_text
    assert "<!-- meta:" in daily_text

    person_path = manager.write_person_note("Ava", "She prefers direct feedback.")
    person_text = person_path.read_text(encoding="utf-8")
    assert person_text.startswith("---\n")
    assert "type: person" in person_text
    assert "<!-- meta:" in person_text


def test_companion_turn_processing(tmp_path):
    companion = PersonalCompanion(vault_root=tmp_path)
    result = companion.process_turn("I need help planning my project deadline and roadmap")

    assert result["interpretation"]["mode_suggestion"] == "project"
    assert result["saved_entry"].exists()
    assert result["prediction"]["action"] in {"ANSWER", "ASK", "ACKNOWLEDGE", "EXPLAIN", "RECALL"}


def test_confide_mode_requires_explicit_user_signal():
    from personal_ai_companion.interpreter import Interpreter
    interpretation = Interpreter.interpret("I feel really anxious and need to tell you something personal")

    assert interpretation["mode_suggestion"] in {"checkin", "mixed"}
    assert interpretation["mode_requires_confirmation"] is True


def test_companion_fallback_reply_is_generated(tmp_path):
    companion = PersonalCompanion(vault_root=tmp_path)
    result = companion.process_turn("I want to remember what I said about my sister last month")

    assert "reply" in result
    assert isinstance(result["reply"], str)
    assert len(result["reply"]) > 0


def test_memory_indexer_parses_person_hypotheses(tmp_path):
    vault = tmp_path / "vault"
    people = vault / "people"
    people.mkdir(parents=True)
    (people / "sarah.md").write_text(
        "---\nid: \"sarah\"\ntype: person\nsensitivity: normal\nsource: user\n---\n\n"
        "## Communication Style\n"
        "<!-- meta: {\"status\": \"fact\", \"confidence\": 1.0} -->\n"
        "Prefers conceptual explanations.\n\n"
        "## Hypothesis: prefers brevity under urgency\n"
        "<!-- meta: {\"status\": \"hypothesis\", \"confidence\": 0.71, \"evidence_count\": 4} -->\n"
        "She prefers shorter answers when rushed.\n",
        encoding="utf-8",
    )

    indexer = MemoryIndexer(vault_root=vault)
    rows = indexer.index_vault()

    assert len(rows) >= 2
    statuses = {row["status"] for row in rows}
    assert "fact" in statuses
    assert "hypothesis" in statuses


def test_weekly_consolidator_updates_hypothesis_confidence(tmp_path):
    vault = tmp_path / "vault"
    people = vault / "people"
    people.mkdir(parents=True)
    (people / "sarah.md").write_text(
        "---\nid: \"sarah\"\ntype: person\nsensitivity: normal\nsource: user\n---\n\n"
        "## Hypothesis: prefers brevity under urgency\n"
        "<!-- meta: {\"status\": \"hypothesis\", \"confidence\": 0.71, \"evidence_count\": 4} -->\n"
        "She prefers shorter answers when rushed.\n",
        encoding="utf-8",
    )
    (vault / "_meta").mkdir(exist_ok=True)
    (vault / "_meta" / "predictions_log.jsonl").write_text(
        '{"action": "ANSWER", "predicted_user_reaction": "continue", "based_on_hypotheses": ["Hypothesis: prefers brevity under urgency"]}\n'
        '{"action": "ANSWER", "predicted_user_reaction": "continue", "based_on_hypotheses": ["Hypothesis: prefers brevity under urgency"]}\n',
        encoding="utf-8",
    )

    consolidator = WeeklyConsolidator(vault_root=vault)
    changed = consolidator.consolidate_week()

    assert any("hypothesis" in entry.lower() for entry in changed)


def test_human_curation_blocks_automatic_fact_promotion(tmp_path):
    vault = tmp_path / "vault"
    people = vault / "people"
    people.mkdir(parents=True)
    (people / "ava.md").write_text(
        "---\nid: \"ava\"\ntype: person\nsensitivity: normal\nsource: user\n---\n\n"
        "## Hypothesis: dislikes confrontation\n"
        "<!-- meta: {\"status\": \"hypothesis\", \"confidence\": 0.74, \"evidence_count\": 2} -->\n"
        "She avoids conflict when stressed.\n",
        encoding="utf-8",
    )

    curation = HumanCurationEngine(vault_root=vault)
    proposals = curation.propose_hypothesis_promotions("Ava")

    assert len(proposals) >= 1
    assert proposals[0].accepted is False
    assert "Awaiting human approval" in proposals[0].reason
    assert (vault / "core" / "_proposed" / "ava-promotion.md").exists()


def test_secrets_are_written_to_separate_vault_and_excluded_from_normal_search(tmp_path):
    manager = VaultManager(tmp_path)
    manager.ensure_scaffold()

    secret_path = manager.write_secret_entry("just between us", "I am worried about my finances")

    assert secret_path.exists()
    assert "secrets" in str(secret_path)
    assert not any("I am worried about my finances" in item.chunk_text for item in manager.search("finances"))


def test_action_schema_validation_and_dead_letter_logging(tmp_path):
    manager = VaultManager(tmp_path)
    manager.ensure_scaffold()

    invalid_payload = {"action": "NOT_A_REAL_ACTION", "predicted_user_reaction": "continue"}

    with pytest.raises(ValueError):
        ActionToolRegistry.validate_select_action(invalid_payload)

    entry = manager.log_dead_letter(
        tool_name="select_action",
        payload=invalid_payload,
        error="invalid enum value",
    )

    assert entry["tool_name"] == "select_action"
    assert (tmp_path / "_meta" / "dead_letter.jsonl").exists()
    assert "invalid enum value" in (tmp_path / "_meta" / "dead_letter.jsonl").read_text(encoding="utf-8")


def test_evaluation_log_and_project_aggregate_are_generated(tmp_path):
    vault = tmp_path / "vault"
    manager = VaultManager(vault)
    manager.ensure_scaffold()
    manager.write_project_entry(
        project_name="book-manuscript",
        content="## Blocker\nThe chapter draft is delayed.\n\n## Progress\nDrafting the outline.\n",
    )

    companion = PersonalCompanion(vault_root=vault)
    result = companion.process_turn("I need to finish the book manuscript this week")

    assert "evaluation" in result
    assert "aggregate_data" in result
    assert (vault / "_meta" / "evaluation_log.jsonl").exists()
    assert isinstance(result["aggregate_data"], dict)


def test_companion_accepts_ui_api_key_and_provider(tmp_path):
    companion = PersonalCompanion(vault_root=tmp_path, api_key="ui-key", provider="gemini")

    assert companion.claude.api_key == "ui-key"
    assert companion.claude.provider == "gemini"


def test_gui_uses_relative_chat_url():
    gui_text = Path("gui.html").read_text(encoding="utf-8")

    assert "/api/chat" in gui_text
    assert "http://localhost:8000/api/chat" not in gui_text


def test_fallback_reply_mentions_api_key_setup():
    message = ClaudeBridge._fallback_reply("hello")

    assert "API key" in message or "Anthropic" in message or "Gemini" in message


def test_browser_chat_endpoint_works():
    from personal_ai_companion.server import app

    client = TestClient(app)
    response = client.post(
        "/api/chat",
        json={"message": "I need help planning my project deadline and roadmap"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reply"]
    assert payload["action"] in {"ANSWER", "ASK", "ACKNOWLEDGE", "EXPLAIN", "RECALL"}
