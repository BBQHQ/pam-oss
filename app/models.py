"""PAM data models."""

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
import uuid


class TaskStatus(str, Enum):
    queued = "queued"
    staged = "staged"       # needs human review before action
    executing = "executing"
    done = "done"
    blocked = "blocked"


class ExecutionType(str, Enum):
    auto = "auto"           # PAM can do this itself
    claude = "claude"       # needs Claude Code CLI
    unknown = "unknown"     # not yet triaged


class Priority(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"


class Task(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    title: str
    description: str = ""
    source: str = "dashboard"       # dashboard, voice, discord, email
    source_raw: str = ""            # original input text
    status: TaskStatus = TaskStatus.queued
    execution_type: ExecutionType = ExecutionType.unknown
    priority: Priority = Priority.normal
    project: str | None = None      # matched project name
    result: str | None = None       # filled after execution
    created: str = Field(default_factory=lambda: datetime.now().isoformat())
    completed: str | None = None


class TaskSubmission(BaseModel):
    text: str
    source: str = "dashboard"
    priority: str = "normal"


class Todo(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    text: str
    done: bool = False
    category: str | None = None
    parent_id: str | None = None
    position: int = 0
    created: str = Field(default_factory=lambda: datetime.now().isoformat())
    # Habit fields (NULL for normal todos)
    recurrence: str | None = None          # daily, weekdays, weekly, MWF, TTh, custom
    recurrence_days: str | None = None     # JSON array of weekday ints for 'custom'
    streak_current: int = 0
    streak_best: int = 0
    last_reset: str | None = None          # ISO date of last reset
    completion_count: int = 0              # all-time times habit has been marked done
    week_count: int = 0                    # days done within the current ISO week
    last_week: str | None = None           # "YYYY-Www" of last week rollover


class TodoSubmission(BaseModel):
    text: str
    category: str | None = None
    parent_id: str | None = None
    recurrence: str | None = None
    recurrence_days: str | None = None


class GratitudeTile(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    title: str
    body: str = ""
    icon: str = ""
    category: str = "pillar"               # pillar or progress
    data_source: str | None = None         # NULL for pillars; commits/habits/wins for progress
    position: int = 0
    color: str = "rgba(232, 183, 106, 0.3)"
    created: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated: str | None = None


class GratitudeSubmission(BaseModel):
    title: str
    body: str = ""
    icon: str = ""
    category: str = "pillar"
    data_source: str | None = None
    color: str = "rgba(232, 183, 106, 0.3)"


class Project(BaseModel):
    name: str
    aliases: list[str] = []
    path: str
    kanban_board: str | None = None
