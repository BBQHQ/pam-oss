"""PAM Kanban — project boards with cards, columns, and stale detection."""

import aiosqlite
from datetime import datetime, timedelta
from app.config import DATA_DIR

DB_PATH = DATA_DIR / "notes.db"

BOARDS = ["tech", "house", "gamedev", "personal"]
COLUMNS = ["backlog", "in_progress", "review", "done"]
BOARD_LABELS = {
    "tech": "Tech",
    "house": "House",
    "gamedev": "Game Dev",
    "personal": "Personal",
}
COLUMN_LABELS = {
    "backlog": "Backlog",
    "in_progress": "In Progress",
    "review": "Review",
    "done": "Done",
}


async def _get_db():
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("""
        CREATE TABLE IF NOT EXISTS kanban_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            board TEXT NOT NULL,
            col TEXT NOT NULL DEFAULT 'backlog',
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            project TEXT DEFAULT NULL,
            source_task_id TEXT DEFAULT NULL,
            source_todo_id TEXT DEFAULT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            color TEXT DEFAULT NULL,
            created TEXT NOT NULL,
            updated TEXT NOT NULL
        )
    """)
    await db.commit()
    return db


async def create_card(
    board: str,
    title: str,
    column: str = "backlog",
    description: str = "",
    project: str | None = None,
    color: str | None = None,
) -> dict:
    if board not in BOARDS:
        return {"error": f"Invalid board. Choose from: {', '.join(BOARDS)}"}
    if column not in COLUMNS:
        column = "backlog"

    now = datetime.now().isoformat()
    db = await _get_db()
    try:
        # Get next position in column
        cursor = await db.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM kanban_cards WHERE board = ? AND col = ?",
            (board, column),
        )
        pos = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "INSERT INTO kanban_cards (board, col, title, description, project, position, color, created, updated) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (board, column, title, description, project, pos, color, now, now),
        )
        await db.commit()
        return {
            "id": cursor.lastrowid, "board": board, "col": column, "title": title,
            "description": description, "project": project, "position": pos,
            "color": color, "created": now, "updated": now,
        }
    finally:
        await db.close()


async def move_card(card_id: int, column: str, position: int | None = None) -> dict | None:
    if column not in COLUMNS:
        return None

    now = datetime.now().isoformat()
    db = await _get_db()
    try:
        cursor = await db.execute("SELECT * FROM kanban_cards WHERE id = ?", (card_id,))
        row = await cursor.fetchone()
        if not row:
            return None

        if position is None:
            cursor = await db.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM kanban_cards WHERE board = ? AND col = ?",
                (row["board"], column),
            )
            position = (await cursor.fetchone())[0]

        await db.execute(
            "UPDATE kanban_cards SET col = ?, position = ?, updated = ? WHERE id = ?",
            (column, position, now, card_id),
        )
        await db.commit()
        return {**dict(row), "col": column, "position": position, "updated": now}
    finally:
        await db.close()


async def update_card(
    card_id: int,
    title: str | None = None,
    description: str | None = None,
    color: str | None = None,
) -> dict | None:
    db = await _get_db()
    try:
        cursor = await db.execute("SELECT * FROM kanban_cards WHERE id = ?", (card_id,))
        row = await cursor.fetchone()
        if not row:
            return None

        data = dict(row)
        if title is not None: data["title"] = title
        if description is not None: data["description"] = description
        if color is not None: data["color"] = color
        data["updated"] = datetime.now().isoformat()

        await db.execute(
            "UPDATE kanban_cards SET title=?, description=?, color=?, updated=? WHERE id=?",
            (data["title"], data["description"], data["color"], data["updated"], card_id),
        )
        await db.commit()
        return data
    finally:
        await db.close()


async def delete_card(card_id: int) -> bool:
    db = await _get_db()
    try:
        cursor = await db.execute("DELETE FROM kanban_cards WHERE id = ?", (card_id,))
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


async def get_board(board_name: str) -> dict:
    """Get a board with cards grouped by column."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM kanban_cards WHERE board = ? ORDER BY position",
            (board_name,),
        )
        rows = await cursor.fetchall()
        columns = {col: [] for col in COLUMNS}
        for r in rows:
            card = dict(r)
            # Add age in days
            card["age_days"] = (datetime.now() - datetime.fromisoformat(card["created"])).days
            col = card["col"] if card["col"] in COLUMNS else "backlog"
            columns[col].append(card)

        return {
            "board": board_name,
            "label": BOARD_LABELS.get(board_name, board_name),
            "columns": columns,
            "column_labels": COLUMN_LABELS,
        }
    finally:
        await db.close()


async def get_boards_summary() -> list[dict]:
    """Get card counts per board/column for briefing."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT board, col, COUNT(*) as count FROM kanban_cards GROUP BY board, col"
        )
        rows = await cursor.fetchall()

        summary = {}
        for r in rows:
            board = r["board"]
            if board not in summary:
                summary[board] = {"board": board, "label": BOARD_LABELS.get(board, board), "columns": {}}
            summary[board]["columns"][r["col"]] = r["count"]

        return list(summary.values())
    finally:
        await db.close()


async def get_stale_cards(days: int = 14) -> list[dict]:
    """Get cards stuck in 'in_progress' for too long."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM kanban_cards WHERE col = 'in_progress' AND updated < ? ORDER BY updated",
            (cutoff,),
        )
        rows = await cursor.fetchall()
        results = []
        for r in rows:
            card = dict(r)
            card["age_days"] = (datetime.now() - datetime.fromisoformat(card["created"])).days
            card["stale_days"] = (datetime.now() - datetime.fromisoformat(card["updated"])).days
            results.append(card)
        return results
    finally:
        await db.close()
