"""Task engine — queue, triage, dispatch."""

import json
from datetime import datetime
from pathlib import Path
from app.config import DATA_DIR
from app.models import Task, TaskStatus, ExecutionType, Priority
from app.services.project_registry import match_project

TASKS_FILE = DATA_DIR / "tasks.json"

# Keywords that suggest different execution types
_CLAUDE_KEYWORDS = [
    "research", "investigate", "find out", "look up", "analyze",
    "draft", "write", "compose", "summarize", "review",
    "plan", "design", "architect", "figure out", "compare",
]

_AUTO_KEYWORDS = [
    "download", "transcribe", "remind", "add to board",
    "note", "save", "log", "record",
]

# Keywords that suggest staging (needs human approval before acting)
_STAGING_KEYWORDS = [
    "email", "send", "invite",
    "delete", "remove", "cancel",
]


def _load_tasks() -> list[Task]:
    """Load tasks from JSON file."""
    if not TASKS_FILE.exists():
        return []
    try:
        with open(TASKS_FILE, "r") as f:
            data = json.load(f)
        return [Task(**t) for t in data]
    except Exception:
        return []


def _save_tasks(tasks: list[Task]):
    """Save tasks to JSON file."""
    TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TASKS_FILE, "w") as f:
        json.dump([t.model_dump() for t in tasks], f, indent=2)


def _triage(text: str) -> tuple[ExecutionType, TaskStatus]:
    """Determine execution type and initial status from task text."""
    text_lower = text.lower()

    # Check Claude first — multi-step reasoning tasks take priority
    for kw in _CLAUDE_KEYWORDS:
        if kw in text_lower:
            return ExecutionType.claude, TaskStatus.queued

    # Check if it needs staging (human approval before acting)
    for kw in _STAGING_KEYWORDS:
        if kw in text_lower:
            return ExecutionType.auto, TaskStatus.staged

    # Check if auto-executable
    for kw in _AUTO_KEYWORDS:
        if kw in text_lower:
            return ExecutionType.auto, TaskStatus.queued

    # Default: unknown, goes to staging for review
    return ExecutionType.unknown, TaskStatus.staged


def submit_task(text: str, source: str = "dashboard", priority: str = "normal") -> Task:
    """Create a new task from raw text input."""
    # Triage
    exec_type, status = _triage(text)

    # Match to project
    project_match = match_project(text)

    task = Task(
        title=text[:120],
        description=text,
        source=source,
        source_raw=text,
        status=status,
        execution_type=exec_type,
        priority=Priority(priority) if priority in Priority.__members__ else Priority.normal,
        project=project_match.name if project_match else None,
    )

    tasks = _load_tasks()
    tasks.append(task)
    _save_tasks(tasks)
    return task


def get_tasks(status: str | None = None) -> list[Task]:
    """Get all tasks, optionally filtered by status."""
    tasks = _load_tasks()
    if status:
        tasks = [t for t in tasks if t.status == status]
    return tasks


def get_task(task_id: str) -> Task | None:
    """Get a single task by ID."""
    tasks = _load_tasks()
    for t in tasks:
        if t.id == task_id:
            return t
    return None


def update_task_status(task_id: str, new_status: str, result: str | None = None) -> Task | None:
    """Update a task's status."""
    tasks = _load_tasks()
    for t in tasks:
        if t.id == task_id:
            t.status = TaskStatus(new_status)
            if result:
                t.result = result
            if new_status == "done":
                t.completed = datetime.now().isoformat()
            _save_tasks(tasks)
            return t
    return None


def delete_task(task_id: str) -> bool:
    """Delete a task by ID."""
    tasks = _load_tasks()
    original_len = len(tasks)
    tasks = [t for t in tasks if t.id != task_id]
    if len(tasks) < original_len:
        _save_tasks(tasks)
        return True
    return False
