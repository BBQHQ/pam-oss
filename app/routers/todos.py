"""To-do list endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel
from app.models import TodoSubmission
from app.services.todos import (
    add_todo, get_todos, get_todos_grouped, toggle_todo,
    delete_todo, get_categories, update_todo, reorder_todo,
    get_habits, get_habit_summary, _expected_per_week,
)
from app.services import accomplishments

router = APIRouter(prefix="/todos", tags=["todos"])


@router.get("/habits")
async def list_habits():
    out = []
    for h in await get_habits():
        d = h.model_dump()
        d["expected_per_week"] = _expected_per_week(h.recurrence, h.recurrence_days)
        out.append(d)
    return out


@router.get("/habits/summary")
async def habits_summary():
    return await get_habit_summary()


@router.post("/")
async def create(body: TodoSubmission):
    todo = await add_todo(body.text, category=body.category, parent_id=body.parent_id,
                          recurrence=body.recurrence, recurrence_days=body.recurrence_days)
    return todo.model_dump()


@router.get("/")
async def list_todos(show_done: bool = False, include_habits: bool = False):
    return [t.model_dump() for t in await get_todos(show_done, include_habits=include_habits)]


@router.get("/grouped")
async def list_grouped(show_done: bool = False, include_habits: bool = False):
    return await get_todos_grouped(show_done=show_done, include_habits=include_habits)


@router.get("/categories")
async def list_categories():
    return await get_categories()


@router.post("/{todo_id}/toggle")
async def toggle(todo_id: str):
    todo = await toggle_todo(todo_id)
    if not todo:
        return {"error": "Not found"}
    if todo.done:
        await accomplishments.safe_log("todo", todo.text, source_id=todo.id)
    else:
        await accomplishments.unlog("todo", todo.id)
    return todo.model_dump()


class TodoUpdate(BaseModel):
    text: str | None = None
    category: str | None = None


@router.put("/{todo_id}")
async def edit(todo_id: str, body: TodoUpdate):
    todo = await update_todo(todo_id, text=body.text, category=body.category)
    if not todo:
        return {"error": "Not found"}
    return todo.model_dump()


class TodoReorder(BaseModel):
    position: int


@router.put("/{todo_id}/reorder")
async def reorder(todo_id: str, body: TodoReorder):
    return {"ok": await reorder_todo(todo_id, body.position)}


@router.delete("/{todo_id}")
async def remove(todo_id: str):
    return {"deleted": await delete_todo(todo_id)}
