"""Briefing endpoints."""

from fastapi import APIRouter
from app.services.briefing import generate_briefing, get_cached_briefing, send_briefing_email, send_checkin_email
from app.services.email import is_configured

router = APIRouter(prefix="/briefing", tags=["briefing"])


@router.get("/")
async def get_briefing():
    """Get today's briefing (cached if available, otherwise generate fresh)."""
    cached = get_cached_briefing()
    if cached:
        return cached
    return await generate_briefing()


@router.post("/generate")
async def force_generate():
    """Force regenerate today's briefing."""
    return await generate_briefing()


@router.post("/send")
async def send():
    """Manually trigger a briefing email."""
    sent = await send_briefing_email()
    return {"sent": sent, "email_configured": is_configured()}


@router.post("/checkin")
async def checkin():
    """Manually trigger a mid-day check-in email."""
    sent = await send_checkin_email()
    return {"sent": sent, "email_configured": is_configured()}


@router.get("/status")
async def status():
    """Check briefing and email status."""
    cached = get_cached_briefing()
    return {
        "email_configured": is_configured(),
        "has_todays_briefing": cached is not None,
        "generated_at": cached["generated_at"] if cached else None,
    }
