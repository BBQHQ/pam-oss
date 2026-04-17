"""Gratitude tiles — pillar (user-curated) and progress (data-enriched)."""

import asyncio
import json
import time
import aiosqlite
from datetime import datetime, timedelta
from app.config import DATA_DIR
from app.models import GratitudeTile

# In-memory TTL cache for progress tile enrichment.
# Keyed by data_source; value = (expires_at_monotonic, data_dict).
# Commits enrichment can be slow (gh api fan-out across repos); 60s is long
# enough to absorb navigation bursts, short enough to feel fresh.
_PROGRESS_TTL_SEC = 60.0
_progress_cache: dict[str, tuple[float, dict]] = {}
_progress_locks: dict[str, asyncio.Lock] = {}

DB_PATH = DATA_DIR / "notes.db"

DEFAULT_PILLARS = [
    {"title": "Family & Friends", "body": "The people who matter most to you.", "icon": "FAM", "color": "rgba(232, 143, 143, 0.3)"},
    {"title": "Health", "body": "Physical wellbeing and the energy to keep going.", "icon": "HP", "color": "rgba(143, 232, 166, 0.3)"},
    {"title": "Home", "body": "The place you live and the space you've made your own.", "icon": "HM", "color": "rgba(143, 186, 232, 0.3)"},
    {"title": "Animals", "body": "Pets, wildlife, the living things around you.", "icon": "PET", "color": "rgba(200, 175, 232, 0.3)"},
    {"title": "Career", "body": "The work you do and what it makes possible.", "icon": "WRK", "color": "rgba(232, 206, 143, 0.3)"},
    {"title": "Creative Freedom", "body": "The ability to build and create on your own terms.", "icon": "DEV", "color": "rgba(143, 220, 232, 0.3)"},
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


async def get_tiles_shell() -> list[dict]:
    """Return tiles without progress enrichment. Paints fast on the client.

    Progress tiles get `progress_data: None` — the client then fetches
    `/gratitude/progress` and fills in the labels asynchronously.
    """
    await seed_defaults()
    db = await _get_db()
    try:
        cur = await db.execute("SELECT * FROM gratitude ORDER BY position, created")
        rows = await cur.fetchall()
        tiles = [_row_to_tile(r) for r in rows]
    finally:
        await db.close()

    for tile in tiles:
        if tile["category"] == "progress":
            tile["progress_data"] = None
    return tiles


async def get_progress_snapshot() -> dict[str, dict]:
    """Return {data_source: enriched_dict} for all active progress tiles.

    Cached for 60s per source so rapid re-navigations don't re-shell-out to
    `gh api` for commits or re-query SQLite for habits/wins.
    """
    db = await _get_db()
    try:
        cur = await db.execute(
            "SELECT DISTINCT data_source FROM gratitude "
            "WHERE category='progress' AND data_source IS NOT NULL"
        )
        sources = [r["data_source"] for r in await cur.fetchall()]
    finally:
        await db.close()

    out: dict[str, dict] = {}
    for src in sources:
        out[src] = await _enrich_progress(src)
    return out


async def get_tiles() -> list[dict]:
    """Return all tiles, progress tiles enriched with live data (uses cache).

    Kept for callers that want a fully-hydrated list in one call — briefing
    uses this via `get_gratitude_summary()`. UI navigates via the
    shell + progress split.
    """
    tiles = await get_tiles_shell()
    for tile in tiles:
        if tile["category"] == "progress" and tile["data_source"]:
            tile["progress_data"] = await _enrich_progress(tile["data_source"])
    return tiles


async def _enrich_progress(source: str) -> dict:
    """Cached wrapper around the real enrichment — 60s TTL per source."""
    now = time.monotonic()
    hit = _progress_cache.get(source)
    if hit and hit[0] > now:
        return hit[1]

    # Single-flight: only one request recomputes per source at a time.
    lock = _progress_locks.setdefault(source, asyncio.Lock())
    async with lock:
        hit = _progress_cache.get(source)
        if hit and hit[0] > time.monotonic():
            return hit[1]
        data = await _compute_progress(source)
        _progress_cache[source] = (time.monotonic() + _PROGRESS_TTL_SEC, data)
        return data


def invalidate_progress_cache(source: str | None = None) -> None:
    """Drop cached enrichment so the next call recomputes. Useful after
    known state changes (todo toggle, win logged) to keep the tile honest."""
    if source is None:
        _progress_cache.clear()
    else:
        _progress_cache.pop(source, None)


async def _compute_progress(source: str) -> dict:
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
