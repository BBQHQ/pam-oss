"""Settings endpoints — user-tunable PAM preferences."""

from typing import Any
from fastapi import APIRouter
from pydantic import BaseModel
from app.services.settings import get_settings, set_setting, delete_setting, DEFAULTS

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingSet(BaseModel):
    key: str
    value: Any
    category: str | None = None


@router.get("/")
async def list_settings():
    return await get_settings()


@router.post("/")
async def save_setting(body: SettingSet):
    if body.key not in DEFAULTS:
        return {"error": f"Unknown setting key: {body.key}"}
    return await set_setting(body.key, body.value, body.category)


@router.delete("/{key}")
async def reset_setting(key: str):
    return {"deleted": await delete_setting(key)}
