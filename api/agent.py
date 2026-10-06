"""
Agent module: defines tools and runs the model's tool-use loop.

How it works:
1. We define "tools": JSON schemas that tell the model what functions it can call.
2. We send the user's message to the model (Gemini by default, see llm.py) along with the tool definitions.
3. The model either responds directly OR returns tool calls asking to run
   functions with specific arguments.
4. We execute those functions locally, send the results back, and let the
   model decide whether to respond or call another tool.
5. This loop continues until the model produces a final text response.
"""

import asyncio
import json
import logging
import time
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from dotenv import load_dotenv
load_dotenv(dotenv_path="../.env")

import openai
from db import (
    search_schools,
    get_school_programs,
    search_occupations,
)
from career_cost import path1_options
from options import allowed_metrics, candidate_rows, pairwise_gaps, with_rows
from user_numbers import extract_user_numbers
from report import REPORT_PROMPT, render_report, report_schema

logger = logging.getLogger(__name__)

from llm import MODEL, REPORT_MODEL, client  # noqa: E402
# The LLM returns compact JSON content; report.py renders the HTML.
REPORT_SPEC_MAX_TOKENS = 4096
# Typical report output size, used to estimate progress while the report streams.
# Tune from the "[timing] report LLM call" log lines.
REPORT_EXPECTED_TOKENS = 1500

# Progress bar ranges (percent) for each stage of a run.
GATHERING_START, GATHERING_END = 5, 60
GATHERING_STEP = 8
WRITING_END = 95
RENDERING_PERCENT = 97

# Cap agent loop so a misbehaving model can't spin forever.
# 8 = enough for realistic multi-tool trajectories, small enough that
# a runaway loop stops fast and cheap.
MAX_TOOL_ITERATIONS = 8

# One retry on transient API failure (network blip, 5xx, rate limit).
# More than one retry hides real outages behind long user-facing waits.
MAX_API_RETRIES = 1
RETRY_BACKOFF_SECONDS = 2

# Cap conversation history to keep prompt size + cost bounded.
# 40 = ~20 user/assistant pairs, plenty for a session but stops runaway growth.
MAX_HISTORY_MESSAGES = 40


def _json_default(obj):
    """Explicit JSON coercion for known non-JSON types. Raises on anything else
    so unexpected schema drift is loud instead of silently stringified."""
    if isinstance(obj, (UUID, Decimal)):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _trim_history(messages: list[dict]) -> list[dict]:
    """Keep the last MAX_HISTORY_MESSAGES, but never start on a dangling tool
    message or assistant tool call: tool calls and their results must stay
    paired, so drop leading messages until the first one is a user turn."""
    if len(messages) <= MAX_HISTORY_MESSAGES:
        return messages
    trimmed = messages[-MAX_HISTORY_MESSAGES:]
    while trimmed and trimmed[0]["role"] != "user":
        trimmed = trimmed[1:]
    return trimmed


def _extract_data_blocks(messages: list[dict]) -> list[dict]:
    """Reconstruct data_blocks from conversation history for report retry."""
    tool_names: dict[str, str] = {}
    blocks: list[dict] = []
    for msg in messages:
        if msg.get("role") == "assistant":
            for call in msg.get("tool_calls") or []:
                tool_names[call["id"]] = call["function"]["name"]
        elif msg.get("role") == "tool":
            try:
                data = json.loads(msg.get("content", ""))
            except (json.JSONDecodeError, TypeError):
                continue
            if (isinstance(data, dict) and "error" not in data) or isinstance(data, list):
                blocks.append({"type": tool_names.get(msg.get("tool_call_id", ""), "unknown"), "data": data})
    return blocks


def _retry_delay_for(exc: Exception) -> float:
    """Honor the retry-after header on 429/5xx when present."""
    response = getattr(exc, "response", None)
    if response is not None:
        header = response.headers.get("retry-after")
        if header:
            try:
                return float(header)
            except ValueError:
                pass
    return RETRY_BACKOFF_SECONDS

# --- Tool definitions ---
# Each tool is a JSON schema describing what the function does, its parameters,
# and their types. The model reads these to decide which tool to call and with what
# arguments.

TOOLS = [
    {
        "name": "search_schools",
        "description": "Search colleges by name, state, or both. Returns up to 5 matches with tuition, net price by income, graduation rate, median debt, earnings, admission rate, retention rate, and loan repayment. Defaults to bachelor's-degree-granting schools. Use filter and sort params based on user's intake preferences.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "School name to search for (e.g. 'University of Florida', 'MIT'). Optional if state is provided.",
                },
                "state": {
                    "type": "string",
                    "description": "Two-letter US state code (e.g. 'FL', 'CA'). Optional if name is provided.",
                },
                "ownership": {
                    "type": "string",
                    "enum": ["public", "private"],
                    "description": "Filter by school type. Omit to include both.",
                },
                "max_net_price": {
                    "type": "integer",
                    "description": "Maximum annual net price after aid. Omit for no limit.",
                },
                "size": {
                    "type": "string",
                    "enum": ["small", "medium", "large"],
                    "description": "Filter by student body size: small (<5k), medium (5k-15k), large (15k+). Omit for no preference.",
                },
                "sort_by": {
                    "type": "string",
                    "enum": ["earnings", "graduation_rate", "net_price", "median_debt", "admission_rate", "retention_rate", "loan_repayment"],
                    "description": "How to rank results. earnings=highest first, graduation_rate=highest first, retention_rate=highest first, loan_repayment=highest first, net_price=lowest first, median_debt=lowest first, admission_rate=lowest first.",
                },
                "degree_type": {
                    "type": "string",
                    "enum": ["certificate", "associate", "bachelor", "graduate"],
                    "description": "Filter by predominant degree awarded. Defaults to 'bachelor'. Use 'certificate' or 'associate' for trade/vocational schools. Omit or pass null for no filter.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_school_programs",
        "description": "Get per-program earnings at a specific school. Returns median earnings 1 year and 4 years after graduation for each program offered, filtered optionally by program name. Requires a school_id from search_schools results. Use this to answer 'What do CS graduates from UF actually earn?' or to compare the same program across schools.",
        "input_schema": {
            "type": "object",
            "properties": {
                "school_id": {
                    "type": "integer",
                    "description": "The school's College Scorecard ID (from search_schools results)",
                },
                "program_search": {
                    "type": "string",
                    "description": "Optional: filter programs by name (e.g. 'computer', 'nursing'). Omit to get all programs with earnings data.",
                },
            },
            "required": ["school_id"],
        },
    },
    {
        "name": "search_occupations",
        "description": "Search occupations by keyword via O*NET. Returns up to 10 matched occupations with SOC code, bright outlook status, typical education years, and BLS annual salary when available. Use this when the user names a career or occupation to match it to real SOC codes and pull education/salary data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "Occupation or career keyword to search (e.g. 'pharmacist', 'electrician', 'software developer')",
                }
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "compare_education_paths",
        "description": "Compare working now against school for one occupation. Returns rows for a high school diploma, cashier, electrician, the national bachelor's median, and the given occupation: years of school, median student debt, median salary, and precomputed gaps vs a bachelor's. Adds a row with the user's own tuition and salary when they gave any. All figures are computed; use them as given. Requires an occupation_code (SOC) from search_occupations or intake.",
        "input_schema": {
            "type": "object",
            "properties": {
                "occupation_code": {
                    "type": "string",
                    "description": "SOC code of the occupation to compare (e.g. '23-1011')",
                }
            },
            "required": ["occupation_code"],
        },
    },
]

# The same tools in the OpenAI function-calling format.
OPENAI_TOOLS = [
    {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
    for t in TOOLS
]

_TOOL_PROGRESS = {
    "search_occupations": "Searching occupations…",
    "search_schools": "Looking up schools…",
    "get_school_programs": "Pulling program earnings…",
    "compare_education_paths": "Comparing education paths…",
}

TOOL_DISPATCH = {
    "search_occupations": lambda args: search_occupations(args["keyword"]),
    "search_schools": lambda args: search_schools(
        args.get("name"), args.get("state"), args.get("ownership"),
        args.get("max_net_price"), args.get("size"), args.get("sort_by"),
        args.get("degree_type", "bachelor"),
    ),
    "get_school_programs": lambda args: get_school_programs(args["school_id"], args.get("program_search")),
}


def _compare_education_paths(occupation_code: str, user_numbers: dict) -> dict:
    options = path1_options(occupation_code, user_numbers)
    if len(options) < 5:
        return {"error": f"No salary or education data for occupation_code {occupation_code!r}"}
    return {"occupation_code": occupation_code, "options": options}


def _dispatch_for(user_numbers: dict) -> dict:
    """Tool functions for one run. Each result carries its option rows
    (options.py). compare_education_paths takes the user's numbers from intake,
    not from the model, so the model never copies them."""
    tools = {
        **TOOL_DISPATCH,
        "compare_education_paths": lambda args: _compare_education_paths(args["occupation_code"], user_numbers),
    }
    return {name: (lambda args, name=name, func=func: with_rows(name, args, func(args))) for name, func in tools.items()}


SYSTEM_PROMPT = """You gather data for a college and career report; a separate step writes it. Tool results include "options": rows the report can compare. Gather the ones this person's question needs. Call independent tools together; if a search finds nothing, try other keywords. When done, reply with one short sentence.

Questions by intake path_type:
- path1: college vs a trade vs working now, for their occupation (use occupation_code from intake when present).
- path2: how the schools they named, or schools in their location, compare.
- path3: how the programs they named at their school compare, and the occupations they lead to.
- path4: how the careers they named compare, with their current job unless compare_to_current is "no".
- path5: how to get from their current role to their target career.
"""


def _parse_json_response(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    try:
        # raw_decode tolerates stray text after the JSON object.
        parsed, _ = json.JSONDecoder().raw_decode(text[text.find("{"):])
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError as exc:
        logger.error(
            "Report generation returned invalid JSON (%s): ...%s",
            exc, text[max(0, exc.pos - 200):exc.pos + 200],
        )
        return None


def _chosen_occupation_code(intake_answers: dict, data_blocks: list[dict]) -> str | None:
    """The occupation the agent compared on path1 (evals/inputs.py checks it)."""
    for block in reversed(data_blocks):
        if block.get("type") == "compare_education_paths" and isinstance(block.get("data"), dict):
            return block["data"].get("occupation_code")
    return None


def _progress(message: str, stage: str, percent: float, **extra) -> dict:
    return {"event": "progress", "message": message, "stage": stage, "percent": round(percent), **extra}


def build_report_input(intake_answers: dict, data_blocks: list[dict]) -> tuple[dict, list[dict]]:
    """Everything the report model receives: the intake answers, every option
    row gathered, and the gaps between them. Raw tool results stay out, so the
    only numbers the model sees are the ones code renders."""
    rows = candidate_rows(intake_answers, data_blocks)
    allowed = allowed_metrics(intake_answers)
    if allowed is not None:
        # Only the metrics the user chose reach the model, so its text can't
        # cite one the report doesn't show.
        rows = [{**r, "metrics": {k: v for k, v in r["metrics"].items() if k in allowed}} if "metrics" in r else r
                for r in rows]
    content = {"intake_answers": intake_answers, "rows": rows, "gaps": pairwise_gaps(rows)}
    return content, rows


async def resolve_user_numbers(intake_answers: dict | None) -> dict:
    """Numbers the user typed (path1 "specific") as structured fields."""
    if not intake_answers or intake_answers.get("data_source") != "specific":
        return {}
    try:
        # Confirmed by the user at intake; extract again only if missing.
        user_numbers = json.loads(intake_answers.get("user_numbers") or "{}")
    except json.JSONDecodeError:
        user_numbers = {}
    if not user_numbers:
        user_numbers = await extract_user_numbers(client, MODEL, intake_answers.get("specific_numbers") or "") or {}
    return user_numbers


async def prepare_report_input(intake_answers: dict, data_blocks: list[dict], agent_text: str = "") -> tuple[dict, list[dict]]:
    """Builds the report input. evals/inputs.py checks this directly."""
    return await asyncio.to_thread(build_report_input, intake_answers, data_blocks)


async def generate_report_stream(
    intake_answers: dict,
    data_blocks: list[dict],
    agent_text: str,
):
    """Async generator: yields progress events while the report streams, then
    a final {"event": "report", "report": {"summary": ..., "html": ...}}."""
    logger.info(
        "generate_report: %d data_blocks, intake_keys=%s",
        len(data_blocks), list(intake_answers.keys()),
    )
    content, _rows = await prepare_report_input(intake_answers, data_blocks, agent_text)
    async for event in write_report(content, agent_text):
        yield event


async def write_report(content: dict, agent_text: str):
    """Report generation alone: writes and renders the report from a prepared
    input (prepare_report_input). evals/report_eval.py calls this with fixed inputs."""
    user_content = json.dumps(content, default=_json_default)

    yield _progress("Writing your report…", "writing", GATHERING_END)
    t0 = time.perf_counter()
    chars = 0
    last_percent = GATHERING_END
    parts: list[str] = []
    usage, finish_reason = None, None
    rows = content["rows"]
    stream = await client.chat.completions.create(
        model=REPORT_MODEL,
        max_tokens=REPORT_SPEC_MAX_TOKENS,
        messages=[
            {"role": "system", "content": REPORT_PROMPT},
            {"role": "user", "content": user_content},
        ],
        # Numbers come from code, so variety only adds risk (e.g. garbled figures).
        temperature=0,
        response_format={"type": "json_schema", "json_schema": {"name": "report", "schema": report_schema(rows, content.get("intake_answers"))}},
        stream=True,
        stream_options={"include_usage": True},
    )
    async for chunk in stream:
        if chunk.usage:
            usage = chunk.usage
        if not chunk.choices:
            continue
        finish_reason = chunk.choices[0].finish_reason or finish_reason
        delta = chunk.choices[0].delta.content or ""
        parts.append(delta)
        chars += len(delta)
        # ~4 chars per token is close enough for a progress estimate.
        fraction = min(1.0, (chars / 4) / REPORT_EXPECTED_TOKENS)
        percent = GATHERING_END + (WRITING_END - GATHERING_END) * fraction
        if percent - last_percent >= 3:
            last_percent = percent
            yield _progress("Writing your report…", "writing", percent)
    elapsed = time.perf_counter() - t0
    out_tokens = usage.completion_tokens if usage else 0
    logger.info(
        "[timing] report LLM call: %.2fs, input_tokens=%d, output_tokens=%d (%.0f tok/s), finish_reason=%s",
        elapsed, usage.prompt_tokens if usage else 0, out_tokens,
        out_tokens / elapsed if elapsed else 0, finish_reason,
    )

    text = "".join(parts)
    logger.info("Report response size: %d bytes, finish_reason=%s", len(text), finish_reason)
    parsed = _parse_json_response(text)
    if parsed is None:
        yield {"event": "report", "report": {"summary": agent_text, "html": ""}}
        return

    yield _progress("Finalizing your report…", "rendering", RENDERING_PERCENT)
    # The headline doubles as the chat reply.
    reply = parsed.get("headline") or agent_text
    parsed = {"summary": reply, "html": render_report(parsed, rows, content.get("intake_answers"))}

    logger.info("Report parsed OK: summary=%d chars, html=%d chars", len(parsed.get("summary", "")), len(parsed.get("html", "")))
    yield {"event": "report", "report": parsed}


async def generate_report(
    intake_answers: dict,
    data_blocks: list[dict],
    agent_text: str,
) -> dict:
    """Non-streaming wrapper for callers that don't show progress (retry-report)."""
    report = {"summary": agent_text, "html": ""}
    async for event in generate_report_stream(intake_answers, data_blocks, agent_text):
        if event["event"] == "report":
            report = event["report"]
    return report


async def _call_model(messages: list[dict]):
    """
    Call the model with one retry on transient errors.
    Retriable: rate limit, connection error, 5xx. Non-retriable errors
    (auth, bad request, no credits) surface immediately so the caller sees the real cause.
    """
    last_exc: Exception | None = None
    for attempt in range(MAX_API_RETRIES + 1):
        try:
            return await client.chat.completions.create(
                model=MODEL,
                max_tokens=1024,
                messages=[{"role": "system", "content": SYSTEM_PROMPT}, *messages],
                tools=OPENAI_TOOLS,
            )
        except (openai.APIConnectionError, openai.RateLimitError) as exc:
            last_exc = exc
            logger.warning("Model API transient error (attempt %d): %s", attempt + 1, exc)
        except openai.APIStatusError as exc:
            if exc.status_code and 500 <= exc.status_code < 600:
                last_exc = exc
                logger.warning("Model API 5xx (attempt %d): %s", attempt + 1, exc)
            else:
                raise
        if attempt < MAX_API_RETRIES:
            await asyncio.sleep(_retry_delay_for(last_exc))
    if last_exc is None:
        raise RuntimeError("_call_model exited retry loop without a response or exception")
    raise last_exc


async def run_agent_stream(
    user_message: str,
    conversation_history: list[dict] | None = None,
    intake_answers: dict | None = None,
):
    """Async generator yielding progress events then a final result.

    Event shapes:
      {"event": "progress", "message": "Searching occupations…",
       "stage": "gathering" | "writing" | "rendering", "percent": 0-100}
      {"event": "complete", "response": "...", "report_html": "...", "conversation_history": [...]}
    """
    messages = list(conversation_history) if conversation_history else []
    messages.append({"role": "user", "content": user_message})
    messages = _trim_history(messages)
    data_blocks: list[dict] = []

    run_start = time.perf_counter()
    llm_total = 0.0
    tools_total = 0.0
    report_total = 0.0
    # Steps completed while gathering (agent calls + tools). Total is unknown
    # up front, so each step advances a fixed amount, capped at GATHERING_END.
    gather_steps = 0

    def gathering(message: str) -> dict:
        percent = min(GATHERING_END, GATHERING_START + GATHERING_STEP * gather_steps)
        return _progress(message, "gathering", percent)

    text_response: str | None = None
    agent_calls = 0
    dispatch = _dispatch_for(await resolve_user_numbers(intake_answers))

    for iteration in range(MAX_TOOL_ITERATIONS):
        agent_calls = iteration + 1
        try:
            yield gathering("Understanding your question…" if iteration == 0 else "Reviewing what I found…")
            t0 = time.perf_counter()
            response = await _call_model(messages)
            llm_total += time.perf_counter() - t0
            gather_steps += 1
        except openai.APIError as exc:
            logger.error("Model API failed after retries: %s", exc)
            yield {
                "event": "complete",
                "response": "Sorry, I'm having trouble right now. Please try again in a moment.",
                "data_blocks": [],
                "conversation_history": messages,
            }
            return

        message = response.choices[0].message
        if message.tool_calls:
            # Keep the message exactly as returned: providers attach fields that
            # must be sent back with tool calls (Gemini's thought signatures,
            # other providers' reasoning fields), and rebuilding it drops them.
            messages.append(message.model_dump(exclude_none=True))

            for call in message.tool_calls:
                tool_name = call.function.name
                tool_id = call.id

                progress_message = _TOOL_PROGRESS.get(tool_name, f"Running {tool_name}…")
                yield gathering(progress_message)

                func = dispatch.get(tool_name)
                if not func:
                    messages.append({"role": "tool", "tool_call_id": tool_id, "content": f"Error: unknown tool '{tool_name}'"})
                    continue

                try:
                    tool_input = json.loads(call.function.arguments or "{}")
                    t0 = time.perf_counter()
                    result = await asyncio.to_thread(func, tool_input)
                    tools_total += time.perf_counter() - t0
                    messages.append({"role": "tool", "tool_call_id": tool_id, "content": json.dumps(result, default=_json_default)})
                    if not (isinstance(result, dict) and "error" in result):
                        data_blocks.append({"type": tool_name, "data": result})
                    gather_steps += 1
                    # Same message, bar advances.
                    yield gathering(progress_message)
                except Exception as exc:
                    logger.exception("Tool %s failed", tool_name)
                    messages.append({"role": "tool", "tool_call_id": tool_id, "content": f"Error executing {tool_name}: {exc}"})

        else:
            text_response = message.content or ""
            messages.append(message.model_dump(exclude_none=True))
            break

    if text_response is None:
        logger.warning("Agent hit MAX_TOOL_ITERATIONS=%d without finishing", MAX_TOOL_ITERATIONS)
        yield {
            "event": "complete",
            "response": "I got stuck working through that. Try rephrasing your question or asking something simpler.",
            "report_html": "",
            "conversation_history": messages,
        }
        return

    report_html = ""
    report_status = "skipped"
    logger.info("Agent done. data_blocks=%d, intake_answers=%s", len(data_blocks), bool(intake_answers))
    if data_blocks and intake_answers:
        report_status = "failed"
        try:
            t0 = time.perf_counter()
            report = {}
            async for event in generate_report_stream(intake_answers, data_blocks, text_response):
                if event["event"] == "report":
                    report = event["report"]
                else:
                    yield event
            report_total = time.perf_counter() - t0
            text_response = report.get("summary", text_response)
            report_html = report.get("html", "")
            if report_html:
                report_status = "success"
                logger.info("Report OK: %d bytes HTML", len(report_html))
            else:
                logger.warning("Report returned empty HTML")
        except Exception as exc:
            logger.exception("Report generation failed: %s", exc)
    else:
        logger.info("Skipping report: data_blocks=%d, intake_answers=%s", len(data_blocks), intake_answers is not None)

    logger.info(
        "[timing] run total: %.2fs (agent LLM: %.2fs over %d calls, tools: %.2fs, report: %.2fs)",
        time.perf_counter() - run_start, llm_total, agent_calls, tools_total, report_total,
    )
    yield {
        "event": "complete",
        "response": text_response,
        "report_html": report_html,
        "report_status": report_status,
        "conversation_history": messages,
    }

