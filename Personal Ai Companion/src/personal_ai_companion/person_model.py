from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PersonHypothesis:
    name: str
    title: str
    status: str = "hypothesis"
    confidence: float = 0.5
    evidence_count: int = 0
    evidence: list[str] = field(default_factory=list)
    notes: str = ""


class PersonModel:
    """Loads structured person beliefs from person note sections."""

    def __init__(self, vault_root: str | Path | None = None):
        self.vault_root = Path(vault_root) if vault_root else Path("vault")

    def load_for_person(self, person_name: str) -> list[PersonHypothesis]:
        person_path = self.vault_root / "people" / f"{person_name.lower().replace(' ', '-')}.md"
        if not person_path.exists():
            return []

        text = person_path.read_text(encoding="utf-8", errors="ignore")
        hypotheses: list[PersonHypothesis] = []
        current_title = None
        current_note: list[str] = []
        current_status = None
        current_confidence = 0.5
        evidence_count = 0
        evidence: list[str] = []

        for raw_line in text.splitlines():
            if raw_line.startswith("## "):
                if current_title:
                    hypotheses.append(
                        PersonHypothesis(
                            name=person_name,
                            title=current_title,
                            status=current_status or "observation",
                            confidence=current_confidence,
                            evidence_count=evidence_count,
                            evidence=evidence,
                            notes="\n".join(current_note).strip(),
                        )
                    )
                current_title = raw_line[3:].strip()
                current_note = []
                current_status = "observation"
                current_confidence = 0.5
                evidence_count = 0
                evidence = []
                continue

            if "meta:" in raw_line:
                try:
                    import json

                    meta_text = raw_line.split("meta:", 1)[1].strip().strip("- ")
                    meta = json.loads(meta_text)
                    current_status = meta.get("status", current_status)
                    current_confidence = float(meta.get("confidence", current_confidence))
                    evidence_count = int(meta.get("evidence_count", evidence_count))
                    evidence = list(meta.get("evidence", evidence))
                except Exception:
                    pass
                continue

            if current_title:
                current_note.append(raw_line)

        if current_title:
            hypotheses.append(
                PersonHypothesis(
                    name=person_name,
                    title=current_title,
                    status=current_status or "observation",
                    confidence=current_confidence,
                    evidence_count=evidence_count,
                    evidence=evidence,
                    notes="\n".join(current_note).strip(),
                )
            )

        return hypotheses
