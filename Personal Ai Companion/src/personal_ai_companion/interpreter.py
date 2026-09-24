from __future__ import annotations

import re
from typing import Any


class Interpreter:
    """Lightweight heuristic interpreter for v1."""

    @staticmethod
    def interpret(message: str) -> dict[str, Any]:
        normalized = message.strip()
        lower = normalized.lower()

        explicit_private_signal = any(
            word in lower for word in ["private", "secret", "just between us", "keep this to myself", "confidential", "between us"]
        )
        emotional_disclosure = any(
            word in lower for word in ["anxious", "panic", "ashamed", "embarrassed", "afraid", "personal", "confession", "scared", "overwhelmed", "i need to tell you something"]
        )

        if any(word in lower for word in ["project", "task", "deadline", "milestone", "roadmap", "plan"]):
            mode = "project"
        elif explicit_private_signal:
            mode = "confide"
        elif any(word in lower for word in ["remember", "recall", "what did i say", "who did i mention", "history"]):
            mode = "recall"
        elif any(word in lower for word in ["how are you", "check in", "how's it going", "feeling", "emotion", "stress", "overwhelmed"]):
            mode = "checkin"
        elif emotional_disclosure:
            mode = "checkin"
        else:
            mode = "mixed"

        mode_requires_confirmation = mode == "confide" and not explicit_private_signal
        if emotional_disclosure and not explicit_private_signal:
            mode_requires_confirmation = True

        intent = "conversation"
        if re.search(r"\?", normalized):
            intent = "question"
        if re.search(r"\b(i need|i want|please|can you|could you)\b", lower):
            intent = "request"

        entities = {"people": [], "projects": []}
        for token in re.findall(r"\b[A-Z][a-z]+\b", normalized):
            if token.lower() not in {"i", "i'm", "im"}:
                entities["people"].append(token)

        needs = []
        if intent == "question":
            needs.append("answer")
        if mode in {"checkin", "confide"}:
            needs.append("support")
        if mode == "project":
            needs.append("planning")

        urgency = 0.2
        if any(word in lower for word in ["urgent", "asap", "tomorrow", "today", "immediately"]):
            urgency = 0.8

        return {
            "literal_content": normalized,
            "topic": "general",
            "entities": entities,
            "intent": intent,
            "implicit_intent": "understand_context",
            "emotional_state": "neutral",
            "needs": needs,
            "urgency": urgency,
            "certainty": 0.6,
            "mode_suggestion": mode,
            "mode_requires_confirmation": mode_requires_confirmation,
            "prediction_check": {
                "had_prior_prediction": False,
                "prior_predicted_action": None,
                "prior_predicted_reaction": None,
                "actual_reaction_category": "continued",
                "prediction_error": "none",
            },
        }
