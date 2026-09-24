from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .companion import PersonalCompanion


class MessageRequest(BaseModel):
    message: str
    user_name: str = "User"
    api_key: str | None = None
    provider: str = "anthropic"


app = FastAPI(title="Personal AI Companion")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root() -> FileResponse:
    gui_path = Path(__file__).resolve().parent.parent.parent / "gui.html"
    return FileResponse(gui_path)


@app.post("/turn")
def handle_turn(payload: MessageRequest) -> dict[str, Any]:
    companion = PersonalCompanion(
        vault_root=Path("vault"),
        user_name=payload.user_name,
        api_key=payload.api_key,
        provider=payload.provider,
    )
    result = companion.process_turn(payload.message)
    return {
        "interpretation": result["interpretation"],
        "action": result["action"],
        "reply": result["reply"],
        "saved_entry": str(result["saved_entry"]),
    }


@app.post("/api/chat")
def api_chat(payload: MessageRequest) -> dict[str, Any]:
    companion = PersonalCompanion(
        vault_root=Path("vault"),
        user_name=payload.user_name,
        api_key=payload.api_key,
        provider=payload.provider,
    )
    result = companion.process_turn(payload.message)
    return {
        "interpretation": result["interpretation"],
        "action": result["action"],
        "reply": result["reply"],
        "saved_entry": str(result["saved_entry"]),
        "privacy": result.get("privacy"),
        "evaluation": result.get("evaluation"),
        "aggregate_data": result.get("aggregate_data"),
    }
