from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PrivacyDecision:
    store_in_secrets: bool
    requires_confirmation: bool
    reason: str


class PrivacyGuard:
    """Enforces the spec's boundary: confide mode only activates with explicit user signal."""

    @staticmethod
    def explicit_private_signal(message: str) -> bool:
        lower = message.lower()
        return any(
            phrase in lower
            for phrase in [
                "private",
                "secret",
                "just between us",
                "keep this to myself",
                "confidential",
                "between us",
                "keep this private",
                "not for others",
            ]
        )

    @classmethod
    def evaluate(cls, interpretation: dict[str, Any], message: str) -> PrivacyDecision:
        explicit_signal = cls.explicit_private_signal(message)
        mode = interpretation.get("mode_suggestion", "mixed")
        if mode == "confide" and explicit_signal:
            return PrivacyDecision(True, False, "explicit-private-signal")
        if mode == "confide" and not explicit_signal:
            return PrivacyDecision(False, True, "requires-confirmation")
        if any(word in message.lower() for word in ["anxious", "personal", "confession", "embarrassed", "scared"]) and not explicit_signal:
            return PrivacyDecision(False, True, "emotional-disclosure-without-explicit-private-signal")
        return PrivacyDecision(False, False, "normal-tier")
