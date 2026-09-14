"""
app/routers/assistant.py

POST /api/v1/assistant/query
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.assistant import answer_query
from app.database import get_db

router = APIRouter(prefix="/assistant", tags=["assistant"])


class QueryRequest(BaseModel):
    query: str


@router.post("/query")
async def query_assistant(
    body: QueryRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    Free-text operator query. Routes to engine tools and composes an answer.

    - If the language model is available (WATSONX_ENABLED=true), it explains
      the engine output in natural language.
    - If the language model is unavailable, a deterministic template response
      is returned. The system is fully functional in either mode.
    - The assistant never answers from its own knowledge when engines return nothing.
    """
    return await answer_query(body.query, db)
