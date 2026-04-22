"""To-do list — categories, sub-tasks, and recurring habits, stored in SQLite."""

import json
import aiosqlite
from datetime import datetime, date, timedelta
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
    """Summary for briefing and dashboard: today's done/total, active streaks.

    `habits` = only habits scheduled for today (what the briefing uses).
    `all_habits` = every habit with a `scheduled_today` flag so the dashboard
    can show the full list and dim off-today ones.
    """
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
    # Sort by frequency desc: daily(7) -> weekdays(5) -> MWF(3) -> TTh(2) -> weekly(1)
    habit_payload.sort(key=lambda d: (-d["expected_per_week"], d["text"].lower()))

    all_habits_payload = []
    for h in habits:
        d = h.model_dump()
        d["expected_per_week"] = _expected_per_week(h.recurrence, h.recurrence_days)
        d["scheduled_today"] = _is_scheduled_today(h.recurrence, h.recurrence_days, h.created)
        all_habits_payload.append(d)
    all_habits_payload.sort(key=lambda d: (-d["expected_per_week"], d["text"].lower()))

    return {
        "today_done": today_done,
        "today_total": today_total,
        "active_streaks": active_streaks[:5],
        "habits": habit_payload,
        "all_habits": all_habits_payload,
        "label": label,
    }


MILESTONE_TIERS = [
    (10, "Starter"),
    (50, "Regular"),
    (100, "Committed"),
    (365, "Year"),
    (1000, "Legend"),
]


def _scheduled_weekdays(recurrence: str, recurrence_days: str | None, created: str) -> set[int]:
    """Return the set of weekdays (Mon=0..Sun=6) a habit is scheduled on."""
    if recurrence == "custom" and recurrence_days:
        try:
            return set(json.loads(recurrence_days))
        except Exception:
            return set(range(7))
    if recurrence == "weekly":
        try:
            return {datetime.fromisoformat(created).weekday()}
        except Exception:
            return set(range(7))
    wd = RECURRENCE_WEEKDAYS.get(recurrence)
    return set(wd) if wd is not None else set(range(7))


async def _habit_daily_completions(since_iso: str | None = None) -> dict:
    """Return per-day habit completion rows from the accomplishments log.

    Shape: {"by_date": {"YYYY-MM-DD": total_count},
            "by_habit_date": {habit_id: {"YYYY-MM-DD": 1, ...}},
            "by_habit_text": {habit_id: text}}
    source_id format is "habit-{habit_id}-{YYYY-MM-DD}".
    """
    # Ensure the accomplishments schema exists before we query it — a fresh
    # install may hit this endpoint before any toggle has materialized the table.
    from app.services import accomplishments
    _ab = await accomplishments._get_db()
    await _ab.close()
    db = await _get_db()
    try:
        clause = "WHERE source = 'todo' AND source_id LIKE 'habit-%'"
        params: list = []
        if since_iso:
            clause += " AND completed_at >= ?"
            params.append(since_iso)
        cur = await db.execute(
            f"SELECT source_id, text, DATE(completed_at) AS d FROM accomplishments {clause}",
            params,
        )
        rows = await cur.fetchall()
    finally:
        await db.close()

    by_date: dict[str, int] = {}
    by_habit_date: dict[str, dict[str, int]] = {}
    by_habit_text: dict[str, str] = {}
    for r in rows:
        sid = r["source_id"]
        d = r["d"]
        if not sid or not d:
            continue
        # source_id = "habit-{id}-{YYYY-MM-DD}" — id may contain dashes
        parts = sid.split("-")
        if len(parts) < 5 or parts[0] != "habit":
            continue
        habit_id = "-".join(parts[1:-3])
        by_date[d] = by_date.get(d, 0) + 1
        by_habit_date.setdefault(habit_id, {})[d] = 1
        by_habit_text[habit_id] = r["text"]
    return {"by_date": by_date, "by_habit_date": by_habit_date, "by_habit_text": by_habit_text}


async def get_habits_totals() -> dict:
    """Scoreboard: totals, active days, perfect days, longest streak, hall of fame."""
    habits = await get_habits()
    total_completions = sum(h.completion_count for h in habits)
    longest_streak_ever = max((h.streak_best for h in habits), default=0)

    daily = await _habit_daily_completions()
    by_date = daily["by_date"]
    active_days = len(by_date)

    # Perfect day = every then-existing habit scheduled for that weekday was completed
    perfect_days = 0
    habit_schedules = []
    for h in habits:
        try:
            created_d = datetime.fromisoformat(h.created).date()
        except Exception:
            created_d = date.today()
        habit_schedules.append({
            "id": h.id,
            "created": created_d,
            "weekdays": _scheduled_weekdays(h.recurrence, h.recurrence_days, h.created),
        })
    by_habit_date = daily["by_habit_date"]
    for d_str in by_date.keys():
        try:
            d = date.fromisoformat(d_str)
        except Exception:
            continue
        wd = d.weekday()
        scheduled = [hs for hs in habit_schedules if d >= hs["created"] and wd in hs["weekdays"]]
        if not scheduled:
            continue
        completed = sum(
            1 for hs in scheduled if by_habit_date.get(hs["id"], {}).get(d_str)
        )
        if completed == len(scheduled):
            perfect_days += 1

    # Tracking since = earliest habit created date
    created_dates = []
    for h in habits:
        try:
            created_dates.append(datetime.fromisoformat(h.created).date())
        except Exception:
            pass
    tracking_since = min(created_dates).isoformat() if created_dates else None
    days_tracked = (date.today() - min(created_dates)).days + 1 if created_dates else 0

    hall_of_fame = sorted(habits, key=lambda h: h.completion_count, reverse=True)[:5]
    return {
        "total_completions": total_completions,
        "active_days": active_days,
        "perfect_days": perfect_days,
        "longest_streak_ever": longest_streak_ever,
        "tracking_since": tracking_since,
        "days_tracked": days_tracked,
        "total_habits": len(habits),
        "hall_of_fame": [
            {
                "id": h.id,
                "text": h.text,
                "completion_count": h.completion_count,
                "streak_best": h.streak_best,
                "streak_current": h.streak_current,
            }
            for h in hall_of_fame
        ],
    }


async def get_habits_heatmap(year: int | None = None) -> dict:
    """Heatmap: daily counts + per-habit strips + stat row, for a calendar year."""
    today = date.today()
    year = year or today.year
    start_date = date(year, 1, 1)
    end_date = date(year, 12, 31)
    days = (end_date - start_date).days + 1

    daily = await _habit_daily_completions(since_iso=start_date.isoformat())
    by_date_raw = daily["by_date"]
    by_habit_date = daily["by_habit_date"]

    # Filter to this calendar year only
    by_date = {d: c for d, c in by_date_raw.items() if start_date.isoformat() <= d <= end_date.isoformat()}

    daily_counts = []
    for i in range(days):
        d = date.fromordinal(start_date.toordinal() + i)
        s = d.isoformat()
        daily_counts.append({"date": s, "count": by_date.get(s, 0)})

    total_completions = sum(by_date.values())
    best_day = None
    if by_date:
        bd, bc = max(by_date.items(), key=lambda x: x[1])
        best_day = {"date": bd, "count": bc}

    # Current streak: consecutive days ending today (or Dec 31 for past years) with >=1 completion
    streak_end = today if today.year == year else end_date
    current_streak = 0
    d = streak_end
    while d >= start_date:
        if by_date.get(d.isoformat(), 0) > 0:
            current_streak += 1
        else:
            if d == today:
                d = date.fromordinal(d.toordinal() - 1)
                continue
            break
        d = date.fromordinal(d.toordinal() - 1)

    # Longest streak in window
    longest = 0
    run = 0
    for entry in daily_counts:
        if entry["count"] > 0:
            run += 1
            longest = max(longest, run)
        else:
            run = 0

    active_days = sum(1 for e in daily_counts if e["count"] > 0)

    # Per-habit strips
    habits = await get_habits()
    habits_sorted = sorted(habits, key=lambda h: h.completion_count, reverse=True)
    habit_strips = []
    for h in habits_sorted:
        dates_for_habit = by_habit_date.get(h.id, {})
        year_hits = [d for d in dates_for_habit.keys()
                     if start_date.isoformat() <= d <= end_date.isoformat()]
        habit_strips.append({
            "id": h.id,
            "text": h.text,
            "total": h.completion_count,
            "year_total": len(year_hits),
            "dates": sorted(year_hits),
        })

    return {
        "year": year,
        "days": days,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily_counts": daily_counts,
        "habit_strips": habit_strips,
        "stat_row": {
            "total_completions": total_completions,
            "active_days": active_days,
            "current_streak": current_streak,
            "longest_streak": longest,
            "best_day": best_day,
        },
    }


async def get_habits_milestones() -> dict:
    """Tier progress per habit + closest-to-unlock."""
    habits = await get_habits()
    tier_list = MILESTONE_TIERS

    habit_entries = []
    total_tiers_unlocked = 0
    closest = None  # (remaining, entry)

    for h in habits:
        n = h.completion_count
        tiers = []
        unlocked_count = 0
        next_tier = None
        for threshold, name in tier_list:
            unlocked = n >= threshold
            if unlocked:
                unlocked_count += 1
            tiers.append({"threshold": threshold, "name": name, "unlocked": unlocked})
            if not unlocked and next_tier is None:
                next_tier = {"threshold": threshold, "name": name, "remaining": threshold - n}
        total_tiers_unlocked += unlocked_count
        # Progress bar: between last-unlocked and next
        prev_threshold = 0
        for threshold, _ in tier_list:
            if n >= threshold:
                prev_threshold = threshold
            else:
                break
        entry = {
            "id": h.id,
            "text": h.text,
            "completion_count": n,
            "tiers": tiers,
            "unlocked_count": unlocked_count,
            "total_tiers": len(tier_list),
            "next_tier": next_tier,
            "prev_threshold": prev_threshold,
        }
        habit_entries.append(entry)
        if next_tier is not None:
            if closest is None or next_tier["remaining"] < closest[0]:
                closest = (next_tier["remaining"], {
                    "habit_id": h.id,
                    "habit_text": h.text,
                    "tier_name": next_tier["name"],
                    "threshold": next_tier["threshold"],
                    "remaining": next_tier["remaining"],
                })

    # Days since day one
    created_dates = []
    for h in habits:
        try:
            created_dates.append(datetime.fromisoformat(h.created).date())
        except Exception:
            pass
    days_since_start = (date.today() - min(created_dates)).days + 1 if created_dates else 0

    habit_entries.sort(key=lambda e: e["completion_count"], reverse=True)

    return {
        "total_habits": len(habits),
        "total_completions": sum(h.completion_count for h in habits),
        "tiers_unlocked": total_tiers_unlocked,
        "days_since_start": days_since_start,
        "tier_definitions": [{"threshold": t, "name": n} for t, n in tier_list],
        "habits": habit_entries,
        "closest_milestone": closest[1] if closest else None,
    }


async def backfill_heatmap() -> dict:
    """Recover + hydrate historical habit completions into the heatmap format.

    Step 1 (recover): walk accomplishments logged with source_id=<raw todo.id>
    (the pre-fix toggle format) and re-log each with source_id=habit-{id}-{date}
    using the original completed_at timestamp. Idempotent — accomplishments.log()
    dedupes on (source, source_id).

    Step 2 (hydrate): for any habit whose completion_count still exceeds its
    dated-row count after recovery, distribute the gap backward from yesterday
    across that habit's scheduled days (skipping already-covered days). The
    dates are approximate — original dates were lost at write time — but the
    total and activity pattern match reality.
    """
    from app.services import accomplishments

    habits = await get_habits()
    habit_ids = {h.id: h.text for h in habits}
    if not habit_ids:
        return {"recovered": 0, "hydrated": 0, "habits": 0, "gaps": {}}

    placeholders = ",".join("?" * len(habit_ids))
    db = await _get_db()
    try:
        cur = await db.execute(
            f"SELECT source_id, text, completed_at FROM accomplishments "
            f"WHERE source = 'todo' AND source_id IN ({placeholders})",
            list(habit_ids.keys()),
        )
        rows = await cur.fetchall()
    finally:
        await db.close()

    recovered = 0
    for r in rows:
        habit_id = r["source_id"]
        completed_at = r["completed_at"]
        try:
            date_part = completed_at.split("T")[0]
        except Exception:
            continue
        new_source_id = f"habit-{habit_id}-{date_part}"
        result = await accomplishments.log(
            "todo", r["text"], source_id=new_source_id, completed_at=completed_at
        )
        if result:
            recovered += 1

    # Step 2: hydrate remaining gaps
    hydrated = 0
    today = date.today()
    report = {}
    for h in habits:
        db = await _get_db()
        try:
            cur = await db.execute(
                "SELECT source_id FROM accomplishments "
                "WHERE source = 'todo' AND source_id LIKE ?",
                (f"habit-{h.id}-%",),
            )
            rows_for_h = [row["source_id"] for row in await cur.fetchall()]
        finally:
            await db.close()
        covered_dates = set()
        for sid in rows_for_h:
            parts = sid.rsplit("-", 3)
            if len(parts) >= 4:
                covered_dates.add("-".join(parts[-3:]))

        gap = max(0, h.completion_count - len(covered_dates))
        report[h.text] = {
            "completion_count": h.completion_count,
            "dated_rows_before": len(covered_dates),
            "gap": gap,
        }
        if gap <= 0:
            continue

        try:
            created_d = datetime.fromisoformat(h.created).date()
        except Exception:
            created_d = today - timedelta(days=30)
        scheduled = _scheduled_weekdays(h.recurrence, h.recurrence_days, h.created)

        added = 0
        d = today - timedelta(days=1)
        safety = 0
        while added < gap and d >= created_d and safety < 400:
            safety += 1
            if d.weekday() in scheduled and d.isoformat() not in covered_dates:
                completed_at = datetime.combine(d, datetime.min.time()).replace(hour=20).isoformat()
                source_id = f"habit-{h.id}-{d.isoformat()}"
                result = await accomplishments.log(
                    "todo", h.text, source_id=source_id, completed_at=completed_at
                )
                if result:
                    hydrated += 1
                    added += 1
                    covered_dates.add(d.isoformat())
            d -= timedelta(days=1)
        report[h.text]["hydrated"] = added
        report[h.text]["dated_rows_after"] = len(covered_dates)

    return {
        "recovered": recovered,
        "hydrated": hydrated,
        "habits": len(habit_ids),
        "per_habit": report,
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
