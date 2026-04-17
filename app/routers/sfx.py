"""SFX management endpoints — list, upload, ingest from Myinstants, delete, update."""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.services import sfx
from app.services.settings import SFX_POOLS

router = APIRouter(prefix="/settings/sfx", tags=["settings", "sfx"])


class IngestBody(BaseModel):
    url: str
    pool: str


class UpdateBody(BaseModel):
    enabled: bool | None = None
    pool: str | None = None
    display_name: str | None = None


@router.get("/")
async def list_sfx():
    return {"pools": list(SFX_POOLS), "sounds": await sfx.list_sounds()}


@router.post("/upload")
async def upload_sfx(pool: str = Form(...), file: UploadFile = File(...)):
    if pool not in SFX_POOLS:
        raise HTTPException(400, f"Unknown pool: {pool}")
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty upload.")
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "MP3 too large (5MB max).")
    try:
        return await sfx.save_uploaded_mp3(file.filename or "upload.mp3", content, pool)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/from-url")
async def ingest_url(body: IngestBody):
    try:
        return await sfx.ingest_myinstants(body.url, body.pool)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(502, str(e))


@router.delete("/{sound_id}")
async def delete_sfx(sound_id: int):
    ok = await sfx.delete_sound(sound_id)
    if not ok:
        raise HTTPException(404, "Sound not found.")
    return {"deleted": True}


@router.patch("/{sound_id}")
async def update_sfx(sound_id: int, body: UpdateBody):
    try:
        ok = await sfx.update_sound(
            sound_id,
            enabled=body.enabled,
            pool=body.pool,
            display_name=body.display_name,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not ok:
        raise HTTPException(404, "Sound not found or no fields to update.")
    return {"updated": True}
