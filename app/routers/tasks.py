"""Task engine endpoints."""

from fastapi import APIRouter
from app.models import TaskSubmission
from app.services.task_engine import (
    submit_task,
    get_tasks,
    get_task,
    update_task_status,
    delete_task,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("/submit")
async def submit(body: TaskSubmission):
    """Submit a new task from text input."""
    task = submit_task(body.text, source=body.source, priority=body.priority)
    return task.model_dump()


@router.get("/")
async def list_tasks(status: str | None = None):
    """List all tasks, optionally filtered by status."""
    tasks = get_tasks(status)
    return [t.model_dump() for t in tasks]


@router.get("/{task_id}")
async def get_single_task(task_id: str):
    """Get a single task by ID."""
    task = get_task(task_id)
    if not task:
        return {"error": "Task not found"}
    return task.model_dump()


@router.post("/{task_id}/approve")
async def approve_task(task_id: str):
    """Move a staged task to queued (approved for execution)."""
    task = update_task_status(task_id, "queued")
    if not task:
        return {"error": "Task not found"}
    return task.model_dump()


@router.post("/{task_id}/reject")
async def reject_task(task_id: str):
    """Mark a staged task as done (rejected / dismissed)."""
    task = update_task_status(task_id, "done", result="Rejected")
    if not task:
        return {"error": "Task not found"}
    return task.model_dump()


@router.post("/{task_id}/done")
async def complete_task(task_id: str, result: str = ""):
    """Mark a task as done."""
    task = update_task_status(task_id, "done", result=result or "Completed")
    if not task:
        return {"error": "Task not found"}
    from app.services import accomplishments
    await accomplishments.safe_log(
        "task", task.title, source_id=task.id, metadata={"project": task.project}
    )
    return task.model_dump()


@router.delete("/{task_id}")
async def remove_task(task_id: str):
    """Delete a task."""
    deleted = delete_task(task_id)
    return {"deleted": deleted}
