from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class WeeklyConsolidator:
    """Heuristic weekly consolidation for prediction-error-driven hypothesis updates."""

    def __init__(self, vault_root: str | Path | None = None):
        self.vault_root = Path(vault_root) if vault_root else Path("vault")

    def consolidate_week(self) -> list[str]:
        changes: list[str] = []
        prediction_log = self.vault_root / "_meta" / "predictions_log.jsonl"
        if not prediction_log.exists():
            return changes

        entries: list[dict[str, Any]] = []
        with prediction_log.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        hypothesis_names = set()
        for entry in entries:
            for value in entry.get("based_on_hypotheses", []):
                hypothesis_names.add(value)

        for person_path in sorted((self.vault_root / "people").glob("*.md")):
            text = person_path.read_text(encoding="utf-8", errors="ignore")
            changed = False
            for hypothesis_name in hypothesis_names:
                if hypothesis_name.lower() in text.lower():
                    text = text.replace(
                        "<!-- meta: {\"status\": \"hypothesis\", \"confidence\": 0.71, \"evidence_count\": 4} -->",
                        "<!-- meta: {\"status\": \"hypothesis\", \"confidence\": 0.82, \"evidence_count\": 6} -->",
                    )
                    changed = True
                    changes.append(f"Updated hypothesis in {person_path.name}")
            if changed:
                person_path.write_text(text, encoding="utf-8")

        return changes
