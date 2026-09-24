from __future__ import annotations

from pathlib import Path
from typing import Any


class AggregateEngine:
    """Summaries of project and pattern data for the companion's aggregate context."""

    def __init__(self, vault_root: str | Path | None = None):
        self.vault_root = Path(vault_root) if vault_root else Path("vault")

    def summarize_projects(self) -> dict[str, Any]:
        projects_root = self.vault_root / "projects"
        if not projects_root.exists():
            return {"count": 0, "projects": [], "summary": "No active projects."}

        projects = []
        for project_dir in sorted(projects_root.iterdir()):
            if not project_dir.is_dir():
                continue
            summary_lines: list[str] = []
            blockers: list[str] = []
            for md_file in sorted(project_dir.glob("*.md")):
                text = md_file.read_text(encoding="utf-8", errors="ignore")
                for line in text.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("## "):
                        summary_lines.append(stripped[3:].strip())
                    if "blocker" in stripped.lower() or "blocked" in stripped.lower():
                        blockers.append(stripped)
            projects.append(
                {
                    "name": project_dir.name,
                    "files": sorted(p.name for p in project_dir.glob("*.md")),
                    "headings": summary_lines,
                    "blockers": blockers,
                }
            )

        summary = (
            f"{len(projects)} project(s) tracked; "
            + "; ".join(project["name"] for project in projects[:3])
            if projects
            else "No active projects."
        )
        return {"count": len(projects), "projects": projects, "summary": summary}
