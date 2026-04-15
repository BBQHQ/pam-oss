"""Kanban board endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel
from app.services.kanban import (
    create_card, move_card, update_card, delete_card,
    get_board, get_boards_summary, get_stale_cards,
    BOARDS, BOARD_LABELS,
)

router = APIRouter(prefix="/kanban", tags=["kanban"])


class CardCreate(BaseModel):
    board: str
    title: str
    column: str = "backlog"
    description: str = ""
    project: str | None = None
    color: str | None = None


class CardUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    color: str | None = None


class CardMove(BaseModel):
    column: str
    position: int | None = None


@router.get("/boards")
async def list_boards():
    summary = await get_boards_summary()
    # Include all boards even if empty
    board_map = {s["board"]: s for s in summary}
    result = []
    for b in BOARDS:
        if b in board_map:
            result.append(board_map[b])
        else:
            result.append({"board": b, "label": BOARD_LABELS[b], "columns": {}})
    return result


@router.get("/boards/{board}")
async def read_board(board: str):
    if board not in BOARDS:
        return {"error": f"Invalid board. Choose from: {', '.join(BOARDS)}"}
    return await get_board(board)


@router.post("/cards")
async def new_card(body: CardCreate):
    return await create_card(
        board=body.board, title=body.title, column=body.column,
        description=body.description, project=body.project, color=body.color,
    )


@router.put("/cards/{card_id}")
async def edit_card(card_id: int, body: CardUpdate):
    result = await update_card(card_id, title=body.title, description=body.description, color=body.color)
    if not result:
        return {"error": "Card not found"}
    return result


@router.put("/cards/{card_id}/move")
async def move(card_id: int, body: CardMove):
    result = await move_card(card_id, column=body.column, position=body.position)
    if not result:
        return {"error": "Card not found or invalid column"}
    return result


@router.delete("/cards/{card_id}")
async def remove_card(card_id: int):
    return {"deleted": await delete_card(card_id)}


@router.get("/stale")
async def stale(days: int = 14):
    return await get_stale_cards(days)
