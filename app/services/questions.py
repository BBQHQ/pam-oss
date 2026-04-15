"""PAM Questions — when PAM needs clarification before acting."""

import aiosqlite
from datetime import datetime
from app.config import DATA_DIR

DB_PATH = DATA_DIR / "questions.db"


async def _get_db():
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            context TEXT NOT NULL DEFAULT '',
            source_task TEXT DEFAULT NULL,
            answer TEXT DEFAULT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created TEXT NOT NULL,
            answered TEXT DEFAULT NULL
        )
    """)
    await db.commit()
    return db


async def ask(question: str, context: str = "", source_task: str = None) -> dict:
    """PAM asks a question. Returns the question record."""
    now = datetime.now().isoformat()
    db = await _get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO questions (question, context, source_task, status, created) VALUES (?, ?, ?, 'open', ?)",
            (question, context, source_task, now),
        )
        await db.commit()
        return {
            "id": cursor.lastrowid, "question": question, "context": context,
            "source_task": source_task, "answer": None, "status": "open", "created": now,
        }
    finally:
        await db.close()


async def get_open_questions() -> list[dict]:
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM questions WHERE status = 'open' ORDER BY created DESC"
        )
        return [dict(r) for r in await cursor.fetchall()]
    finally:
        await db.close()


async def get_all_questions(include_answered: bool = False) -> list[dict]:
    db = await _get_db()
    try:
        if include_answered:
            cursor = await db.execute("SELECT * FROM questions ORDER BY created DESC")
        else:
            cursor = await db.execute("SELECT * FROM questions WHERE status = 'open' ORDER BY created DESC")
        return [dict(r) for r in await cursor.fetchall()]
    finally:
        await db.close()


async def answer_question(question_id: int, answer: str) -> dict | None:
    """User answers a PAM question."""
    now = datetime.now().isoformat()
    db = await _get_db()
    try:
        cursor = await db.execute("SELECT * FROM questions WHERE id = ?", (question_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        await db.execute(
            "UPDATE questions SET answer = ?, status = 'answered', answered = ? WHERE id = ?",
            (answer, now, question_id),
        )
        await db.commit()
        result = dict(row)
        result["answer"] = answer
        result["status"] = "answered"
        result["answered"] = now
    finally:
        await db.close()

    # Mirror to accomplishments log (outside the db context to avoid nesting)
    from app.services import accomplishments
    await accomplishments.safe_log(
        "question",
        result["question"],
        source_id=str(question_id),
        metadata={"answer": answer},
    )
    return result


async def get_questions_for_source(source_task: str, status: str | None = None) -> list[dict]:
    """Get all questions linked to a source_task, optionally filtered by status."""
    db = await _get_db()
    try:
        if status:
            cursor = await db.execute(
                "SELECT * FROM questions WHERE source_task = ? AND status = ? ORDER BY created",
                (source_task, status),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM questions WHERE source_task = ? ORDER BY created",
                (source_task,),
            )
        return [dict(r) for r in await cursor.fetchall()]
    finally:
        await db.close()


async def mark_incorporated(source_task: str) -> int:
    """Mark all answered questions for a source_task as incorporated."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "UPDATE questions SET status = 'incorporated' WHERE source_task = ? AND status = 'answered'",
            (source_task,),
        )
        await db.commit()
        return cursor.rowcount
    finally:
        await db.close()


async def dismiss_question(question_id: int) -> bool:
    """Dismiss a question without answering."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "UPDATE questions SET status = 'dismissed' WHERE id = ?", (question_id,)
        )
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()
