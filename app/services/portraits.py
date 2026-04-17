"""Custom portrait registry — per-period user-uploaded images.

User uploads land under `data/custom/portraits/<period>/` and are served via
the `/custom/` static mount. The `portraits` SQLite table tracks which files
are active; deleting a row also deletes the file from disk.

The built-in portraits under `/img/<period>/` are independent from this
registry — the root `/portraits` endpoint merges both sources.
"""

import asyncio
import re
from datetime import datetime
from pathlib import Path

import aiosqlite

from app.config import DATA_DIR

DB_PATH = DATA_DIR / "notes.db"
CUSTOM_ROOT = DATA_DIR / "custom" / "portraits"
STATIC_PREFIX = "/custom/portraits/"

PERIODS = ("morning", "workday", "evening")
ALLOWED_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
MAX_BYTES = 5 * 1024 * 1024  # 5MB per upload


def _pretty_name(filename: str) -> str:
    stem = Path(filename).stem
    return stem.replace("-", " ").replace("_", " ").strip().title()


async def _get_db():
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS portraits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL UNIQUE,
            period TEXT NOT NULL,
            display_name TEXT NOT NULL,
            created TEXT NOT NULL
        )
        """
    )
    await db.commit()
    return db


async def list_portraits() -> list[dict]:
    db = await _get_db()
    try:
        cur = await db.execute(
            "SELECT id, filename, period, display_name, created "
            "FROM portraits ORDER BY period, display_name"
        )
        rows = await cur.fetchall()
    finally:
        await db.close()
    return [
        {
            "id": r["id"],
            "filename": r["filename"],
            "period": r["period"],
            "display_name": r["display_name"],
            "url": STATIC_PREFIX + r["filename"],
            "created": r["created"],
        }
        for r in rows
    ]


async def list_urls_by_period() -> dict[str, list[str]]:
    """Return {period: [url, ...]} for merging into /portraits."""
    db = await _get_db()
    try:
        cur = await db.execute("SELECT filename, period FROM portraits ORDER BY period, filename")
        rows = await cur.fetchall()
    finally:
        await db.close()
    out: dict[str, list[str]] = {p: [] for p in PERIODS}
    for r in rows:
        if r["period"] in out:
            out[r["period"]].append(STATIC_PREFIX + r["filename"])
    return out


async def save_uploaded(filename: str, content: bytes, period: str) -> dict:
    if period not in PERIODS:
        raise ValueError(f"Unknown period: {period}")
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise ValueError(f"Unsupported image type: {ext or '(none)'}")
    if not content:
        raise ValueError("Empty upload.")
    if len(content) > MAX_BYTES:
        raise ValueError(f"Image too large (max {MAX_BYTES // (1024*1024)}MB).")

    target_dir = CUSTOM_ROOT / period
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_.\-]", "_", filename)
    target = target_dir / safe_name
    counter = 1
    while target.exists():
        target = target_dir / f"{target.stem}-{counter}{target.suffix}"
        counter += 1
    await asyncio.to_thread(target.write_bytes, content)

    rel = f"{period}/{target.name}"
    now = datetime.now().isoformat()
    display = _pretty_name(target.name)
    db = await _get_db()
    try:
        await db.execute(
            "INSERT INTO portraits (filename, period, display_name, created) "
            "VALUES (?, ?, ?, ?)",
            (rel, period, display, now),
        )
        await db.commit()
        cur = await db.execute("SELECT id FROM portraits WHERE filename = ?", (rel,))
        row = await cur.fetchone()
    finally:
        await db.close()

    return {
        "id": row["id"],
        "filename": rel,
        "period": period,
        "display_name": display,
        "url": STATIC_PREFIX + rel,
        "created": now,
    }


async def delete_portrait(portrait_id: int) -> bool:
    db = await _get_db()
    try:
        cur = await db.execute(
            "SELECT filename FROM portraits WHERE id = ?", (portrait_id,)
        )
        row = await cur.fetchone()
        if not row:
            return False
        await db.execute("DELETE FROM portraits WHERE id = ?", (portrait_id,))
        await db.commit()
    finally:
        await db.close()

    path = CUSTOM_ROOT / row["filename"]
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass
    return True
