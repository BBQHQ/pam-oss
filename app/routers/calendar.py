"""Calendar endpoints."""

from fastapi import APIRouter, UploadFile, File
from pydantic import BaseModel
from app.services.calendar import (
    create_event, create_hold, cancel_event, get_upcoming,
    parse_event_text, parse_event_image, is_google_configured,
)
from app.services.contacts import add_contact, get_contacts, delete_contact

router = APIRouter(prefix="/calendar", tags=["calendar"])


class EventCreate(BaseModel):
    summary: str
    start_time: str
    end_time: str
    description: str = ""
    attendees: str = ""
    location: str = ""


class HoldCreate(BaseModel):
    summary: str
    start_time: str
    end_time: str
    description: str = ""


class EventParseRequest(BaseModel):
    text: str


@router.post("/parse")
async def parse_text(body: EventParseRequest):
    """Parse natural language text into event details (preview, no creation)."""
    return await parse_event_text(body.text)


@router.post("/parse-image")
async def parse_image(file: UploadFile = File(...)):
    """Parse an uploaded image into event details (preview, no creation)."""
    image_bytes = await file.read()
    return await parse_event_image(image_bytes, filename=file.filename or "image.png")


@router.post("/events")
async def new_event(body: EventCreate):
    return await create_event(
        summary=body.summary, start_time=body.start_time, end_time=body.end_time,
        description=body.description, attendees=body.attendees, location=body.location,
    )


@router.post("/hold")
async def new_hold(body: HoldCreate):
    return await create_hold(
        summary=body.summary, start_time=body.start_time, end_time=body.end_time,
        description=body.description,
    )


@router.get("/upcoming")
async def upcoming(limit: int = 10):
    return await get_upcoming(max_results=limit)


@router.delete("/events/{event_id}")
async def remove_event(event_id: int):
    result = await cancel_event(event_id)
    if not result:
        return {"error": "Event not found or already cancelled"}
    return result


@router.get("/status")
async def status():
    return {"google_configured": is_google_configured()}


# ─── Contacts ───────────────────────────────

class ContactCreate(BaseModel):
    name: str
    email: str


@router.get("/contacts")
async def list_contacts():
    return await get_contacts()


@router.post("/contacts")
async def new_contact(body: ContactCreate):
    return await add_contact(body.name, body.email)


@router.delete("/contacts/{contact_id}")
async def remove_contact(contact_id: int):
    return {"deleted": await delete_contact(contact_id)}
