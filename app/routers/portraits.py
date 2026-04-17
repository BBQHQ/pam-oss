"""Custom portrait management endpoints — list, upload, delete."""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.services import portraits
from app.services.portraits import PERIODS

router = APIRouter(prefix="/settings/portraits", tags=["settings", "portraits"])


@router.get("/")
async def list_all():
    return {"periods": list(PERIODS), "portraits": await portraits.list_portraits()}


@router.post("/upload")
async def upload(period: str = Form(...), file: UploadFile = File(...)):
    content = await file.read()
    try:
        return await portraits.save_uploaded(file.filename or "upload.png", content, period)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/{portrait_id}")
async def remove(portrait_id: int):
    ok = await portraits.delete_portrait(portrait_id)
    if not ok:
        raise HTTPException(404, "Portrait not found.")
    return {"deleted": True}
