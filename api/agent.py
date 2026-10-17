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
from alerts import send_alert
from db import (
    schools_by_ids,
    search_schools,
    get_school_programs,
    search_occupations,
)
from career_cost import CASHIER_CODE, ELECTRICIAN_CODE, path1_options
from options import (RANK_SORT, allowed_metrics, candidate_rows, check_rows, pairwise_gaps, path3_options, path4_options,
                     path3_gaps, path5_gaps, path5_options, rank_choice, report_rows, with_rows)
from user_numbers import extract_user_numbers
from report import REPORT_PROMPT, render_report, report_schema
from report_checks import number_problems, report_facts, sentence_ok, split_sentences

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
    {
        "name": "compare_programs",
        "description": "Compare programs at one school. Returns rows for the programs the user confirmed in intake (or the school's top programs if they weren't sure): graduates' earnings and median debt, and the occupations each program leads to with BLS median salary. All figures are computed; use them as given. Requires the school_id from intake or search_schools.",
        "input_schema": {
            "type": "object",
            "properties": {
                "school_id": {
                    "type": "integer",
                    "description": "The school's College Scorecard ID",
                }
            },
            "required": ["school_id"],
        },
    },
    {
        "name": "get_schools",
        "description": "Get schools by their College Scorecard IDs, with the same figures as search_schools. Use it for schools the user confirmed in intake (school_picks).",
        "input_schema": {
            "type": "object",
            "properties": {
                "school_ids": {"type": "array", "items": {"type": "integer"}, "description": "College Scorecard IDs"},
            },
            "required": ["school_ids"],
        },
    },
    {
        "name": "compare_careers",
        "description": "Compare the careers the user confirmed in intake, plus their current job if they included it. Returns a row per career with years of school, median student debt, and BLS median salary. All figures are computed; use them as given. Takes no arguments: the careers come from intake.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "rank_schools_for_career",
        "description": "Rank schools for the career the user confirmed in intake, on the program (fields of study and degree level), location, limits, and ranking they chose. Returns the top schools, one row each with graduates' pay 1 and 4 years after graduating and median debt, plus the career's BLS median and the program's national spread. All figures are computed; use them as given. Takes no arguments: everything comes from intake.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
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
    "get_schools": "Looking up schools…",
    "get_school_programs": "Pulling program earnings…",
    "compare_education_paths": "Comparing education paths…",
    "compare_programs": "Comparing programs…",
    "compare_careers": "Comparing careers…",
    "rank_schools_for_career": "Ranking schools…",
}

TOOL_DISPATCH = {
    "search_occupations": lambda args: search_occupations(args["keyword"]),
    "search_schools": lambda args: search_schools(
        args.get("name"), args.get("state"), args.get("ownership"),
        args.get("max_net_price"), args.get("size"), args.get("sort_by"),
        args.get("degree_type", "bachelor"),
    ),
    "get_school_programs": lambda args: get_school_programs(args["school_id"], args.get("program_search")),
    "get_schools": lambda args: schools_by_ids(args["school_ids"]),
}


def _compare_education_paths(occupation_code: str, user_numbers: dict) -> dict:
    options = path1_options(occupation_code, user_numbers)
    expected = ["baseline:hs", f"occ:{CASHIER_CODE}", f"occ:{ELECTRICIAN_CODE}", "baseline:bachelors", f"occ:{occupation_code}"]
    missing = [i for i in expected if i not in {o["option_id"] for o in options}]
    if missing:
        return {"error": f"No salary or education data for {', '.join(missing)}"}
    return {"occupation_code": occupation_code, "options": options}


def _program_list(intake_answers: dict) -> list[str] | None:
    """The program titles the user confirmed (path3); [] = not sure, None = none confirmed."""
    try:
        programs = json.loads(intake_answers.get("program_list") or "null")
    except json.JSONDecodeError:
        return None
    return [p for p in programs if isinstance(p, str)] if isinstance(programs, list) else None


def _compare_programs(school_id, intake_answers: dict) -> dict:
    # The confirmed school wins over the model's argument.
    confirmed = str(intake_answers.get("school_id") or "")
    school_id = int(confirmed) if confirmed.isdigit() else int(school_id)
    result = path3_options(school_id, _program_list(intake_answers), intake_answers.get("program_priority"))
    if "error" not in result and not any(o["option_id"].startswith("program:") for o in result["options"]):
        return {"error": f"No program earnings data at school_id {school_id}", **result}
    return result


def _dispatch_for(user_numbers: dict, intake_answers: dict | None = None) -> dict:
    """Tool functions for one run. Each result carries its option rows
    (options.py). compare_education_paths and compare_programs take the user's
    numbers and programs from intake, not from the model, so the model never
    copies them."""
    tools = {
        **TOOL_DISPATCH,
        "compare_education_paths": lambda args: _compare_education_paths(args["occupation_code"], user_numbers),
        "compare_programs": lambda args: _compare_programs(args["school_id"], intake_answers or {}),
        "compare_careers": lambda args: path4_options(intake_answers or {}),
        "rank_schools_for_career": lambda args: path5_options(intake_answers or {}),
    }
    return {name: (lambda args, name=name, func=func: with_rows(name, args, func(args))) for name, func in tools.items()}


SYSTEM_PROMPT = """You gather data for a college and career report; a separate step writes it. Tool results include "options": rows the report can compare. Gather the ones this person's question needs. Call independent tools together; if a search finds nothing, try other keywords. When done, reply with one short sentence.

The user confirmed the occupations (with SOC codes), schools (with school_id), and programs in their intake. Use exactly those: search an occupation by its confirmed title and take the result with that SOC code, and pass a confirmed school_id straight to the tool that takes it.

Questions by intake path_type:
- path1: college vs a trade vs working now, for their occupation (use occupation_code from intake when present).
- path2: how the schools they named, or schools in their location, compare.
- path3: call compare_programs with the school_id from intake; it returns the programs they confirmed and the occupations each leads to. Nothing else is needed.
- path4: call compare_careers; it returns the careers they confirmed and their current job if included. Nothing else is needed.
- path5: call rank_schools_for_career; it returns the top schools for their target career on the program, location, and limits they chose. Nothing else is needed.
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
    """Everything the report model receives: the intake answers, the option
    rows the report shows (options.report_rows), and the gaps between them. Raw tool results stay out, so the
    only numbers the model sees are the ones code renders."""
    rows = report_rows(intake_answers, candidate_rows(intake_answers, data_blocks))
    allowed = allowed_metrics(intake_answers)
    if allowed is not None:
        # Only the metrics the user chose reach the model, so its text can't
        # cite one the report doesn't show.
        rows = [{**r, "metrics": {k: v for k, v in r["metrics"].items() if k in allowed}} if "metrics" in r else r
                for r in rows]
    content = {"intake_answers": intake_answers, "rows": rows}
    ranked = next((b["data"] for b in data_blocks if b.get("type") == "rank_schools_for_career"
                   and isinstance(b.get("data"), dict) and "options" in b["data"]), None)
    if ranked:
        # path5: the career and the program's national spread, which the report compares the schools with.
        content["career"] = {k: ranked[k] for k in ("occupation", "rank_by", "national_spread")}
        content["gaps"], content["median_gaps"] = path5_gaps(rows, ranked.get("national_spread") or {})
    elif intake_answers.get("path_type") == "path3":
        content["gaps"] = path3_gaps(rows)
    else:
        content["gaps"] = pairwise_gaps(rows)
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


async def _report_call(content: dict, show_progress: bool):
    """One report model call. Yields progress events while it streams (when
    show_progress), then {"event": "text", "text": ...}."""
    t0 = time.perf_counter()
    chars = 0
    last_percent = GATHERING_END
    parts: list[str] = []
    usage, finish_reason = None, None
    stream = await client.chat.completions.create(
        model=REPORT_MODEL,
        max_tokens=REPORT_SPEC_MAX_TOKENS,
        messages=[
            {"role": "system", "content": REPORT_PROMPT},
            {"role": "user", "content": json.dumps(content, default=_json_default)},
        ],
        # Numbers come from code, so variety only adds risk (e.g. garbled figures).
        temperature=0,
        response_format={"type": "json_schema", "json_schema": {"name": "report", "schema": report_schema(content["rows"], content.get("intake_answers"))}},
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
        if show_progress and percent - last_percent >= 3:
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
    yield {"event": "text", "text": text}


def _checked(spec: dict, content: dict, agent_text: str) -> tuple[dict, dict[str, list[str]]]:
    """Renders a report spec and runs the number checks (report_checks.py) on
    it. Returns ({"summary", "html"}, problems)."""
    # The headline doubles as the chat reply.
    reply = spec.get("headline") or agent_text
    report_html = render_report(spec, content["rows"], content.get("intake_answers"), content.get("career"))
    return {"summary": reply, "html": report_html}, number_problems(reply, report_html)


def _supported_only(spec: dict, report_html: str) -> dict:
    """The spec without the sentences whose figures the checks reject. The
    tables and charts the checks compare with are code's, so dropping text
    doesn't change them. A headline left empty takes the first remaining bullet."""
    facts = report_facts(report_html)

    def keep(text) -> str:
        return " ".join(s for s in split_sentences(text if isinstance(text, str) else "") if sentence_ok(s, facts))

    sections = [
        {**sec, "bullets": [b for b in (keep(b) for b in sec.get("bullets") or []) if b],
         "what_it_means": keep(sec.get("what_it_means"))}
        for sec in spec.get("sections") or [] if isinstance(sec, dict)
    ]
    headline = keep(spec.get("headline")) or next((b for sec in sections for b in sec["bullets"]), "")
    return {**spec, "headline": headline, "sections": sections,
            "limitations": [x for x in (keep(x) for x in spec.get("limitations") or []) if x]}


async def write_report(content: dict, agent_text: str, check_numbers: bool = True):
    """Report generation alone: writes and renders the report from a prepared
    input (prepare_report_input). evals/report_eval.py calls this with fixed
    inputs and check_numbers=False, to score the model's own text.

    With check_numbers, a report whose text has a figure the data doesn't
    support (report_checks.py) is written once more; if the second one fails
    too, the failing sentences are dropped from the one with fewer problems."""
    yield _progress("Writing your report…", "writing", GATHERING_END)
    text = ""
    async for event in _report_call(content, show_progress=True):
        if event["event"] == "text":
            text = event["text"]
        else:
            yield event
    parsed = _parse_json_response(text)
    if parsed is None:
        yield {"event": "report", "report": {"summary": agent_text, "html": ""}}
        return

    yield _progress("Finalizing your report…", "rendering", RENDERING_PERCENT)
    report, problems = _checked(parsed, content, agent_text)
    if check_numbers and any(problems.values()):
        logger.warning("Report failed number checks, writing it again: %s", problems)
        yield _progress("Double-checking the figures…", "rendering", RENDERING_PERCENT)
        attempts = [(parsed, report, problems)]
        retried = None
        try:
            async for event in _report_call(content, show_progress=False):
                retried = _parse_json_response(event["text"])
            if retried is not None:
                attempts.append((retried, *_checked(retried, content, agent_text)))
        except Exception:
            logger.exception("Report retry after failed number checks raised")
        spec, report, problems = min(attempts, key=lambda a: sum(len(p) for p in a[2].values()))
        if any(problems.values()):
            send_alert("Report failed number checks twice; dropped sentences", {
                "problems": problems, "intake_answers": content.get("intake_answers")})
            report, problems = _checked(_supported_only(spec, report["html"]), content, agent_text)
            if any(problems.values()):
                logger.error("Report still fails number checks after dropping sentences: %s", problems)

    logger.info("Report parsed OK: summary=%d chars, html=%d chars", len(report["summary"]), len(report["html"]))
    yield {"event": "report", "report": report}


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


# Chat reply for a run gathered in code, until the report's headline replaces it.
PLANNED_REPLY = "Here's what I found."


def _planned_calls(intake_answers: dict | None) -> list[tuple[str, dict]] | None:
    """The first turn's tool calls when intake already confirmed everything
    they take, else None (the model gathers). path1: the confirmed occupation;
    path2: the schools picked, or a search per state ranked by the user's
    choice; path3-5: the one tool that reads intake."""
    answers = intake_answers or {}
    path = answers.get("path_type")
    if path == "path1" and answers.get("occupation_code"):
        return [("compare_education_paths", {"occupation_code": answers["occupation_code"]})]
    if path == "path2":
        picks = [int(p) for p in (answers.get("school_picks") or "").split("|") if p.isdigit()]
        if picks:
            return [("get_schools", {"school_ids": picks})]
        states = [s.strip() for s in (answers.get("target_states") or "").split(",") if s.strip()]
        sort = RANK_SORT.get(rank_choice(answers))
        return [("search_schools", {"state": s, **({"sort_by": sort} if sort else {})}) for s in states] or None
    if path == "path3" and str(answers.get("school_id") or "").isdigit() and _program_list(answers) is not None:
        return [("compare_programs", {"school_id": int(answers["school_id"])})]
    if path == "path4" and answers.get("career_matches"):
        return [("compare_careers", {})]
    if path == "path5" and answers.get("career_programs"):
        return [("rank_schools_for_career", {})]
    return None


def _tools_for(intake_answers: dict | None, first_turn: bool) -> list[dict]:
    """Tools the model may call. The first path3 turn, with confirmed programs
    but no school_id for code to gather with (_planned_calls), needs only
    compare_programs; with other tools on offer, the model went looking for
    programs that have no earnings data. Follow-ups get every tool."""
    answers = intake_answers or {}
    if first_turn and answers.get("path_type") == "path3" and _program_list(answers) is not None:
        return [t for t in OPENAI_TOOLS if t["function"]["name"] == "compare_programs"]
    return OPENAI_TOOLS


async def _call_model(messages: list[dict], tools: list[dict] = OPENAI_TOOLS):
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
                tools=tools,
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
    first_turn = not messages
    tools = _tools_for(intake_answers, first_turn=first_turn)
    planned = _planned_calls(intake_answers) if first_turn else None
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
    tool_errors: list[dict] = []
    dispatch = _dispatch_for(await resolve_user_numbers(intake_answers), intake_answers)

    async def run_tools(calls: list[tuple[str, str, str]]):
        """Runs (id, name, JSON arguments) tool calls, appending each result to
        messages and data_blocks; yields progress."""
        nonlocal tools_total, gather_steps
        for tool_id, tool_name, arguments in calls:
            progress_message = _TOOL_PROGRESS.get(tool_name, f"Running {tool_name}…")
            yield gathering(progress_message)

            func = dispatch.get(tool_name)
            if not func:
                messages.append({"role": "tool", "tool_call_id": tool_id, "content": f"Error: unknown tool '{tool_name}'"})
                continue

            try:
                tool_input = json.loads(arguments or "{}")
                t0 = time.perf_counter()
                result = await asyncio.to_thread(func, tool_input)
                tools_total += time.perf_counter() - t0
                messages.append({"role": "tool", "tool_call_id": tool_id, "content": json.dumps(result, default=_json_default)})
                if isinstance(result, dict) and "error" in result:
                    tool_errors.append({"tool": tool_name, "args": tool_input, "error": result["error"],
                                        **({"no_match": True} if result.get("no_match") else {})})
                elif isinstance(result, dict) and "options" in result and not result["options"]:
                    # Results came back, but none has the data a comparison needs.
                    tool_errors.append({"tool": tool_name, "args": tool_input, "error": "No comparable rows"})
                else:
                    data_blocks.append({"type": tool_name, "data": result})
                gather_steps += 1
                # Same message, bar advances.
                yield gathering(progress_message)
            except Exception as exc:
                logger.exception("Tool %s failed", tool_name)
                tool_errors.append({"tool": tool_name, "args": arguments, "error": repr(exc)})
                send_alert(f"Tool {tool_name} raised", {"args": arguments, "error": repr(exc),
                                                       "intake_answers": intake_answers})
                messages.append({"role": "tool", "tool_call_id": tool_id, "content": f"Error executing {tool_name}: {exc}"})

    if planned:
        # Intake already fixed what to gather, so code makes the calls. They go
        # into the history as the model's would, so a report retry and the
        # model on a follow-up see them.
        calls = [(f"intake_{i}", name, json.dumps(args)) for i, (name, args) in enumerate(planned)]
        messages.append({"role": "assistant", "content": "", "tool_calls": [
            {"id": i, "type": "function", "function": {"name": n, "arguments": a}} for i, n, a in calls]})
        async for event in run_tools(calls):
            yield event
        text_response = PLANNED_REPLY
        messages.append({"role": "assistant", "content": text_response})

    for iteration in range(0 if planned else MAX_TOOL_ITERATIONS):
        agent_calls = iteration + 1
        try:
            yield gathering("Understanding your question…" if iteration == 0 else "Reviewing what I found…")
            t0 = time.perf_counter()
            response = await _call_model(messages, tools)
            llm_total += time.perf_counter() - t0
            gather_steps += 1
        except openai.APIError as exc:
            send_alert("Model API failed after retries", {"error": repr(exc), "intake_answers": intake_answers})
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
            async for event in run_tools([(c.id, c.function.name, c.function.arguments) for c in message.tool_calls]):
                yield event
        else:
            text_response = message.content or ""
            messages.append(message.model_dump(exclude_none=True))
            break

    if text_response is None:
        send_alert("Agent hit MAX_TOOL_ITERATIONS", {"limit": MAX_TOOL_ITERATIONS, "tool_errors": tool_errors,
                                                     "intake_answers": intake_answers})
        yield {
            "event": "complete",
            "response": "I got stuck working through that. Try rephrasing your question or asking something simpler.",
            "report_html": "",
            "conversation_history": messages,
        }
        return

    if data_blocks and not first_turn:
        # A follow-up adds to what earlier turns gathered (another school, say),
        # so its report compares everything gathered so far.
        data_blocks = _extract_data_blocks(messages)

    if intake_answers:
        required, expected = check_rows(intake_answers, data_blocks)
        details = {"path": intake_answers.get("path_type"), "tool_errors": tool_errors, "intake_answers": intake_answers}
        no_match = next((e["error"] for e in tool_errors if e.get("no_match")), None)
        if required and no_match:
            # The user's filters left nothing to rank: an answer, not a failure.
            yield {
                "event": "complete",
                "response": no_match,
                "report_html": "",
                "report_status": "skipped",
                "tool_errors": tool_errors,
                "conversation_history": messages,
            }
            return
        if required:
            send_alert(f"Missing required data ({intake_answers.get('path_type')})", {"missing": required, **details})
            yield {
                "event": "complete",
                "response": f"I couldn't get the data this comparison needs: {'; '.join(required)}. "
                            "The problem has been reported. Please try again later.",
                "report_html": "",
                "report_status": "error",
                "tool_errors": tool_errors,
                "conversation_history": messages,
            }
            return
        if expected:
            send_alert(f"Missing expected data ({intake_answers.get('path_type')})", {"missing": expected, **details})

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
                send_alert("Report returned empty HTML", {"intake_answers": intake_answers})
        except Exception as exc:
            logger.exception("Report generation failed: %s", exc)
            send_alert("Report generation failed", {"error": repr(exc), "intake_answers": intake_answers})
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
        "tool_errors": tool_errors,
        "conversation_history": messages,
    }

