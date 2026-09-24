from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


class MemoryIndexer:
    """Index Markdown files into structured chunks, including person-note hypothesis blocks."""

    def __init__(self, vault_root: str | Path | None = None):
        self.vault_root = Path(vault_root) if vault_root else Path("vault")

    def index_vault(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for path in sorted(self.vault_root.rglob("*.md")):
            if "_meta" in path.parts or path.name.startswith("."):
                continue
            rows.extend(self._index_file(path))
        return rows

    def _index_file(self, path: Path) -> list[dict[str, Any]]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if path.name.endswith(".md"):
            return self._parse_markdown_sections(path, text)
        return []

    def _parse_markdown_sections(self, path: Path, text: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        lines = text.splitlines()
        current_heading = None
        current_block: list[str] = []
        current_meta: dict[str, Any] | None = None
        in_meta = False

        for line in lines:
            if line.strip().startswith("<!-- meta:"):
                meta_text = line.strip()[len("<!-- meta:") : -len("-->")].strip()
                try:
                    current_meta = json.loads(meta_text)
                except json.JSONDecodeError:
                    current_meta = None
                if current_block:
                    rows.append(self._row_from_block(path, current_heading, current_block, current_meta))
                    current_block = []
                continue

            if line.startswith("## "):
                if current_block and current_heading is not None:
                    rows.append(self._row_from_block(path, current_heading, current_block, current_meta))
                current_heading = line[3:].strip()
                current_block = []
                current_meta = None
                continue

            if current_heading is not None:
                current_block.append(line)

        if current_block and current_heading is not None:
            rows.append(self._row_from_block(path, current_heading, current_block, current_meta))

        if not rows and text.strip():
            rows.append(
                {
                    "file_path": str(path.relative_to(self.vault_root)),
                    "entry_anchor": path.stem,
                    "chunk_text": text[:500],
                    "status": None,
                    "confidence": None,
                    "date": self._extract_date_text(text),
                    "type": self._infer_type(path),
                }
            )
        return rows

    def _row_from_block(self, path: Path, heading: str, lines: list[str], meta: dict[str, Any] | None) -> dict[str, Any]:
        text = "\n".join(lines).strip()
        status = (meta or {}).get("status")
        confidence = (meta or {}).get("confidence")
        return {
            "file_path": str(path.relative_to(self.vault_root)),
            "entry_anchor": heading,
            "chunk_text": text,
            "status": status,
            "confidence": confidence,
            "date": self._extract_date_text(text),
            "type": self._infer_type(path),
        }

    @staticmethod
    def _extract_date_text(text: str) -> str | None:
        match = re.search(r"date:\s*(\d{4}-\d{2}-\d{2})", text)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def _infer_type(path: Path) -> str:
        if "daily" in path.parts:
            return "daily"
        if "people" in path.parts:
            return "person"
        if "projects" in path.parts:
            return "project-log"
        if "core" in path.parts:
            return "core"
        return "markdown"
