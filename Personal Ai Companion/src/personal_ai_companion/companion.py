from __future__ import annotations

from pathlib import Path
from typing import Any

from .action_tools import ActionToolRegistry
from .aggregation import AggregateEngine
from .claude_bridge import ClaudeBridge
from .consolidation import WeeklyConsolidator
from .curation import HumanCurationEngine
from .indexer import MemoryIndexer
from .interpreter import Interpreter
from .person_model import PersonModel
from .privacy import PrivacyGuard
from .retrieval import RetrievalEngine
from .vault import VaultManager


class PersonalCompanion:
    """Main orchestration object for a single local companion instance."""

    def __init__(self, vault_root: str | Path | None = None, user_name: str = "User", api_key: str | None = None, provider: str = "anthropic"):
        self.vault_root = Path(vault_root) if vault_root else Path("vault")
        self.user_name = user_name
        self.provider = provider or "anthropic"
        self.vault = VaultManager(self.vault_root)
        self.vault.ensure_scaffold()
        self.claude = ClaudeBridge(api_key=api_key, provider=self.provider)
        self.indexer = MemoryIndexer(self.vault_root)
        self.person_model = PersonModel(self.vault_root)
        self.consolidator = WeeklyConsolidator(self.vault_root)
        self.curation = HumanCurationEngine(self.vault_root)
        self.aggregator = AggregateEngine(self.vault_root)

    def process_turn(self, message: str) -> dict[str, Any]:
        interpretation = Interpreter.interpret(message)
        path = self.vault.write_daily_entry(
            f"User message: {message}\n\nInterpretation: {interpretation['mode_suggestion']}"
        )

        privacy = PrivacyGuard.evaluate(interpretation, message)
        action = self._choose_action(interpretation)
        tool_action = ActionToolRegistry.select_action(
            action=action,
            predicted_user_reaction="the user continues the conversation with a specific follow-up.",
            based_on_hypotheses=[],
        )
        prediction = self.vault.append_prediction(
            action=action,
            predicted_user_reaction=tool_action.predicted_user_reaction,
            based_on_hypotheses=tool_action.based_on_hypotheses,
        )

        indexed_rows = self.indexer.index_vault()
        retrieval = RetrievalEngine.retrieve(
            message,
            interpretation,
            indexed_rows,
            limit=8,
        )
        if privacy.store_in_secrets:
            secret_path = self.vault.write_secret_entry(
                interpretation.get("mode_suggestion", "confide"),
                message,
            )
            save_memory = ActionToolRegistry.save_memory(
                save_to="secrets",
                file_path=str(secret_path.relative_to(self.vault_root)),
                content=f"User message: {message}",
                status="secret",
                confidence=0.9,
            )
        else:
            save_memory = ActionToolRegistry.save_memory(
                save_to="normal",
                file_path=str(path.relative_to(self.vault_root)) if path else "daily/entry.md",
                content=f"User message: {message}",
                status="observation",
                confidence=0.6,
            )

        evaluation = self.vault.log_evaluation(
            turn_id=f"turn-{len(self.vault.read_predictions()) + 1}",
            prediction_error=interpretation.get("prediction_check", {}).get("prediction_error", "none"),
            action_match=True,
            save_memory_valid=True,
        )
        aggregate_data = self.aggregator.summarize_projects()
        consolidation = self.consolidator.consolidate_week()
        curation = {
            "person_proposals": self.curation.propose_hypothesis_promotions("Ava"),
            "core_proposals": self.curation.propose_core_updates(),
        }
        reply = self._generate_reply(message, interpretation, action, retrieval)

        return {
            "interpretation": interpretation,
            "saved_entry": path,
            "prediction": prediction,
            "action": action,
            "reply": reply,
            "retrieval": retrieval,
            "privacy": privacy,
            "tool_action": tool_action.to_dict(),
            "save_memory": save_memory.to_dict(),
            "consolidation": consolidation,
            "curation": curation,
            "evaluation": evaluation,
            "aggregate_data": aggregate_data,
        }

    @staticmethod
    def _choose_action(interpretation: dict[str, Any]) -> str:
        mode = interpretation.get("mode_suggestion", "mixed")
        if mode == "project":
            return "EXPLAIN"
        if mode == "recall":
            return "RECALL"
        if mode == "confide":
            return "ACKNOWLEDGE"
        if interpretation.get("intent") == "question":
            return "ANSWER"
        return "ACKNOWLEDGE"

    def _generate_reply(
        self,
        message: str,
        interpretation: dict[str, Any],
        action: str,
        retrieval: Any | None = None,
    ) -> str:
        system_prompt = (
            "You are a private reflection companion. Keep memory local-first and never infer secrets "
            "without explicit user confirmation. Use the user's context, but do not claim clinical confidentiality."
        )
        context_lines = [
            f"Mode: {interpretation.get('mode_suggestion', 'mixed')}",
            f"Intent: {interpretation.get('intent', 'conversation')}",
            f"Needs: {', '.join(interpretation.get('needs', [])) or 'none'}",
            f"Action selected: {action}",
        ]
        if retrieval is not None:
            context_lines.append("Relevant memory:")
            for row in retrieval[:3]:
                context_lines.append(f"- {row['file_path']}: {row['chunk_text'][:200]}")
        context = "\n".join(context_lines)
        return self.claude.generate(system_prompt=system_prompt, user_message=message, context=context)
