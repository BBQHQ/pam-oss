"""Notes service — SQLite-backed notes with pinning and AI enhancement."""

import asyncio
import hashlib
import subprocess
import sys
import aiosqlite
from datetime import datetime
from app.config import DATA_DIR, CLAUDE_BIN

_CREATION_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

DB_PATH = DATA_DIR / "notes.db"


async def _get_db():
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    await db.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            pinned INTEGER NOT NULL DEFAULT 0,
            created TEXT NOT NULL,
            updated TEXT NOT NULL
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS note_enhancements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            note_id INTEGER NOT NULL UNIQUE,
            enhanced_content TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE
        )
    """)
    # Migration: add pinned column if missing
    try:
        await db.execute("SELECT pinned FROM notes LIMIT 1")
    except Exception:
        await db.execute("ALTER TABLE notes ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")
    await db.commit()
    return db


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


async def create_note(title: str, content: str = "", pinned: bool = False) -> dict:
    now = datetime.now().isoformat()
    db = await _get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO notes (title, content, pinned, created, updated) VALUES (?, ?, ?, ?, ?)",
            (title, content, int(pinned), now, now),
        )
        await db.commit()
        return {"id": cursor.lastrowid, "title": title, "content": content, "pinned": pinned,
                "has_enhancement": False, "enhancement_stale": False, "created": now, "updated": now}
    finally:
        await db.close()


async def get_notes(pinned: bool | None = None) -> list[dict]:
    db = await _get_db()
    try:
        query = """
            SELECT n.id, n.title, n.content, n.pinned, n.created, n.updated,
                   e.source_hash, e.generated_at
            FROM notes n
            LEFT JOIN note_enhancements e ON e.note_id = n.id
        """
        if pinned is not None:
            query += " WHERE n.pinned = ?"
            cursor = await db.execute(query + " ORDER BY n.updated DESC", (int(pinned),))
        else:
            cursor = await db.execute(query + " ORDER BY n.updated DESC")
        rows = await cursor.fetchall()
        results = []
        for r in rows:
            has_enh = r["source_hash"] is not None
            stale = False
            if has_enh:
                stale = _content_hash(r["content"]) != r["source_hash"]
            results.append({
                "id": r["id"], "title": r["title"], "content": r["content"],
                "pinned": bool(r["pinned"]), "created": r["created"], "updated": r["updated"],
                "has_enhancement": has_enh, "enhancement_stale": stale,
            })
        return results
    finally:
        await db.close()


async def get_note(note_id: int) -> dict | None:
    db = await _get_db()
    try:
        cursor = await db.execute("""
            SELECT n.id, n.title, n.content, n.pinned, n.created, n.updated,
                   e.source_hash, e.generated_at
            FROM notes n
            LEFT JOIN note_enhancements e ON e.note_id = n.id
            WHERE n.id = ?
        """, (note_id,))
        r = await cursor.fetchone()
        if not r:
            return None
        has_enh = r["source_hash"] is not None
        stale = has_enh and _content_hash(r["content"]) != r["source_hash"]
        return {
            "id": r["id"], "title": r["title"], "content": r["content"],
            "pinned": bool(r["pinned"]), "created": r["created"], "updated": r["updated"],
            "has_enhancement": has_enh, "enhancement_stale": stale,
        }
    finally:
        await db.close()


async def update_note(note_id: int, title: str | None = None, content: str | None = None) -> dict | None:
    db = await _get_db()
    try:
        existing = await get_note(note_id)
        if not existing:
            return None
        new_title = title if title is not None else existing["title"]
        new_content = content if content is not None else existing["content"]
        now = datetime.now().isoformat()
        await db.execute(
            "UPDATE notes SET title = ?, content = ?, updated = ? WHERE id = ?",
            (new_title, new_content, now, note_id),
        )
        await db.commit()
        return await get_note(note_id)
    finally:
        await db.close()


async def pin_note(note_id: int, pinned: bool) -> dict | None:
    db = await _get_db()
    try:
        now = datetime.now().isoformat()
        cursor = await db.execute(
            "UPDATE notes SET pinned = ?, updated = ? WHERE id = ?",
            (int(pinned), now, note_id),
        )
        await db.commit()
        if cursor.rowcount == 0:
            return None
        # Delete enhancement when unpinning
        if not pinned:
            await db.execute("DELETE FROM note_enhancements WHERE note_id = ?", (note_id,))
            await db.commit()
        return await get_note(note_id)
    finally:
        await db.close()


async def delete_note(note_id: int) -> bool:
    db = await _get_db()
    try:
        cursor = await db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


# ─── Enhancement ─────────────────────────────────────

async def enhance_note(note_id: int) -> dict:
    """Generate an AI-enhanced version of a pinned note."""
    from app.services.questions import ask, get_questions_for_source, mark_incorporated

    note = await get_note(note_id)
    if not note:
        return {"error": "Note not found"}
    if not note["pinned"]:
        return {"error": "Only pinned notes can be enhanced"}

    content = note["content"]
    if not content.strip():
        return {"error": "Note has no content to enhance"}

    # Gather answered questions from previous enhancements
    answered_qs = await get_questions_for_source(f"note:{note_id}", status="answered")

    prompt = (
        "You are organizing a personal note. The user dumped raw thoughts and you need to "
        "create a clean, structured version.\n\n"
        "Rules:\n"
        "- Organize into logical sections with markdown headers (##)\n"
        "- Use bullet points for lists of ideas\n"
        "- Extract any action items into a '## Action Items' section with checkboxes (- [ ])\n"
        "- Extract key decisions or conclusions into a '## Key Points' section\n"
        "- Deduplicate repeated ideas — merge them into one clear statement\n"
        "- If something is ambiguous or unclear, note it in a '## Needs Clarification' section\n"
        "- Keep the user's voice and intent — do not add new ideas\n"
        "- Use markdown formatting throughout\n\n"
        f"Note title: {note['title']}\n\n"
        f"Raw note content:\n{content[:8000]}"
    )

    if answered_qs:
        qa_lines = "\n".join(
            f"Q: {q['question']}\nA: {q['answer']}" for q in answered_qs
        )
        prompt += (
            "\n\nPreviously, you identified items needing clarification. "
            "The user has since provided answers:\n\n"
            f"{qa_lines}\n\n"
            "Incorporate these answers into the structured note. "
            "Do not re-list answered items in the 'Needs Clarification' section."
        )

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            [CLAUDE_BIN, "--print", "-p", prompt],
            capture_output=True, text=True, timeout=120,
            encoding="utf-8",
            creationflags=_CREATION_FLAGS,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return {"error": "Claude enhancement failed — empty response"}
        enhanced = result.stdout.strip()
    except subprocess.TimeoutExpired:
        return {"error": "Enhancement timed out (120s)"}
    except Exception as e:
        return {"error": f"Enhancement failed: {e}"}

    # Store enhancement
    source_hash = _content_hash(content)
    now = datetime.now().isoformat()
    db = await _get_db()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO note_enhancements (note_id, enhanced_content, source_hash, generated_at) "
            "VALUES (?, ?, ?, ?)",
            (note_id, enhanced, source_hash, now),
        )
        await db.commit()
    finally:
        await db.close()

    # Check for clarification items and create PAM questions
    in_clarification = False
    clarifications = []
    for line in enhanced.split("\n"):
        stripped = line.strip()
        if stripped.lower().startswith("## needs clarification"):
            in_clarification = True
            continue
        if in_clarification:
            if stripped.startswith("## "):
                break  # next section
            if stripped.startswith("- ") or stripped.startswith("* "):
                clarifications.append(stripped.lstrip("-* ").strip())

    # Only create questions for truly new clarification items —
    # skip anything already asked (answered, incorporated, dismissed, or still open)
    all_existing_qs = await get_questions_for_source(f"note:{note_id}")
    existing_texts = {q["question"].lower().strip() for q in all_existing_qs}

    new_clarifications = 0
    for item in clarifications:
        if item and item.lower().strip() not in existing_texts:
            await ask(
                question=item,
                context=f'From note enhancement: "{note["title"]}"',
                source_task=f"note:{note_id}",
            )
            new_clarifications += 1

    # Mark previously answered questions as incorporated
    if answered_qs:
        await mark_incorporated(f"note:{note_id}")

    return {
        "note_id": note_id,
        "enhanced_content": enhanced,
        "source_hash": source_hash,
        "generated_at": now,
        "stale": False,
        "clarifications_created": new_clarifications,
        "answers_incorporated": len(answered_qs),
    }


async def get_enhancement(note_id: int) -> dict | None:
    """Get the stored enhancement for a note, with stale detection and question counts."""
    from app.services.questions import get_questions_for_source

    note = await get_note(note_id)
    if not note:
        return None

    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT enhanced_content, source_hash, generated_at FROM note_enhancements WHERE note_id = ?",
            (note_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        stale = _content_hash(note["content"]) != row["source_hash"]

        # Count questions linked to this note
        all_qs = await get_questions_for_source(f"note:{note_id}")
        answered_count = sum(1 for q in all_qs if q["status"] == "answered")
        open_count = sum(1 for q in all_qs if q["status"] == "open")

        return {
            "note_id": note_id,
            "enhanced_content": row["enhanced_content"],
            "source_hash": row["source_hash"],
            "generated_at": row["generated_at"],
            "stale": stale,
            "answered_question_count": answered_count,
            "open_question_count": open_count,
        }
    finally:
        await db.close()


async def delete_enhancement(note_id: int) -> bool:
    db = await _get_db()
    try:
        cursor = await db.execute("DELETE FROM note_enhancements WHERE note_id = ?", (note_id,))
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()
