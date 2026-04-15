"""PAM Questions endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel
from app.services.questions import ask, get_open_questions, get_all_questions, answer_question, dismiss_question

router = APIRouter(prefix="/questions", tags=["questions"])


class AskQuestion(BaseModel):
    question: str
    context: str = ""
    source_task: str | None = None


class AnswerQuestion(BaseModel):
    answer: str


@router.post("/")
async def create_question(body: AskQuestion):
    return await ask(body.question, body.context, body.source_task)


@router.get("/")
async def list_questions(include_answered: bool = False):
    return await get_all_questions(include_answered)


@router.get("/open")
async def list_open():
    return await get_open_questions()


@router.post("/{question_id}/answer")
async def submit_answer(question_id: int, body: AnswerQuestion):
    result = await answer_question(question_id, body.answer)
    if not result:
        return {"error": "Not found"}
    return result


@router.post("/{question_id}/dismiss")
async def dismiss(question_id: int):
    return {"dismissed": await dismiss_question(question_id)}
