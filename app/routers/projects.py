"""Project registry endpoints."""

from fastapi import APIRouter
from app.services.project_registry import get_projects, match_project, load_projects

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("/")
async def list_projects():
    """List all registered projects."""
    projects = get_projects()
    return [p.model_dump() for p in projects]


@router.get("/match")
async def match(text: str):
    """Match text to a project."""
    project = match_project(text)
    if project:
        return {"matched": True, "project": project.model_dump()}
    return {"matched": False, "project": None}


@router.post("/reload")
async def reload():
    """Reload projects from disk."""
    load_projects()
    return {"status": "reloaded", "count": len(get_projects())}
