"""
FastAPI server for the college advisor agent.

Endpoints:
- POST /chat  — streaming SSE: progress events then final result
- GET  /health — health check for Railway
"""

import json
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from intake_validation import validate_intake
from agent import run_agent_stream, generate_report, _extract_data_blocks, _json_default

app = FastAPI(title="Next Right Step - Agent API")


class ChatRequest(BaseModel):
    message: str
    conversation_history: list[dict] | None = None
    intake_answers: dict | None = None


class ValidateIntakeRequest(BaseModel):
    key: str
    value: str
    answers: dict


class ReportRetryRequest(BaseModel):
    intake_answers: dict
    conversation_history: list[dict]
    agent_text: str = ""


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/validate-intake")
async def validate_intake_step(req: ValidateIntakeRequest):
    """Checks one free-text intake answer when the user submits the step."""
    return await validate_intake(req.key, req.value, req.answers)


@app.post("/retry-report")
async def retry_report(req: ReportRetryRequest):
    logger = logging.getLogger(__name__)
    data_blocks = _extract_data_blocks(req.conversation_history)
    logger.info("retry-report: extracted %d data_blocks", len(data_blocks))
    if not data_blocks:
        return {"summary": "", "html": "", "error": "No tool data found in conversation history"}
    try:
        report = await generate_report(req.intake_answers, data_blocks, req.agent_text)
        return report
    except Exception as exc:
        logger.exception("retry-report failed: %s", exc)
        return {"summary": "", "html": "", "error": str(exc)}


@app.post("/chat")
async def chat(req: ChatRequest):
    async def event_stream():
        async for event in run_agent_stream(req.message, req.conversation_history, req.intake_answers):
            yield f"data: {json.dumps(event, default=_json_default)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
