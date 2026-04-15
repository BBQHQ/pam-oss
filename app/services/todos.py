"""To-do list — categories, sub-tasks, and recurring habits, stored in SQLite."""

import json
import aiosqlite
from datetime import datetime, date
from pathlib import Path
from app.config import DATA_DIR
from app.models import Todo

DB_PATH = DATA_DIR / "notes.db"
_MIGRATED_MARKER = DATA_DIR / "todos.json.migrated"
TODOS_JSON = DATA_DIR / "todos.json"


async def _get_db():
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("""
        CREATE TABLE IF NOT EXISTS todos (
            id        TEXT PRIMARY KEY,
            text      TEXT NOT NULL,
            done      INTEGER NOT NULL DEFAULT 0,
            category  TEXT,
            parent_id TEXT,
            position  INTEGER NOT NULL DEFAULT 0,
            created   TEXT NOT NULL,
            FOREIGN KEY (parent_id) REFERENCES todos(id) ON DELETE SET NULL
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_todos_category ON todos(category)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_todos_parent ON todos(parent_id)"
    )
    # Habit columns — safe to re-run (ALTER TABLE ADD COLUMN is no-op if exists)
    for col, defn in [
        ("recurrence", "TEXT"),
        ("recurrence_days", "TEXT"),
        ("streak_current", "INTEGER NOT NULL DEFAULT 0"),
        ("streak_best", "INTEGER NOT NULL DEFAULT 0"),
        ("last_reset", "TEXT"),
        ("completion_count", "INTEGER NOT NULL DEFAULT 0"),
        ("week_count", "INTEGER NOT NULL DEFAULT 0"),
        ("last_week", "TEXT"),
    ]:
        try:
            await db.execute(f"ALTER TABLE todos ADD COLUMN {col} {defn}")
        except Exception:
            pass  # column already exists
    await db.commit()

    # One-shot backfill: habits that were already `done=1` when the
    # week_count / completion_count columns were added won't have
    # been counted by toggle_todo (which only increments on transition).
    # Guard by last_week IS NULL so this only runs for pre-migration rows.
    this_week = _iso_week()
    await db.execute(
        "UPDATE todos SET week_count = 1, "
        "completion_count = MAX(completion_count, 1), last_week = ? "
        "WHERE recurrence IS NOT NULL AND done = 1 AND last_week IS NULL",
        (this_week,),
    )
    # And stamp last_week on already-processed done=0 habits so the
    # rollover logic knows they've been seen this week.
    await db.execute(
        "UPDATE todos SET last_week = ? "
        "WHERE recurrence IS NOT NULL AND last_week IS NULL",
        (this_week,),
    )
    await db.commit()

    # One-time migration from todos.json
    if TODOS_JSON.exists() and not _MIGRATED_MARKER.exists():
        try:
            with open(TODOS_JSON, "r") as f:
                old_todos = json.load(f)
            for t in old_todos:
                await db.execute(
                    "INSERT OR IGNORE INTO todos (id, text, done, category, parent_id, position, created) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (t["id"], t["text"], int(t.get("done", False)), None, None, 0, t["created"]),
                )
            await db.commit()
            TODOS_JSON.rename(_MIGRATED_MARKER)
        except Exception:
            pass

    return db


def _row_to_todo(row) -> Todo:
    return Todo(
        id=row["id"],
        text=row["text"],
        done=bool(row["done"]),
        category=row["category"],
        parent_id=row["parent_id"],
        position=row["position"],
        created=row["created"],
        recurrence=row["recurrence"] if "recurrence" in row.keys() else None,
        recurrence_days=row["recurrence_days"] if "recurrence_days" in row.keys() else None,
        streak_current=row["streak_current"] if "streak_current" in row.keys() else 0,
        streak_best=row["streak_best"] if "streak_best" in row.keys() else 0,
        last_reset=row["last_reset"] if "last_reset" in row.keys() else None,
        completion_count=row["completion_count"] if "completion_count" in row.keys() else 0,
        week_count=row["week_count"] if "week_count" in row.keys() else 0,
        last_week=row["last_week"] if "last_week" in row.keys() else None,
    )


def _iso_week(d: date | None = None) -> str:
    d = d or date.today()
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


async def add_todo(text: str, category: str | None = None, parent_id: str | None = None,
                   recurrence: str | None = None, recurrence_days: str | None = None) -> Todo:
    todo = Todo(text=text, category=category, parent_id=parent_id,
                recurrence=recurrence, recurrence_days=recurrence_days)
    db = await _get_db()
    try:
        # Auto-position: append to end of category
        cur = await db.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM todos WHERE category IS ? AND parent_id IS ?",
            (category, parent_id),
        )
        row = await cur.fetchone()
        todo.position = row[0] if row else 0
        await db.execute(
            "INSERT INTO todos (id, text, done, category, parent_id, position, created, recurrence, recurrence_days) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (todo.id, todo.text, int(todo.done), todo.category, todo.parent_id,
             todo.position, todo.created, todo.recurrence, todo.recurrence_days),
        )
        await db.commit()
        return todo
    finally:
        await db.close()


async def get_todos(show_done: bool = False, include_habits: bool = False) -> list[Todo]:
    """Return todos. Briefing calls this with show_done=False.

    Habits (rows with recurrence IS NOT NULL) are excluded by default so
    the main to-do surfaces don't duplicate the habits widget/section.
    """
    where = []
    if not show_done:
        where.append("done = 0")
    if not include_habits:
        where.append("recurrence IS NULL")
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    db = await _get_db()
    try:
        cur = await db.execute(
            f"SELECT * FROM todos {clause} ORDER BY category, position, created"
        )
        rows = await cur.fetchall()
        return [_row_to_todo(r) for r in rows]
    finally:
        await db.close()


async def get_todos_grouped(show_done: bool = False, include_habits: bool = False) -> dict:
    """Return todos grouped by category with sub-tasks nested.

    Returns {category: {items: [...], done_count: N}} where done_count
    is always present (even when show_done=False) so the UI can show
    a "N done" indicator per category.
    """
    db = await _get_db()
    try:
        # Always fetch all to compute done counts
        if include_habits:
            cur = await db.execute("SELECT * FROM todos ORDER BY category, position, created")
        else:
            cur = await db.execute(
                "SELECT * FROM todos WHERE recurrence IS NULL ORDER BY category, position, created"
            )
        rows = await cur.fetchall()
        all_todos = [_row_to_todo(r) for r in rows]

        categories: dict[str, dict] = {}

        for t in all_todos:
            if t.parent_id:
                continue
            cat = t.category or ""
            if cat not in categories:
                categories[cat] = {"items": [], "done_count": 0}
            if t.done:
                categories[cat]["done_count"] += 1
                # Count done sub-tasks too
                categories[cat]["done_count"] += sum(
                    1 for c in all_todos if c.parent_id == t.id and c.done
                )
                if not show_done:
                    continue
            item = t.model_dump()
            subs = [c for c in all_todos if c.parent_id == t.id]
            if not show_done:
                subs = [c for c in subs if not c.done]
            item["subtasks"] = [c.model_dump() for c in subs]
            categories[cat]["items"].append(item)

        return categories
    finally:
        await db.close()


async def toggle_todo(todo_id: str) -> Todo | None:
    db = await _get_db()
    try:
        cur = await db.execute("SELECT * FROM todos WHERE id = ?", (todo_id,))
        row = await cur.fetchone()
        if not row:
            return None
        new_done = 0 if row["done"] else 1
        is_habit = row["recurrence"] is not None
        if is_habit:
            # Keep week_count fresh for the current ISO week
            this_week = _iso_week()
            if row["last_week"] != this_week:
                await db.execute(
                    "UPDATE todos SET week_count = 0, last_week = ? WHERE id = ?",
                    (this_week, todo_id),
                )
            if new_done == 1:
                # 0 -> 1: count it
                await db.execute(
                    "UPDATE todos SET done = 1, completion_count = completion_count + 1, "
                    "week_count = week_count + 1, last_week = ? WHERE id = ?",
                    (this_week, todo_id),
                )
            else:
                # 1 -> 0: undo the count (floor 0)
                await db.execute(
                    "UPDATE todos SET done = 0, "
                    "completion_count = MAX(completion_count - 1, 0), "
                    "week_count = MAX(week_count - 1, 0) WHERE id = ?",
                    (todo_id,),
                )
        else:
            await db.execute("UPDATE todos SET done = ? WHERE id = ?", (new_done, todo_id))
        await db.commit()
        cur = await db.execute("SELECT * FROM todos WHERE id = ?", (todo_id,))
        return _row_to_todo(await cur.fetchone())
    finally:
        await db.close()


async def delete_todo(todo_id: str) -> bool:
    db = await _get_db()
    try:
        # Orphan sub-tasks: promote to top-level in same category
        cur = await db.execute("SELECT category FROM todos WHERE id = ?", (todo_id,))
        row = await cur.fetchone()
        if not row:
            return False
        await db.execute(
            "UPDATE todos SET parent_id = NULL WHERE parent_id = ?", (todo_id,)
        )
        await db.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
        await db.commit()
        return True
    finally:
        await db.close()


async def get_categories() -> list[str]:
    db = await _get_db()
    try:
        cur = await db.execute(
            "SELECT DISTINCT category FROM todos WHERE category IS NOT NULL AND category != '' ORDER BY category"
        )
        rows = await cur.fetchall()
        return [r["category"] for r in rows]
    finally:
        await db.close()


async def update_todo(todo_id: str, text: str | None = None, category: str | None = None) -> Todo | None:
    db = await _get_db()
    try:
        cur = await db.execute("SELECT * FROM todos WHERE id = ?", (todo_id,))
        row = await cur.fetchone()
        if not row:
            return None
        new_text = text if text is not None else row["text"]
        new_cat = category if category is not None else row["category"]
        await db.execute(
            "UPDATE todos SET text = ?, category = ? WHERE id = ?",
            (new_text, new_cat, todo_id),
        )
        await db.commit()
        cur = await db.execute("SELECT * FROM todos WHERE id = ?", (todo_id,))
        return _row_to_todo(await cur.fetchone())
    finally:
        await db.close()


async def reorder_todo(todo_id: str, position: int) -> bool:
    db = await _get_db()
    try:
        await db.execute("UPDATE todos SET position = ? WHERE id = ?", (position, todo_id))
        await db.commit()
        return True
    finally:
        await db.close()


# --- Habits (recurring todos) ---

RECURRENCE_WEEKDAYS = {
    "daily": [0, 1, 2, 3, 4, 5, 6],
    "weekdays": [0, 1, 2, 3, 4],
    "MWF": [0, 2, 4],
    "TTh": [1, 3],
    "weekly": None,  # defaults to the day it was created
}


def _is_scheduled_today(recurrence: str, recurrence_days: str | None, created: str) -> bool:
    """Check if a habit is scheduled for today."""
    today_weekday = date.today().weekday()  # Mon=0..Sun=6

    if recurrence == "custom" and recurrence_days:
        try:
            days = json.loads(recurrence_days)
            return today_weekday in days
        except Exception:
            return True

    if recurrence == "weekly":
        # Scheduled on the same weekday it was created
        try:
            created_weekday = datetime.fromisoformat(created).weekday()
            return today_weekday == created_weekday
        except Exception:
            return True

    weekdays = RECURRENCE_WEEKDAYS.get(recurrence)
    if weekdays is not None:
        return today_weekday in weekdays

    return True  # fallback: treat as daily


async def get_habits() -> list[Todo]:
    """Return all habits (todos with recurrence set)."""
    db = await _get_db()
    try:
        cur = await db.execute(
            "SELECT * FROM todos WHERE recurrence IS NOT NULL ORDER BY position, created"
        )
        rows = await cur.fetchall()
        return [_row_to_todo(r) for r in rows]
    finally:
        await db.close()


def _expected_per_week(recurrence: str, recurrence_days: str | None) -> int:
    """How many times a week a habit is scheduled (for X/Y rollup)."""
    if recurrence == "custom" and recurrence_days:
        try:
            return max(1, len(json.loads(recurrence_days)))
        except Exception:
            return 7
    weekdays = RECURRENCE_WEEKDAYS.get(recurrence)
    if weekdays is None:
        return 1  # weekly
    return len(weekdays)


async def get_habit_summary() -> dict:
    """Summary for briefing and dashboard: today's done/total, active streaks."""
    habits = await get_habits()
    today_habits = [h for h in habits if _is_scheduled_today(h.recurrence, h.recurrence_days, h.created)]
    today_done = sum(1 for h in today_habits if h.done)
    today_total = len(today_habits)

    active_streaks = [
        {"text": h.text, "current": h.streak_current, "best": h.streak_best}
        for h in habits if h.streak_current > 0
    ]
    active_streaks.sort(key=lambda s: s["current"], reverse=True)

    label = f"{today_done}/{today_total} done today"
    if active_streaks:
        top = active_streaks[0]
        label += f", longest streak: {top['text']} ({top['current']}d)"

    habit_payload = []
    for h in today_habits:
        d = h.model_dump()
        d["expected_per_week"] = _expected_per_week(h.recurrence, h.recurrence_days)
        habit_payload.append(d)

    return {
        "today_done": today_done,
        "today_total": today_total,
        "active_streaks": active_streaks[:5],
        "habits": habit_payload,
        "label": label,
    }


async def reset_habits():
    """Daily reset: increment streaks for done habits, reset missed ones.

    Called by the 4am scheduler. Each habit resets at most once per day
    (tracked by last_reset).
    """
    from app.services import accomplishments

    today_str = date.today().isoformat()
    this_week = _iso_week()
    db = await _get_db()
    try:
        # Week rollover: zero week_count for any habit not yet rolled to this week
        await db.execute(
            "UPDATE todos SET week_count = 0, last_week = ? "
            "WHERE recurrence IS NOT NULL AND (last_week IS NULL OR last_week != ?)",
            (this_week, this_week),
        )
        await db.commit()

        cur = await db.execute(
            "SELECT * FROM todos WHERE recurrence IS NOT NULL"
        )
        rows = await cur.fetchall()
        habits = [_row_to_todo(r) for r in rows]

        for h in habits:
            # Skip if already reset today
            if h.last_reset == today_str:
                continue
            # Skip if not scheduled today
            if not _is_scheduled_today(h.recurrence, h.recurrence_days, h.created):
                continue

            if h.done:
                # Completed — increment streak, log accomplishment, reset for new day
                new_streak = h.streak_current + 1
                new_best = max(h.streak_best, new_streak)
                await db.execute(
                    "UPDATE todos SET done=0, streak_current=?, streak_best=?, last_reset=? WHERE id=?",
                    (new_streak, new_best, today_str, h.id),
                )
                await accomplishments.safe_log("todo", h.text, source_id=f"habit-{h.id}-{today_str}")
            else:
                # Missed — reset streak, clean slate
                await db.execute(
                    "UPDATE todos SET streak_current=0, last_reset=? WHERE id=?",
                    (today_str, h.id),
                )

        await db.commit()
    finally:
        await db.close()
