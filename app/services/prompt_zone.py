"""Prompt Zone — SQLite storage for saved prompts with golden (starred) support."""

import aiosqlite
from datetime import datetime
from app.config import DATA_DIR

DB_PATH = DATA_DIR / "notes.db"


async def _get_db():
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("""
        CREATE TABLE IF NOT EXISTS prompts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            title      TEXT    NOT NULL,
            prompt     TEXT    NOT NULL,
            golden     INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created    TEXT    NOT NULL,
            updated    TEXT    NOT NULL
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_prompts_golden ON prompts(golden, sort_order)"
    )
    await db.commit()
    return db


async def create_prompt(title: str, prompt: str, golden: bool = False) -> dict:
    db = await _get_db()
    try:
        now = datetime.now().isoformat()
        cur = await db.execute(
            "INSERT INTO prompts (title, prompt, golden, created, updated) VALUES (?, ?, ?, ?, ?)",
            (title.strip(), prompt.strip(), int(golden), now, now),
        )
        await db.commit()
        return {"id": cur.lastrowid, "title": title.strip(), "prompt": prompt.strip(),
                "golden": golden, "sort_order": 0, "created": now, "updated": now}
    finally:
        await db.close()


async def list_prompts(golden_only: bool = False) -> list[dict]:
    db = await _get_db()
    try:
        if golden_only:
            cur = await db.execute(
                "SELECT * FROM prompts WHERE golden = 1 ORDER BY sort_order, created DESC"
            )
        else:
            cur = await db.execute(
                "SELECT * FROM prompts ORDER BY golden DESC, sort_order, created DESC"
            )
        rows = await cur.fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        await db.close()


async def get_prompt(prompt_id: int) -> dict | None:
    db = await _get_db()
    try:
        cur = await db.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,))
        row = await cur.fetchone()
        return _row_to_dict(row) if row else None
    finally:
        await db.close()


async def update_prompt(prompt_id: int, title: str | None = None,
                        prompt: str | None = None, golden: bool | None = None) -> dict | None:
    db = await _get_db()
    try:
        fields, values = [], []
        if title is not None:
            fields.append("title = ?")
            values.append(title.strip())
        if prompt is not None:
            fields.append("prompt = ?")
            values.append(prompt.strip())
        if golden is not None:
            fields.append("golden = ?")
            values.append(int(golden))
        if not fields:
            return await get_prompt(prompt_id)
        fields.append("updated = ?")
        values.append(datetime.now().isoformat())
        values.append(prompt_id)
        await db.execute(f"UPDATE prompts SET {', '.join(fields)} WHERE id = ?", values)
        await db.commit()
        cur = await db.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,))
        row = await cur.fetchone()
        return _row_to_dict(row) if row else None
    finally:
        await db.close()


async def delete_prompt(prompt_id: int) -> bool:
    db = await _get_db()
    try:
        cur = await db.execute("DELETE FROM prompts WHERE id = ?", (prompt_id,))
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()


def _row_to_dict(row) -> dict:
    d = dict(row)
    d["golden"] = bool(d.get("golden", 0))
    return d
