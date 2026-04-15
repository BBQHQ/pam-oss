"""Prompt Zone endpoints — saved prompts with golden (starred) support."""

from fastapi import APIRouter, Query
from pydantic import BaseModel
from app.services import prompt_zone

router = APIRouter(prefix="/prompts", tags=["prompts"])


class PromptCreate(BaseModel):
    title: str
    prompt: str
    golden: bool = False


class PromptUpdate(BaseModel):
    title: str | None = None
    prompt: str | None = None
    golden: bool | None = None


@router.get("/")
async def list_prompts(golden: bool = Query(False)):
    return await prompt_zone.list_prompts(golden_only=golden)


@router.post("/")
async def create_prompt(body: PromptCreate):
    return await prompt_zone.create_prompt(
        title=body.title, prompt=body.prompt, golden=body.golden
    )


@router.get("/{prompt_id}")
async def get_prompt(prompt_id: int):
    item = await prompt_zone.get_prompt(prompt_id)
    if not item:
        return {"error": "Not found"}
    return item


@router.put("/{prompt_id}")
async def update_prompt(prompt_id: int, body: PromptUpdate):
    item = await prompt_zone.update_prompt(
        prompt_id, title=body.title, prompt=body.prompt, golden=body.golden
    )
    if not item:
        return {"error": "Not found"}
    return item


@router.delete("/{prompt_id}")
async def delete_prompt(prompt_id: int):
    ok = await prompt_zone.delete_prompt(prompt_id)
    return {"deleted": ok}
