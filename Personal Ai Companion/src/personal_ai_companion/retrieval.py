from __future__ import annotations

from datetime import datetime
from math import exp
from typing import Any


class RetrievalEngine:
    @staticmethod
    def rank(query: str, interpretation: dict[str, Any], chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        mode = interpretation.get("mode_suggestion", "mixed")
        alpha, beta = {
            "recall": (0.7, 0.1),
            "checkin": (0.4, 0.4),
            "project": (0.5, 0.3),
            "confide": (0.65, 0.15),
            "mixed": (0.5, 0.3),
        }.get(mode, (0.5, 0.3))

        normalized_query = query.lower()
        entity_overlap = set()
        for value in interpretation.get("entities", {}).values():
            if isinstance(value, list):
                entity_overlap.update(str(item).lower() for item in value)

        scored: list[tuple[float, dict[str, Any]]] = []
        for chunk in chunks:
            chunk_text = str(chunk.get("chunk_text", "")).lower()
            similarity = 1.0 if normalized_query in chunk_text else 0.2
            recency = 1.0
            date_value = chunk.get("date")
            if date_value:
                try:
                    dt = datetime.fromisoformat(date_value)
                    delta_days = (datetime.utcnow().date() - dt.date()).days
                    recency = exp(-((delta_days / 30) * 0.69314718056))
                except ValueError:
                    pass
            relevance_boost = 1.0 if any(entity in chunk_text for entity in entity_overlap) else 0.0
            combined = alpha * similarity + beta * recency + (1.0 - alpha - beta) * relevance_boost
            scored.append((combined, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [chunk for _, chunk in scored]

    @staticmethod
    def retrieve(query: str, interpretation: dict[str, Any], chunks: list[dict[str, Any]], *, limit: int = 8):
        ranked = RetrievalEngine.rank(query, interpretation, chunks)[:limit]
        return ranked
