"""PAM Calendar — Google Calendar API + Claude parsing + SQLite ledger."""

import asyncio
import json
import subprocess
import sys
import uuid
import tempfile
import base64
import aiosqlite

_CREATION_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
from datetime import datetime, timedelta
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from app.config import (
    DATA_DIR, GOOGLE_CREDENTIALS_FILE, GOOGLE_TOKEN_FILE,
    CALENDAR_TIMEZONE, USER_EMAIL, CLAUDE_BIN,
)

DB_PATH = DATA_DIR / "notes.db"
SCOPES = ["https://www.googleapis.com/auth/calendar"]


# ─── SQLite Ledger ──────────────────────────────────

async def _get_db():
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("""
        CREATE TABLE IF NOT EXISTS calendar_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            google_event_id TEXT DEFAULT NULL,
            summary TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            location TEXT NOT NULL DEFAULT '',
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            attendees TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            created TEXT NOT NULL,
            updated TEXT NOT NULL
        )
    """)
    await db.commit()
    return db


async def _ledger_record(google_event_id, summary, start_time, end_time, description="", location="", attendees=""):
    """Record an event in the local SQLite ledger."""
    now = datetime.now().isoformat()
    db = await _get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO calendar_events (google_event_id, summary, description, location, start_time, end_time, attendees, status, created, updated) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)",
            (google_event_id, summary, description, location, start_time, end_time, attendees, now, now),
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def _ledger_cancel(ledger_id):
    now = datetime.now().isoformat()
    db = await _get_db()
    try:
        await db.execute("UPDATE calendar_events SET status='cancelled', updated=? WHERE id=?", (now, ledger_id))
        await db.commit()
    finally:
        await db.close()


# ─── Google Calendar API ────────────────────────────

def _get_google_service():
    """Load Google Calendar API service. Returns None if not configured."""
    if not GOOGLE_TOKEN_FILE.exists():
        return None

    try:
        creds = Credentials.from_authorized_user_file(str(GOOGLE_TOKEN_FILE), SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            GOOGLE_TOKEN_FILE.write_text(creds.to_json())
        if not creds or not creds.valid:
            return None
        return build("calendar", "v3", credentials=creds)
    except Exception as e:
        print(f"[PAM] Google Calendar auth failed: {e}")
        return None


def is_google_configured() -> bool:
    return _get_google_service() is not None


def _to_gcal_datetime(iso_str: str, tz: str | None = None) -> dict:
    """Convert ISO datetime string to Google Calendar dateTime format."""
    return {"dateTime": iso_str, "timeZone": tz or CALENDAR_TIMEZONE}


# ─── Event CRUD ─────────────────────────────────────

async def create_event(
    summary: str,
    start_time: str,
    end_time: str,
    description: str = "",
    attendees: str = "",
    location: str = "",
) -> dict:
    """Create event on Google Calendar and record in local ledger."""
    from app.services.settings import get_setting
    service = _get_google_service()
    google_event_id = None
    event_link = None
    tz = await get_setting("timezone", CALENDAR_TIMEZONE)

    if service:
        body = {
            "summary": summary,
            "start": _to_gcal_datetime(start_time, tz),
            "end": _to_gcal_datetime(end_time, tz),
        }
        if description:
            body["description"] = description
        if location:
            body["location"] = location
        if attendees:
            body["attendees"] = [
                {"email": e.strip()} for e in attendees.split(",") if e.strip()
            ]

        try:
            result = await asyncio.to_thread(
                service.events().insert(
                    calendarId="primary", body=body, sendUpdates="all"
                ).execute
            )
            google_event_id = result.get("id")
            event_link = result.get("htmlLink")
        except Exception as e:
            print(f"[PAM] Google Calendar create failed: {e}")

    ledger_id = await _ledger_record(
        google_event_id, summary, start_time, end_time, description, location, attendees
    )

    return {
        "id": ledger_id,
        "google_event_id": google_event_id,
        "event_link": event_link,
        "summary": summary,
        "start_time": start_time,
        "end_time": end_time,
        "attendees": attendees,
        "location": location,
        "description": description,
        "created": datetime.now().isoformat(),
    }


async def create_hold(
    summary: str,
    start_time: str,
    end_time: str,
    description: str = "",
) -> dict:
    """Create calendar hold — invites the user's personal email."""
    return await create_event(
        summary=summary,
        start_time=start_time,
        end_time=end_time,
        description=description,
        attendees=USER_EMAIL,
    )


async def cancel_event(ledger_id: int) -> dict | None:
    """Cancel event from Google Calendar and update local ledger."""
    db = await _get_db()
    try:
        cursor = await db.execute("SELECT * FROM calendar_events WHERE id = ? AND status = 'active'", (ledger_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        data = dict(row)
    finally:
        await db.close()

    # Delete from Google Calendar
    if data.get("google_event_id"):
        service = _get_google_service()
        if service:
            try:
                await asyncio.to_thread(
                    service.events().delete(
                        calendarId="primary",
                        eventId=data["google_event_id"],
                        sendUpdates="all",
                    ).execute
                )
            except Exception as e:
                print(f"[PAM] Google Calendar delete failed: {e}")

    await _ledger_cancel(ledger_id)
    return {"id": ledger_id, "summary": data["summary"], "status": "cancelled"}


async def get_upcoming(max_results: int = 10) -> list[dict]:
    """Get upcoming events from Google Calendar API."""
    service = _get_google_service()
    if not service:
        # Fallback to local ledger
        return await _get_upcoming_local(max_results)

    try:
        now = datetime.now().isoformat() + "Z"
        result = await asyncio.to_thread(
            service.events().list(
                calendarId="primary",
                timeMin=now,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            ).execute
        )
        events = []
        for item in result.get("items", []):
            start = item.get("start", {})
            end = item.get("end", {})
            events.append({
                "google_event_id": item.get("id"),
                "summary": item.get("summary", ""),
                "start_time": start.get("dateTime", start.get("date", "")),
                "end_time": end.get("dateTime", end.get("date", "")),
                "location": item.get("location", ""),
                "description": item.get("description", ""),
                "attendees": ", ".join(
                    a.get("email", "") for a in item.get("attendees", [])
                ),
                "event_link": item.get("htmlLink", ""),
            })
        return events
    except Exception as e:
        print(f"[PAM] Google Calendar list failed: {e}")
        return await _get_upcoming_local(max_results)


async def _get_upcoming_local(max_results: int = 10) -> list[dict]:
    """Fallback: upcoming events from local SQLite ledger."""
    now = datetime.now().isoformat()
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM calendar_events WHERE status = 'active' AND end_time >= ? ORDER BY start_time LIMIT ?",
            (now, max_results),
        )
        return [dict(r) for r in await cursor.fetchall()]
    finally:
        await db.close()


async def get_all_events() -> list[dict]:
    """Get all events from local SQLite ledger."""
    db = await _get_db()
    try:
        cursor = await db.execute("SELECT * FROM calendar_events ORDER BY start_time DESC")
        return [dict(r) for r in await cursor.fetchall()]
    finally:
        await db.close()


# ─── Claude Parsing ─────────────────────────────────

async def parse_event_text(text: str) -> dict:
    """Parse natural language text into structured event data via Claude CLI."""
    now = datetime.now()

    prompt = (
        f"Parse the following text into a calendar event. Today is {now.strftime('%A, %B %d, %Y')} "
        f"and the current time is {now.strftime('%I:%M %p')}.\n\n"
        "Return ONLY valid JSON (no markdown, no code blocks) with these fields:\n"
        '- "title": string (event title)\n'
        '- "start_date": string (YYYY-MM-DD)\n'
        '- "start_time": string (HH:MM in 24-hour format)\n'
        '- "duration_minutes": integer (default 60 if not specified)\n'
        '- "location": string or null\n'
        '- "description": string or null\n'
        '- "attendees": string (comma-separated emails) or null\n\n'
        "Handle relative dates like 'tomorrow', 'next Tuesday', 'in 2 hours'.\n"
        "If only a date is given with no time, use 09:00.\n\n"
        f"Text to parse:\n{text}"
    )

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            [CLAUDE_BIN, "--print", "-p", prompt],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8",
            creationflags=_CREATION_FLAGS,
        )
        if result.returncode == 0 and result.stdout.strip():
            output = result.stdout.strip()
            # Strip markdown code blocks if present
            if output.startswith("```"):
                output = "\n".join(output.split("\n")[1:-1])
            parsed = json.loads(output)

            # Convert to start/end times
            start_dt = datetime.strptime(
                f"{parsed['start_date']} {parsed['start_time']}", "%Y-%m-%d %H:%M"
            )
            duration = parsed.get("duration_minutes", 60)
            end_dt = start_dt + timedelta(minutes=duration)

            return {
                "success": True,
                "summary": parsed.get("title", "Untitled Event"),
                "start_time": start_dt.isoformat(),
                "end_time": end_dt.isoformat(),
                "location": parsed.get("location") or "",
                "description": parsed.get("description") or "",
                "attendees": parsed.get("attendees") or "",
                "duration_minutes": duration,
            }
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Failed to parse Claude response as JSON: {e}"}
    except Exception as e:
        return {"success": False, "error": f"Parsing failed: {e}"}

    return {"success": False, "error": "Claude returned empty response"}


async def parse_event_image(image_bytes: bytes, filename: str = "image.png") -> dict:
    """Parse an image of an appointment card into structured event data via Claude CLI."""
    now = datetime.now()

    # Save image to temp file
    suffix = Path(filename).suffix or ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(image_bytes)
        tmp_path = tmp.name

    prompt = (
        f"Look at this image of an appointment card, flyer, or screenshot. "
        f"Today is {now.strftime('%A, %B %d, %Y')}.\n\n"
        "Extract the calendar event details and return ONLY valid JSON (no markdown, no code blocks) with:\n"
        '- "title": string\n'
        '- "start_date": string (YYYY-MM-DD)\n'
        '- "start_time": string (HH:MM in 24-hour format)\n'
        '- "duration_minutes": integer (default 60)\n'
        '- "location": string or null\n'
        '- "description": string or null\n\n'
        "If you cannot determine a field, use reasonable defaults. "
        "If the year is not specified, assume the current or next occurrence."
    )

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            [CLAUDE_BIN, "--print", "-p", prompt, "--image", tmp_path],
            capture_output=True, text=True, timeout=60,
            encoding="utf-8",
            creationflags=_CREATION_FLAGS,
        )
        # Clean up temp file
        Path(tmp_path).unlink(missing_ok=True)

        if result.returncode == 0 and result.stdout.strip():
            output = result.stdout.strip()
            if output.startswith("```"):
                output = "\n".join(output.split("\n")[1:-1])
            parsed = json.loads(output)

            start_dt = datetime.strptime(
                f"{parsed['start_date']} {parsed['start_time']}", "%Y-%m-%d %H:%M"
            )
            duration = parsed.get("duration_minutes", 60)
            end_dt = start_dt + timedelta(minutes=duration)

            return {
                "success": True,
                "summary": parsed.get("title", "Untitled Event"),
                "start_time": start_dt.isoformat(),
                "end_time": end_dt.isoformat(),
                "location": parsed.get("location") or "",
                "description": parsed.get("description") or "",
                "attendees": "",
                "duration_minutes": duration,
            }
    except json.JSONDecodeError as e:
        Path(tmp_path).unlink(missing_ok=True)
        return {"success": False, "error": f"Failed to parse Claude response: {e}"}
    except Exception as e:
        Path(tmp_path).unlink(missing_ok=True)
        return {"success": False, "error": f"Image parsing failed: {e}"}

    return {"success": False, "error": "Claude returned empty response"}
