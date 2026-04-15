"""PAM Contacts — quick-access email contacts for calendar invites."""

import aiosqlite
from datetime import datetime
from app.config import DATA_DIR

DB_PATH = DATA_DIR / "notes.db"


async def _get_db():
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            created TEXT NOT NULL
        )
    """)
    await db.commit()
    return db


async def add_contact(name: str, email: str) -> dict:
    now = datetime.now().isoformat()
    db = await _get_db()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO contacts (name, email, created) VALUES (?, ?, ?)",
            (name.strip(), email.strip().lower(), now),
        )
        await db.commit()
        return {"name": name.strip(), "email": email.strip().lower(), "created": now}
    finally:
        await db.close()


async def get_contacts() -> list[dict]:
    db = await _get_db()
    try:
        cursor = await db.execute("SELECT * FROM contacts ORDER BY name")
        return [dict(r) for r in await cursor.fetchall()]
    finally:
        await db.close()


async def delete_contact(contact_id: int) -> bool:
    db = await _get_db()
    try:
        cursor = await db.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()
