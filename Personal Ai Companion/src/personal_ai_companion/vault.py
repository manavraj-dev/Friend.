from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import DEFAULT_VAULT_ROOT, VAULT_DIRECTORIES


@dataclass
class MemoryChunk:
    file_path: str
    chunk_text: str
    date: str | None = None
    type: str | None = None
    tags: list[str] = field(default_factory=list)
    people: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    sensitivity: str = "normal"
    status: str | None = None
    confidence: float | None = None
    mood: str | None = None


class VaultManager:
    def __init__(self, vault_root: str | Path | None = None):
        self.vault_root = Path(vault_root) if vault_root else DEFAULT_VAULT_ROOT

    def ensure_scaffold(self) -> Path:
        self.vault_root.mkdir(parents=True, exist_ok=True)
        for folder in VAULT_DIRECTORIES:
            (self.vault_root / folder).mkdir(parents=True, exist_ok=True)

        prediction_log = self.vault_root / "_meta" / "predictions_log.jsonl"
        if not prediction_log.exists():
            prediction_log.write_text("", encoding="utf-8")

        eval_log = self.vault_root / "_meta" / "evaluation_log.jsonl"
        if not eval_log.exists():
            eval_log.write_text("", encoding="utf-8")

        index_log = self.vault_root / "_meta" / "index_log.jsonl"
        if not index_log.exists():
            index_log.write_text("", encoding="utf-8")

        dead_letter = self.vault_root / "_meta" / "dead_letter.jsonl"
        if not dead_letter.exists():
            dead_letter.write_text("", encoding="utf-8")

        core_people_index = self.vault_root / "core" / "people-index.md"
        if not core_people_index.exists():
            core_people_index.write_text(
                "# People Index\n\nThis file is auto-created for the companion vault.\n",
                encoding="utf-8",
            )

        core_system_notes = self.vault_root / "core" / "system-notes.md"
        if not core_system_notes.exists():
            core_system_notes.write_text(
                "# System Notes\n\nDefault operating assumptions for the companion.\n",
                encoding="utf-8",
            )

        return self.vault_root

    def write_daily_entry(self, content: str, *, title: str | None = None) -> Path:
        filename = (title or datetime.utcnow().strftime("%Y-%m-%d")).replace(" ", "-") + ".md"
        path = self.vault_root / "daily" / filename
        date = datetime.utcnow().strftime("%Y-%m-%d")

        meta = '{"status": "observation", "confidence": 0.6, "evidence_count": 1}'
        text = (
            "---\n"
            "id: daily\n"
            "type: daily\n"
            f"date: {date}\n"
            "source: user\n"
            "---\n\n"
            "## Daily note\n"
            f"<!-- meta: {meta} -->\n"
            f"{content.strip()}\n"
        )
        path.write_text(text, encoding="utf-8")
        return path

    def write_person_note(self, name: str, content: str, *, sensitivity: str = "normal") -> Path:
        path = self.vault_root / "people" / f"{name.lower().replace(' ', '-')}.md"
        frontmatter = (
            "---\n"
            f'id: "{name.lower().replace(" ", "-")}"\n'
            f'type: person\n'
            f'sensitivity: {sensitivity}\n'
            "source: user\n"
            "---\n\n"
        )
        meta = '{"status": "observation", "confidence": 0.5, "evidence_count": 1}'
        note_text = (
            f"{frontmatter}"
            "## Profile\n"
            f"<!-- meta: {meta} -->\n"
            f"{content.strip()}\n"
        )
        path.write_text(note_text, encoding="utf-8")
        return path

    def write_project_entry(self, project_name: str, content: str) -> Path:
        project_dir = self.vault_root / "projects" / project_name
        project_dir.mkdir(parents=True, exist_ok=True)
        path = project_dir / "overview.md"
        meta = '{"status": "observation", "confidence": 0.6, "evidence_count": 1}'
        text = (
            "---\n"
            f'id: "{project_name}"\n'
            "type: project\n"
            "source: user\n"
            "---\n\n"
            "## Project overview\n"
            f"<!-- meta: {meta} -->\n"
            f"{content.strip()}\n"
        )
        path.write_text(text, encoding="utf-8")
        return path

    def write_secret_entry(self, trigger: str, content: str, *, title: str | None = None) -> Path:
        safe_title = (title or f"secret-{datetime.utcnow().strftime('%Y%m%d-%H%M%S%f')}").replace(" ", "-")
        path = self.vault_root / "secrets" / f"{safe_title}.md"
        date = datetime.utcnow().strftime("%Y-%m-%d")
        meta = '{"status": "secret", "confidence": 0.95, "evidence_count": 1}'
        text = (
            "---\n"
            f'id: "{safe_title}"\n'
            "type: secret\n"
            f'date: {date}\n'
            "sensitivity: secret\n"
            "source: explicit-user-signal\n"
            "---\n\n"
            "## Secret note\n"
            f"<!-- meta: {meta} -->\n"
            f"User signal: {trigger}\n\n"
            f"{content.strip()}\n"
        )
        path.write_text(text, encoding="utf-8")
        return path

    def append_prediction(self, *, action: str, predicted_user_reaction: str, based_on_hypotheses: list[str]) -> dict[str, Any]:
        entry = {
            "turn_id": f"turn-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}",
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "predicted_user_reaction": predicted_user_reaction,
            "based_on_hypotheses": based_on_hypotheses,
        }
        log_path = self.vault_root / "_meta" / "predictions_log.jsonl"
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def read_predictions(self) -> list[dict[str, Any]]:
        log_path = self.vault_root / "_meta" / "predictions_log.jsonl"
        if not log_path.exists():
            return []
        entries: list[dict[str, Any]] = []
        with log_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return entries

    def log_dead_letter(self, *, tool_name: str, payload: dict[str, Any], error: str) -> dict[str, Any]:
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "tool_name": tool_name,
            "payload": payload,
            "error": error,
        }
        log_path = self.vault_root / "_meta" / "dead_letter.jsonl"
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def log_evaluation(self, *, turn_id: str, prediction_error: str, action_match: bool, save_memory_valid: bool) -> dict[str, Any]:
        entry = {
            "turn_id": turn_id,
            "timestamp": datetime.utcnow().isoformat(),
            "prediction_error": prediction_error,
            "action_match": action_match,
            "save_memory_valid": save_memory_valid,
        }
        log_path = self.vault_root / "_meta" / "evaluation_log.jsonl"
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def search(self, query: str, *, limit: int = 8) -> list[MemoryChunk]:
        if not self.vault_root.exists():
            return []
        results: list[MemoryChunk] = []
        for path in self.vault_root.rglob("*.md"):
            if "_meta" in path.parts or "secrets" in path.parts or path.name.startswith("."):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if query.lower() in text.lower():
                results.append(
                    MemoryChunk(
                        file_path=str(path.relative_to(self.vault_root)),
                        chunk_text=text[:600],
                        date=self._infer_date(text),
                        type="markdown",
                        tags=[],
                        people=[],
                        projects=[],
                    )
                )
                if len(results) >= limit:
                    break
        return results

    @staticmethod
    def _infer_date(text: str) -> str | None:
        for line in text.splitlines():
            if line.startswith("date:"):
                return line.split(":", 1)[1].strip()
        return None
