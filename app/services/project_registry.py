"""Project registry — keyword matching to route tasks to projects."""

import json
from app.config import DATA_DIR
from app.models import Project

_projects: list[Project] = []
PROJECTS_FILE = DATA_DIR / "projects.json"


def load_projects():
    """Load projects from JSON file."""
    global _projects
    try:
        with open(PROJECTS_FILE, "r") as f:
            data = json.load(f)
        _projects = [Project(**p) for p in data["projects"]]
    except Exception as e:
        print(f"[PAM] Failed to load projects: {e}")
        _projects = []


def get_projects() -> list[Project]:
    """Return all registered projects."""
    if not _projects:
        load_projects()
    return _projects


def match_project(text: str) -> Project | None:
    """Match text against project aliases. Returns best match or None."""
    if not _projects:
        load_projects()

    text_lower = text.lower()
    best_match = None
    best_score = 0

    for project in _projects:
        for alias in project.aliases:
            alias_lower = alias.lower()
            # Exact word boundary match scores higher
            if f" {alias_lower} " in f" {text_lower} ":
                score = len(alias_lower) + 10  # bonus for exact word match
            elif alias_lower in text_lower:
                score = len(alias_lower)
            else:
                continue

            if score > best_score:
                best_score = score
                best_match = project

    return best_match
