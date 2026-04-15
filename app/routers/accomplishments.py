"""Accomplishments log endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel
from app.services import accomplishments

router = APIRouter(prefix="/accomplishments", tags=["accomplishments"])


class ManualAccomplishment(BaseModel):
    text: str
    metadata: dict | None = None


@router.get("/")
async def list_(limit: int = 100, since: str | None = None, source: str | None = None):
    return await accomplishments.list_accomplishments(
        limit=limit, since=since, source_filter=source
    )


@router.post("/")
async def create(body: ManualAccomplishment):
    return await accomplishments.log("manual", body.text, metadata=body.metadata)


@router.delete("/{accomplishment_id}")
async def remove(accomplishment_id: int):
    return {"deleted": await accomplishments.delete(accomplishment_id)}


@router.post("/backfill")
async def backfill():
    """Walk existing done todos, answered questions, and completed tasks
    and log them retroactively. Idempotent — safe to re-run."""
    return await accomplishments.backfill()
