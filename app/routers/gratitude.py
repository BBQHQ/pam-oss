"""Gratitude tile endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel
from app.services.gratitude import get_tiles, add_tile, update_tile, delete_tile

router = APIRouter(prefix="/gratitude", tags=["gratitude"])


@router.get("/")
async def list_tiles():
    return await get_tiles()


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
