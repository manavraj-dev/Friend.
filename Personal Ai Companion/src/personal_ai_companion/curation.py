from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CurationDecision:
    accepted: bool
    type: str
    target: str
    reason: str


class HumanCurationEngine:
    """Human-in-the-loop proposal and fact-promotion flow for person and core memory."""

    def __init__(self, vault_root: str | Path | None = None):
        self.vault_root = Path(vault_root) if vault_root else Path("vault")

    def propose_hypothesis_promotions(self, person_name: str) -> list[CurationDecision]:
        person_path = self.vault_root / "people" / f"{person_name.lower().replace(' ', '-')}.md"
        if not person_path.exists():
            return []

        text = person_path.read_text(encoding="utf-8", errors="ignore")
        if "status\": \"hypothesis\"" not in text:
            return []

        proposal_dir = self.vault_root / "core" / "_proposed"
        proposal_dir.mkdir(parents=True, exist_ok=True)
        proposal_path = proposal_dir / f"{person_name.lower().replace(' ', '-')}-promotion.md"
        proposal_path.write_text(
            "# Proposed fact promotion\n\nThis proposal is awaiting human approval.\n\n",
            encoding="utf-8",
        )

        return [
            CurationDecision(
                accepted=False,
                type="person-hypothesis",
                target=person_path.name,
                reason="Awaiting human approval before converting hypothesis to fact.",
            )
        ]

    def propose_core_updates(self) -> list[CurationDecision]:
        proposal_dir = self.vault_root / "core" / "_proposed"
        proposal_dir.mkdir(parents=True, exist_ok=True)
        proposal_path = proposal_dir / "core-updates.md"
        proposal_path.write_text(
            "# Proposed core memory updates\n\nAwaiting human review.\n",
            encoding="utf-8",
        )

        return [
            CurationDecision(
                accepted=False,
                type="core-memory",
                target="core",
                reason="Awaiting human approval before writing to curated core memory.",
            )
        ]
