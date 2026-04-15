"""Gratitude tiles — pillar (user-curated) and progress (data-enriched)."""

import json
import aiosqlite
from datetime import datetime, timedelta
from app.config import DATA_DIR
from app.models import GratitudeTile

DB_PATH = DATA_DIR / "notes.db"

DEFAULT_PILLARS = [
    {"title": "Family & Friends", "body": "Daughter, marriage, relationships -- the people who matter most.", "icon": "FAM", "color": "rgba(232, 143, 143, 0.3)"},
    {"title": "Health", "body": "Physical wellbeing, ability to be active, energy to keep building.", "icon": "HP", "color": "rgba(143, 232, 166, 0.3)"},
    {"title": "Home", "body": "Beautiful house, great neighborhood everybody wants to live in.", "icon": "HM", "color": "rgba(143, 186, 232, 0.3)"},
    {"title": "Animals", "body": "Pets, nature, the living things that ground you.", "icon": "PET", "color": "rgba(200, 175, 232, 0.3)"},
    {"title": "Career", "body": "Good income, AI consulting, meaningful work that matters.", "icon": "WRK", "color": "rgba(232, 206, 143, 0.3)"},
    {"title": "Creative Freedom", "body": "Ability to build whatever you want with AI. More progress than ever.", "icon": "DEV", "color": "rgba(143, 220, 232, 0.3)"},
]

DEFAULT_PROGRESS = [
    {"title": "Projects", "body": "", "icon": "PRJ", "data_source": "commits", "color": "rgba(54, 241, 205, 0.2)"},
    {"title": "Habits", "body": "", "icon": "HAB", "data_source": "habits", "color": "rgba(232, 183, 106, 0.2)"},
    {"title": "Wins", "body": "", "icon": "WIN", "data_source": "wins", "color": "rgba(167, 139, 250, 0.2)"},
]


async def _get_db():
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("""
        CREATE TABLE IF NOT EXISTS gratitude (
            id          TEXT PRIMARY KEY,
            title       TEXT NOT NULL,
            body        TEXT DEFAULT '',
            icon        TEXT DEFAULT '',
            category    TEXT DEFAULT 'pillar',
            data_source TEXT,
            position    INTEGER NOT NULL DEFAULT 0,
            color       TEXT DEFAULT 'rgba(232, 183, 106, 0.3)',
            created     TEXT NOT NULL,
            updated     TEXT
        )
    """)
    await db.commit()
    return db


def _row_to_tile(row) -> dict:
    return dict(row)


async def seed_defaults():
    """Create default tiles if table is empty. Called on first access."""
    db = await _get_db()
    try:
        cur = await db.execute("SELECT COUNT(*) AS c FROM gratitude")
        row = await cur.fetchone()
        if row["c"] > 0:
            return
        now = datetime.now().isoformat()
        pos = 0
        for p in DEFAULT_PILLARS:
            tile = GratitudeTile(title=p["title"], body=p["body"], icon=p["icon"],
                                 category="pillar", color=p["color"], position=pos)
            await db.execute(
                "INSERT INTO gratitude (id, title, body, icon, category, data_source, position, color, created) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (tile.id, tile.title, tile.body, tile.icon, tile.category, None, pos, tile.color, now),
            )
            pos += 1
        for p in DEFAULT_PROGRESS:
            tile = GratitudeTile(title=p["title"], body=p["body"], icon=p["icon"],
                                 category="progress", data_source=p["data_source"],
                                 color=p["color"], position=pos)
            await db.execute(
                "INSERT INTO gratitude (id, title, body, icon, category, data_source, position, color, created) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (tile.id, tile.title, tile.body, tile.icon, tile.category, tile.data_source, pos, tile.color, now),
            )
            pos += 1
        await db.commit()
    finally:
        await db.close()


async def get_tiles() -> list[dict]:
    """Return all tiles, progress tiles enriched with live data."""
    await seed_defaults()
    db = await _get_db()
    try:
        cur = await db.execute("SELECT * FROM gratitude ORDER BY position, created")
        rows = await cur.fetchall()
        tiles = [_row_to_tile(r) for r in rows]
    finally:
        await db.close()

    # Enrich progress tiles
    for tile in tiles:
        if tile["category"] == "progress" and tile["data_source"]:
            tile["progress_data"] = await _enrich_progress(tile["data_source"])

    return tiles


async def _enrich_progress(source: str) -> dict:
    """Fetch live stats for a progress tile."""
    if source == "commits":
        try:
            from app.services.briefing import _get_recent_commits
            commits = await _get_recent_commits(hours=168)  # 7 days
            projects = set(c["project"] for c in commits)
            return {
                "count_7d": len(commits),
                "projects": sorted(projects),
                "label": f"{len(commits)} commits across {len(projects)} projects this week",
            }
        except Exception:
            return {"count_7d": 0, "projects": [], "label": "No recent commits"}

    elif source == "habits":
        try:
            from app.services.todos import get_habit_summary
            summary = await get_habit_summary()
            return summary
        except Exception:
            return {"today_done": 0, "today_total": 0, "label": "No habits yet"}

    elif source == "wins":
        try:
            from app.services.accomplishments import count_recent, list_accomplishments
            count_7d = await count_recent(days=7)
            count_prev = await count_recent(days=14) - count_7d
            trend = "up" if count_7d > count_prev else ("down" if count_7d < count_prev else "flat")
            return {
                "count_7d": count_7d,
                "count_prev_7d": count_prev,
                "trend": trend,
                "label": f"{count_7d} wins this week ({trend} from {count_prev} last week)",
            }
        except Exception:
            return {"count_7d": 0, "trend": "flat", "label": "No recent wins"}

    return {}


async def add_tile(title: str, body: str = "", icon: str = "", category: str = "pillar",
                   data_source: str | None = None, color: str = "rgba(232, 183, 106, 0.3)") -> dict:
    tile = GratitudeTile(title=title, body=body, icon=icon, category=category,
                         data_source=data_source, color=color)
    db = await _get_db()
    try:
        cur = await db.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM gratitude")
        row = await cur.fetchone()
        tile.position = row[0] if row else 0
        await db.execute(
            "INSERT INTO gratitude (id, title, body, icon, category, data_source, position, color, created) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (tile.id, tile.title, tile.body, tile.icon, tile.category, tile.data_source,
             tile.position, tile.color, tile.created),
        )
        await db.commit()
        return tile.model_dump()
    finally:
        await db.close()


async def update_tile(tile_id: str, title: str | None = None, body: str | None = None,
                      icon: str | None = None, color: str | None = None) -> dict | None:
    db = await _get_db()
    try:
        cur = await db.execute("SELECT * FROM gratitude WHERE id = ?", (tile_id,))
        row = await cur.fetchone()
        if not row:
            return None
        new_title = title if title is not None else row["title"]
        new_body = body if body is not None else row["body"]
        new_icon = icon if icon is not None else row["icon"]
        new_color = color if color is not None else row["color"]
        now = datetime.now().isoformat()
        await db.execute(
            "UPDATE gratitude SET title=?, body=?, icon=?, color=?, updated=? WHERE id=?",
            (new_title, new_body, new_icon, new_color, now, tile_id),
        )
        await db.commit()
        cur = await db.execute("SELECT * FROM gratitude WHERE id = ?", (tile_id,))
        return _row_to_tile(await cur.fetchone())
    finally:
        await db.close()


async def delete_tile(tile_id: str) -> bool:
    db = await _get_db()
    try:
        cur = await db.execute("DELETE FROM gratitude WHERE id = ?", (tile_id,))
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()


async def get_gratitude_summary() -> dict:
    """Summary for briefing injection — pillar titles + progress stats."""
    tiles = await get_tiles()
    pillars = [t["title"] for t in tiles if t["category"] == "pillar"]
    progress = {t["title"]: t.get("progress_data", {}).get("label", "")
                for t in tiles if t["category"] == "progress"}
    return {"pillars": pillars, "progress": progress}
