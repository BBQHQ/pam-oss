"""Notes endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel
from app.services.notes import (
    create_note, get_notes, get_note, update_note, pin_note, delete_note,
    enhance_note, get_enhancement, delete_enhancement,
)

router = APIRouter(prefix="/notes", tags=["notes"])


class NoteCreate(BaseModel):
    title: str
    content: str = ""


class NoteUpdate(BaseModel):
    title: str | None = None
    content: str | None = None


@router.post("/")
async def create(body: NoteCreate):
    return await create_note(body.title, body.content)


@router.get("/")
async def list_notes():
    return await get_notes()


@router.get("/{note_id}")
async def read_note(note_id: int):
    note = await get_note(note_id)
    if not note:
        return {"error": "Not found"}
    return note


@router.put("/{note_id}")
async def edit_note(note_id: int, body: NoteUpdate):
    note = await update_note(note_id, title=body.title, content=body.content)
    if not note:
        return {"error": "Not found"}
    return note


@router.post("/{note_id}/pin")
async def pin(note_id: int):
    note = await pin_note(note_id, True)
    if not note:
        return {"error": "Not found"}
    return note


@router.post("/{note_id}/unpin")
async def unpin(note_id: int):
    note = await pin_note(note_id, False)
    if not note:
        return {"error": "Not found"}
    return note


@router.post("/{note_id}/enhance")
async def enhance(note_id: int):
    """Generate an AI-enhanced version of a pinned note."""
    return await enhance_note(note_id)


@router.get("/{note_id}/enhancement")
async def read_enhancement(note_id: int):
    """Get the stored enhancement for a note."""
    enh = await get_enhancement(note_id)
    if not enh:
        return {"error": "No enhancement found"}
    return enh


@router.delete("/{note_id}/enhancement")
async def remove_enhancement(note_id: int):
    return {"deleted": await delete_enhancement(note_id)}


@router.delete("/{note_id}")
async def remove_note(note_id: int):
    return {"deleted": await delete_note(note_id)}
