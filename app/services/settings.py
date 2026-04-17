"""PAM Settings — user-tunable preferences stored as key/value pairs."""

import aiosqlite
from datetime import datetime
from typing import Any
from app.config import DATA_DIR

DB_PATH = DATA_DIR / "notes.db"

SFX_POOLS = ("create", "complete", "delete", "utility", "epic")

# Defaults: key -> (default_value, category). Defines the v1 settings surface.
DEFAULTS: dict[str, tuple[Any, str]] = {
    "briefing_hour": (7, "schedule"),
    "checkin_hour": (13, "schedule"),
    "habit_reset_hour": (4, "schedule"),
    "timezone": ("America/New_York", "notifications"),
    "briefing_email_recipient": ("", "notifications"),
    "assistant_name": ("PAM", "ui"),
    "sfx_enabled": (True, "ui"),
    "sfx_volume": (0.6, "ui"),
    **{f"sfx_pool_{p}_enabled": (True, "ui") for p in SFX_POOLS},
    **{f"sfx_pool_{p}_volume": (1.0, "ui") for p in SFX_POOLS},
}


async def _get_db():
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("""
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL UNIQUE,
            value TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'general',
            created TEXT NOT NULL,
            updated TEXT NOT NULL
        )
    """)
    await db.commit()
    return db


def _coerce(raw: str, default: Any) -> Any:
    """Cast a stored string back to the type of its default."""
    if isinstance(default, bool):
        return raw.lower() in ("1", "true", "yes", "on")
    if isinstance(default, int):
        try:
            return int(raw)
        except (ValueError, TypeError):
            return default
    if isinstance(default, float):
        try:
            return float(raw)
        except (ValueError, TypeError):
            return default
    return raw


async def set_setting(key: str, value: Any, category: str | None = None) -> dict:
    """Store or update a setting. Upserts by key."""
    now = datetime.now().isoformat()
    if category is None:
        category = DEFAULTS.get(key, (None, "general"))[1]
    stored = str(value).strip() if not isinstance(value, bool) else ("true" if value else "false")
    db = await _get_db()
    try:
        await db.execute(
            "INSERT INTO memory (key, value, category, created, updated) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, category = excluded.category, updated = excluded.updated",
            (key.strip(), stored, category, now, now),
        )
        await db.commit()
        return {"key": key.strip(), "value": stored, "category": category, "updated": now}
    finally:
        await db.close()


async def get_setting(key: str, default: Any) -> Any:
    """Get a single setting value, type-coerced to match `default`."""
    db = await _get_db()
    try:
        cursor = await db.execute("SELECT value FROM memory WHERE key = ?", (key,))
        row = await cursor.fetchone()
        if not row:
            return default
        return _coerce(row["value"], default)
    finally:
        await db.close()


async def get_settings() -> dict:
    """Return all settings as a dict mapping key -> {value, category, updated}.

    Missing settings fall back to defaults so the UI always has a complete picture.
    """
    db = await _get_db()
    try:
        cursor = await db.execute("SELECT key, value, category, updated FROM memory")
        rows = {r["key"]: dict(r) for r in await cursor.fetchall()}
    finally:
        await db.close()

    out = {}
    for key, (default, category) in DEFAULTS.items():
        if key in rows:
            r = rows[key]
            out[key] = {
                "value": _coerce(r["value"], default),
                "category": r["category"],
                "updated": r["updated"],
                "overridden": True,
            }
        else:
            out[key] = {
                "value": default,
                "category": category,
                "updated": None,
                "overridden": False,
            }
    return out


async def delete_setting(key: str) -> bool:
    """Delete a setting (revert to default)."""
    db = await _get_db()
    try:
        cursor = await db.execute("DELETE FROM memory WHERE key = ?", (key,))
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()
