"""Settings endpoints — user-tunable PAM preferences."""

import asyncio
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import DATA_DIR
from app.services.settings import get_settings, set_setting, delete_setting, DEFAULTS
from pydantic import BaseModel

router = APIRouter(prefix="/settings", tags=["settings"])

_BRAND_DIR = DATA_DIR / "custom" / "brand"
_BRAND_URL_PREFIX = "/custom/brand/"
_BRAND_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_BRAND_MAX_BYTES = 5 * 1024 * 1024


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
    if body.key == "pam_port":
        try:
            port = int(body.value)
        except (TypeError, ValueError):
            raise HTTPException(400, "Port must be an integer.")
        if not 1024 <= port <= 65535:
            raise HTTPException(400, "Port must be between 1024 and 65535.")
        body = SettingSet(key=body.key, value=port, category=body.category)
    return await set_setting(body.key, body.value, body.category)


@router.delete("/{key}")
async def reset_setting(key: str):
    return {"deleted": await delete_setting(key)}


@router.post("/avatar")
async def upload_avatar(file: UploadFile = File(...)):
    """Upload the brand avatar (top-left logo next to the assistant name).

    Overwrites any previous avatar. Saves to `data/custom/brand/avatar.<ext>`
    and stores the URL in the `brand_avatar_url` setting.
    """
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty upload.")
    if len(content) > _BRAND_MAX_BYTES:
        raise HTTPException(413, f"Image too large (max {_BRAND_MAX_BYTES // (1024*1024)}MB).")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _BRAND_EXTS:
        raise HTTPException(400, f"Unsupported image type: {ext or '(none)'}")

    _BRAND_DIR.mkdir(parents=True, exist_ok=True)
    # Clear any previous avatar files so we don't accumulate across ext changes
    for old in _BRAND_DIR.glob("avatar.*"):
        try:
            old.unlink()
        except OSError:
            pass
    target = _BRAND_DIR / f"avatar{ext}"
    await asyncio.to_thread(target.write_bytes, content)

    url = f"{_BRAND_URL_PREFIX}{target.name}"
    await set_setting("brand_avatar_url", url, "ui")
    return {"url": url}


@router.delete("/avatar")
async def clear_avatar():
    """Remove the brand avatar and revert to the default image."""
    if _BRAND_DIR.exists():
        for old in _BRAND_DIR.glob("avatar.*"):
            try:
                old.unlink()
            except OSError:
                pass
    await set_setting("brand_avatar_url", "", "ui")
    return {"cleared": True}
