from __future__ import annotations

from typing import Optional

from app.models import ChatResponse, StadiumStatusResponse
from app.services.gemini_agent import run_gemini_agent


def answer_question(
    message: str,
    status: StadiumStatusResponse,
    api_key: Optional[str] = None
) -> ChatResponse:
    if not status.zones:
        return ChatResponse(
            answer="No live stadium data is available yet. Load demo data or ingest signals first.",
            suggested_questions=[
                "Load demo data first",
                "What is the highest risk zone?",
            ],
            thoughts=["Aborted agent execution: Stadium data is currently empty."]
        )

    return run_gemini_agent(message, status.tenant_id, status.stadium_id, api_key=api_key)