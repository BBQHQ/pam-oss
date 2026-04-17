"""Gratitude tile endpoints."""

import time

from fastapi import APIRouter
from pydantic import BaseModel
from app.services.gratitude import (
    add_tile, delete_tile, get_progress_snapshot, get_tiles_shell, update_tile,
)

router = APIRouter(prefix="/gratitude", tags=["gratitude"])


@router.get("/")
async def list_tiles():
    """Shell only — no progress enrichment. Fetch `/gratitude/progress`
    after this to fill in progress tile labels."""
    t0 = time.perf_counter()
    tiles = await get_tiles_shell()
    print(f"[gratitude] GET / {(time.perf_counter() - t0) * 1000:.0f}ms ({len(tiles)} tiles)")
    return tiles


@router.get("/progress")
async def progress_snapshot():
    """Enrichment data per data_source, 60s cached."""
    t0 = time.perf_counter()
    snap = await get_progress_snapshot()
    print(f"[gratitude] GET /progress {(time.perf_counter() - t0) * 1000:.0f}ms")
    return snap


@router.post("/")
async def create(body: dict):
    return await add_tile(
        title=body["title"],
        body=body.get("body", ""),
        icon=body.get("icon", ""),
        category=body.get("category", "pillar"),
        data_source=body.get("data_source"),
        color=body.get("color", "rgba(232, 183, 106, 0.3)"),
    )


class TileUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    icon: str | None = None
    color: str | None = None


@router.put("/{tile_id}")
async def edit(tile_id: str, body: TileUpdate):
    tile = await update_tile(tile_id, title=body.title, body=body.body,
                             icon=body.icon, color=body.color)
    if not tile:
        return {"error": "Not found"}
    return tile


@router.delete("/{tile_id}")
async def remove(tile_id: str):
    return {"deleted": await delete_tile(tile_id)}
