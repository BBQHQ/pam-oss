"""Accomplishments log — append-only event stream of completed things.

Captures completed to-dos, answered questions, completed tasks, and
manual user entries. Stored in notes.db (single-file consolidation
direction per audit).
"""

import json
import aiosqlite
from datetime import datetime, timedelta
from app.config import DATA_DIR

DB_PATH = DATA_DIR / "notes.db"

VALID_SOURCES = {"todo", "question", "task", "manual"}


async def _get_db():
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("""
        CREATE TABLE IF NOT EXISTS accomplishments (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            source       TEXT    NOT NULL CHECK(source IN ('todo','question','task','manual')),
            source_id    TEXT,
            text         TEXT    NOT NULL,
            metadata     TEXT,
            completed_at TEXT    NOT NULL
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_accomp_completed ON accomplishments(completed_at DESC)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_accomp_source ON accomplishments(source, source_id)"
    )
    await db.commit()
    return db


def _row_to_dict(row) -> dict:
    d = dict(row)
    if d.get("metadata"):
        try:
            d["metadata"] = json.loads(d["metadata"])
        except Exception:
            pass
    return d


async def log(
    source: str,
    text: str,
    source_id: str | None = None,
    metadata: dict | None = None,
    completed_at: str | None = None,
) -> dict:
    """Insert one accomplishment. Dedupes (source, source_id) for non-manual."""
    if source not in VALID_SOURCES:
        raise ValueError(f"invalid source: {source}")
    if not text or not text.strip():
        raise ValueError("text is required")
    completed_at = completed_at or datetime.now().isoformat()
    meta_json = json.dumps(metadata) if metadata else None

    db = await _get_db()
    try:
        # Dedupe non-manual sources
        if source != "manual" and source_id is not None:
            cur = await db.execute(
                "SELECT * FROM accomplishments WHERE source = ? AND source_id = ?",
                (source, source_id),
            )
            existing = await cur.fetchone()
            if existing:
                return _row_to_dict(existing)

        cur = await db.execute(
            "INSERT INTO accomplishments (source, source_id, text, metadata, completed_at) VALUES (?, ?, ?, ?, ?)",
            (source, source_id, text.strip(), meta_json, completed_at),
        )
        await db.commit()
        cur2 = await db.execute(
            "SELECT * FROM accomplishments WHERE id = ?", (cur.lastrowid,)
        )
        row = await cur2.fetchone()
        return _row_to_dict(row)
    finally:
        await db.close()


async def safe_log(source: str, text: str, **kw) -> dict | None:
    """log() that swallows exceptions — for use in integration hooks."""
    try:
        return await log(source, text, **kw)
    except Exception as e:
        print(f"[PAM] accomplishments.safe_log failed: {e}")
        return None


async def list_accomplishments(
    limit: int = 100,
    since: str | None = None,
    source_filter: str | None = None,
) -> list[dict]:
    """Newest-first. since=ISO date string; source_filter=one of VALID_SOURCES."""
    db = await _get_db()
    try:
        clauses = []
        params: list = []
        if since:
            clauses.append("completed_at >= ?")
            params.append(since)
        if source_filter and source_filter in VALID_SOURCES:
            clauses.append("source = ?")
            params.append(source_filter)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        cur = await db.execute(
            f"SELECT * FROM accomplishments {where} ORDER BY completed_at DESC LIMIT ?",
            params,
        )
        rows = await cur.fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        await db.close()


async def delete(accomplishment_id: int) -> bool:
    db = await _get_db()
    try:
        cur = await db.execute(
            "DELETE FROM accomplishments WHERE id = ?", (accomplishment_id,)
        )
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()


async def unlog(source: str, source_id: str) -> bool:
    """Reverse-lookup delete. Used when a todo is un-toggled."""
    db = await _get_db()
    try:
        cur = await db.execute(
            "DELETE FROM accomplishments WHERE source = ? AND source_id = ?",
            (source, source_id),
        )
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()


async def backfill() -> dict:
    """Walk existing done todos, answered questions, and completed tasks and
    log them. Idempotent thanks to (source, source_id) dedupe — safe to re-run.
    """
    counts = {"todo": 0, "question": 0, "task": 0, "skipped": 0}

    # Done todos — use `created` since Todo has no completion timestamp
    try:
        from app.services.todos import get_todos
        for t in await get_todos(show_done=True):
            if not t.done:
                continue
            existing = await log("todo", t.text, source_id=t.id, completed_at=t.created)
            counts["todo"] += 1
    except Exception as e:
        print(f"[PAM] backfill todos failed: {e}")

    # Answered + incorporated questions — use `answered` timestamp
    try:
        import aiosqlite
        from app.config import DATA_DIR
        qdb = await aiosqlite.connect(str(DATA_DIR / "questions.db"))
        qdb.row_factory = aiosqlite.Row
        cur = await qdb.execute(
            "SELECT id, question, answer, answered FROM questions "
            "WHERE status IN ('answered','incorporated') AND answered IS NOT NULL"
        )
        rows = await cur.fetchall()
        await qdb.close()
        for r in rows:
            await log(
                "question",
                r["question"],
                source_id=str(r["id"]),
                metadata={"answer": r["answer"]} if r["answer"] else None,
                completed_at=r["answered"],
            )
            counts["question"] += 1
    except Exception as e:
        print(f"[PAM] backfill questions failed: {e}")

    # Done tasks — use `completed` timestamp, fall back to `created`
    try:
        from app.services.task_engine import get_tasks
        for t in get_tasks(status="done"):
            ts = t.completed or t.created
            await log(
                "task",
                t.title,
                source_id=t.id,
                metadata={"project": t.project} if t.project else None,
                completed_at=ts,
            )
            counts["task"] += 1
    except Exception as e:
        print(f"[PAM] backfill tasks failed: {e}")

    return counts


async def count_recent(days: int = 7) -> int:
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    db = await _get_db()
    try:
        cur = await db.execute(
            "SELECT COUNT(*) AS c FROM accomplishments WHERE completed_at >= ?",
            (cutoff,),
        )
        row = await cur.fetchone()
        return int(row["c"]) if row else 0
    finally:
        await db.close()
