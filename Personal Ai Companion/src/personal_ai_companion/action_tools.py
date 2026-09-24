from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Any


VALID_ACTIONS = {
    "ANSWER",
    "ASK",
    "ACKNOWLEDGE",
    "CHALLENGE",
    "CLARIFY",
    "REFLECT",
    "ENCOURAGE",
    "WAIT",
    "CHANGE_TOPIC",
    "RECALL",
    "EXPLAIN",
    "DO_NOTHING",
}

VALID_SAVE_TARGETS = {"normal", "person", "secrets"}


@dataclass
class SelectActionResult:
    action: str
    based_on_hypotheses: list[str]
    predicted_user_reaction: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SaveMemoryResult:
    save_to: str
    file_path: str
    status: str | None = None
    confidence: float | None = None
    content: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ActionToolRegistry:
    """Schema-ready tool output layer for select_action and save_memory."""

    @staticmethod
    def validate_select_action(payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("select_action payload must be a dictionary")
        if "action" not in payload:
            raise ValueError("select_action action is required")
        if payload["action"] not in VALID_ACTIONS:
            raise ValueError(f"invalid select_action action: {payload['action']!r}")
        if "predicted_user_reaction" not in payload:
            raise ValueError("select_action predicted_user_reaction is required")
        if "based_on_hypotheses" in payload and not isinstance(payload["based_on_hypotheses"], list):
            raise ValueError("select_action based_on_hypotheses must be a list")
        normalized = {
            "action": str(payload["action"]),
            "predicted_user_reaction": str(payload["predicted_user_reaction"]),
            "based_on_hypotheses": list(payload.get("based_on_hypotheses") or []),
        }
        return normalized

    @staticmethod
    def validate_save_memory(payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("save_memory payload must be a dictionary")
        if "save_to" not in payload:
            raise ValueError("save_memory save_to is required")
        if payload["save_to"] not in VALID_SAVE_TARGETS:
            raise ValueError(f"invalid save_memory save_to: {payload['save_to']!r}")
        if "file_path" not in payload:
            raise ValueError("save_memory file_path is required")
        if "content" not in payload:
            raise ValueError("save_memory content is required")
        normalized = {
            "save_to": str(payload["save_to"]),
            "file_path": str(payload["file_path"]),
            "status": payload.get("status"),
            "confidence": payload.get("confidence"),
            "content": str(payload["content"]),
        }
        return normalized

    @staticmethod
    def select_action(action: str, predicted_user_reaction: str, based_on_hypotheses: list[str] | None = None) -> SelectActionResult:
        payload = ActionToolRegistry.validate_select_action(
            {
                "action": action,
                "predicted_user_reaction": predicted_user_reaction,
                "based_on_hypotheses": based_on_hypotheses or [],
            }
        )
        return SelectActionResult(
            action=payload["action"],
            based_on_hypotheses=payload["based_on_hypotheses"],
            predicted_user_reaction=payload["predicted_user_reaction"],
        )

    @staticmethod
    def save_memory(save_to: str, file_path: str, content: str, status: str | None = None, confidence: float | None = None) -> SaveMemoryResult:
        payload = ActionToolRegistry.validate_save_memory(
            {
                "save_to": save_to,
                "file_path": file_path,
                "content": content,
                "status": status,
                "confidence": confidence,
            }
        )
        return SaveMemoryResult(
            save_to=payload["save_to"],
            file_path=payload["file_path"],
            status=payload["status"],
            confidence=payload["confidence"],
            content=payload["content"],
        )
