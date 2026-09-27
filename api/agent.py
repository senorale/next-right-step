"""
Agent module: defines tools and runs the Claude tool-use loop.

How it works:
1. We define "tools" — JSON schemas that tell Claude what functions it can call.
2. We send the user's message to Claude along with the tool definitions.
3. Claude either responds directly OR returns a "tool_use" block asking to call
   a function with specific arguments.
4. We execute that function locally, send the result back to Claude, and let it
   decide whether to respond or call another tool.
5. This loop continues until Claude produces a final text response.
"""

import asyncio
import json
import logging
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from dotenv import load_dotenv
load_dotenv(dotenv_path="../.env")

import anthropic
from db import (
    find_majors_with_occupations,
    get_tuition_medians,
    run_sql,
    search_schools,
    get_school_programs,
    search_occupations,
)

logger = logging.getLogger(__name__)

client = anthropic.AsyncAnthropic()
MODEL = "claude-haiku-4-5-20251001"
REPORT_MODEL = "claude-haiku-4-5-20251001"
REPORT_MAX_TOKENS = 16384

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
    """Keep the last MAX_HISTORY_MESSAGES, but never start on a dangling
    tool_result or assistant tool_use — Anthropic requires tool_use/tool_result
    to be paired, so drop leading fragments until the first message is a
    plain user text turn."""
    if len(messages) <= MAX_HISTORY_MESSAGES:
        return messages
    trimmed = messages[-MAX_HISTORY_MESSAGES:]
    while trimmed:
        first = trimmed[0]
        content = first.get("content")
        is_tool_result = (
            first["role"] == "user"
            and isinstance(content, list)
            and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)
        )
        is_assistant_fragment = first["role"] == "assistant"
        if is_tool_result or is_assistant_fragment:
            trimmed = trimmed[1:]
        else:
            break
    return trimmed


def _extract_data_blocks(messages: list[dict]) -> list[dict]:
    """Reconstruct data_blocks from conversation history for report retry."""
    tool_names: dict[str, str] = {}
    blocks: list[dict] = []
    for msg in messages:
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue
        if msg["role"] == "assistant":
            for item in content:
                if isinstance(item, dict) and item.get("type") == "tool_use":
                    tool_names[item["id"]] = item["name"]
        elif msg["role"] == "user":
            for item in content:
                if not isinstance(item, dict) or item.get("type") != "tool_result":
                    continue
                if item.get("is_error"):
                    continue
                raw = item.get("content", "")
                try:
                    data = json.loads(raw) if isinstance(raw, str) else raw
                    if isinstance(data, dict) and "error" not in data:
                        tool_name = tool_names.get(item.get("tool_use_id", ""), "unknown")
                        blocks.append({"type": tool_name, "data": data})
                except (json.JSONDecodeError, TypeError):
                    pass
    return blocks


def _retry_delay_for(exc: Exception) -> float:
    """Honor Anthropic's retry-after header on 429/5xx when present."""
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
# and their types. Claude reads these to decide which tool to call and with what
# arguments.

TOOLS = [
    {
        "name": "find_majors",
        "description": "Search college majors by name and get all linked occupations with annual salaries and relevance scores in one call. Each result includes a major_id (UUID) you can use to build comparison links. Relevance: 1.0 = direct pipeline, 0.7 = common path, 0.4 = possible path. Salary data is from BLS May 2024. BLS caps reported salaries at $239,200/yr.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Partial or full major name to search for (e.g. 'computer', 'nursing', 'engineering')",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_tuition_medians",
        "description": "Get national median annual tuition costs by school type (public in-state, public out-of-state, private nonprofit). Includes sticker price, net price after aid, and full cost of attendance. Use this for general cost comparisons when no specific school is named.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "search_schools",
        "description": "Search colleges by name, state, or both. Returns up to 5 matches (graduation rate >= 70%) with tuition, net price by income, graduation rate, median debt, earnings, admission rate, retention rate, and loan repayment. Defaults to bachelor's-degree-granting schools. Use filter and sort params based on user's intake preferences.",
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
        "description": "Get per-program earnings at a specific school. Returns median earnings 1 year and 4 years after graduation for each program (major) offered, filtered optionally by major name. Requires a school_id from search_schools results. Use this to answer 'What do CS graduates from UF actually earn?' or to compare the same major across schools.",
        "input_schema": {
            "type": "object",
            "properties": {
                "school_id": {
                    "type": "integer",
                    "description": "The school's College Scorecard ID (from search_schools results)",
                },
                "major_search": {
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
        "name": "run_sql",
        "description": """Run a read-only SQL SELECT query against the database. Only SELECT statements are allowed. Results are capped at 50 rows.

Database schema (PostgreSQL, all table/column names are double-quoted):

"Major" (id UUID PK, name TEXT UNIQUE, created_at, updated_at)
  Sample: id='abc-123', name='Computer Science'

"OccupationCategory" (id UUID PK, name TEXT UNIQUE, occupation_code TEXT UNIQUE, created_at, updated_at)
  Sample: id='def-456', name='Computer and Mathematical Occupations', occupation_code='15-0000'

"OccupationSubCategory" (id UUID PK, name TEXT, occupation_code TEXT, annual_salary FLOAT, category_id UUID FK->OccupationCategory.id, typical_years_of_school FLOAT NULL, created_at, updated_at)
  Sample: id='ghi-789', name='Software Developers', occupation_code='15-1252', annual_salary=132270.0, typical_years_of_school=4.0

"MajorOccupation" (id UUID PK, major_id UUID FK->Major.id, occupation_id UUID FK->OccupationSubCategory.id, relevance FLOAT)
  Links majors to occupations. relevance: 1.0=direct pipeline, 0.7=common path, 0.4=possible path

"TuitionMedian" (id UUID PK, cohort TEXT UNIQUE, label TEXT, sticker_annual INT NULL, net_price_annual INT NULL, cost_of_attendance_annual INT NULL, sample_size INT, source TEXT, created_at, updated_at)
  Cohorts: public_in_state, public_out_of_state, private_nonprofit, all""",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A SQL SELECT query to run against the database",
                }
            },
            "required": ["query"],
        },
    },
]

_TOOL_PROGRESS = {
    "find_majors": ("Searching majors…", "Found matching majors"),
    "search_occupations": ("Searching occupations…", "Found matching occupations"),
    "search_schools": ("Looking up schools…", "Found schools"),
    "get_school_programs": ("Pulling program earnings…", "Got program data"),
    "get_tuition_medians": ("Getting tuition data…", "Got tuition data"),
    "run_sql": ("Querying database…", "Query complete"),
}

TOOL_DISPATCH = {
    "find_majors": lambda args: find_majors_with_occupations(args["query"]),
    "search_occupations": lambda args: search_occupations(args["keyword"]),
    "get_tuition_medians": lambda _args: get_tuition_medians(),
    "search_schools": lambda args: search_schools(
        args.get("name"), args.get("state"), args.get("ownership"),
        args.get("max_net_price"), args.get("size"), args.get("sort_by"),
        args.get("degree_type", "bachelor"),
    ),
    "get_school_programs": lambda args: get_school_programs(args["school_id"], args.get("major_search")),
    "run_sql": lambda args: run_sql(args["query"]),
}

SYSTEM_PROMPT = """You are a data-gathering agent for the "Should I Go?" college advisor app. Your job is to collect all relevant data for a user's situation by calling tools. A separate step will synthesize and present the data.

TOOLS:

1. find_majors(query) - Search majors by name. Returns linked occupations with BLS salaries, relevance scores, and major_id.
2. get_tuition_medians() - National median tuition by school type (public in-state, out-of-state, private).
3. search_schools(name, state, ownership, max_net_price, sort_by) - Search schools with filters. Only returns schools with graduation rate >= 70%. Use intake preferences as filter params.
4. get_school_programs(school_id, major_search?) - Per-program earnings at a specific school. Requires school_id from search_schools.
5. run_sql(query) - Read-only SQL for analytical questions the other tools can't answer.

DATA GATHERING BY SEGMENT:

Considering college:
- get_tuition_medians for cost baseline (ALWAYS call this)
- search_schools when they name schools or a state (use their school_type, budget, size, sort preferences as filters)
- find_majors for each field of interest
- get_school_programs for their target schools + majors
- run_sql for occupations with low typical_years_of_school

In college:
- find_majors for current major AND any alternatives mentioned
- get_tuition_medians (ALWAYS call this for financial analysis)
- get_school_programs for their school if named
- run_sql for occupation overlap, career option counts, weighted salary comparisons

Not in school:
- find_majors for their degree field
- run_sql for salary comparisons, education requirements across occupations
- get_school_programs if they name their school

RULES:

- Call ALL relevant tools for the user's situation in the first turn. Gather broadly.
- When a user mentions a major, call find_majors. When they name a school, call search_schools.
- To get program earnings, call search_schools first (for school_id), then get_school_programs.
- If find_majors returns no results, try broader search terms.
- BLS caps reported salaries at $239,200/yr.

RESPONSE:

After gathering data, respond with ONE sentence confirming what you found. Example: "I pulled data on 6 California schools, Biology and Pre-Med career paths, and national tuition benchmarks."

Do not narrate the data. Do not list numbers. Do not use markdown. A report will be generated separately from your tool results.
"""

REPORT_SYSTEM_PROMPT = """You generate HTML reports for a college advisor app. You receive raw data from tool calls and the user's intake profile.

Generate a single self-contained HTML page that presents the findings as a clear, personalized report.

HTML RULES:
- All CSS in a single <style> tag. No external stylesheets except Google Fonts (one clean font).
- Charts as inline SVG: horizontal bar charts for salary comparisons, grouped bars for cost comparisons. Label bars directly, no legend needed.
- Clean, professional design. White background. Good contrast. Readable at 14-16px base.
- Responsive: works on phone (320px) and desktop.
- Print-friendly: no fixed positioning, no dark backgrounds, page breaks between sections.
- Include a fixed-position "Save Report" button (top-right corner) that triggers a download of the page as an HTML file. Use this exact script:
  <button onclick="(function(){var a=document.createElement('a');a.href='data:text/html,'+encodeURIComponent(document.documentElement.outerHTML);a.download='should-i-go-report.html';a.click()})()">Save Report</button>
  Style it to match the report design. Hide it in print (@media print { .save-btn { display: none } }).

CONTENT RULES:
- Open with a bold 1-2 sentence personalized headline takeaway.
- Group data into logical sections with clear headings. Order by importance to this user.
- Omit data not relevant to the user's stated priorities and segment.
- Highlight comparisons: which school is cheapest, which major pays most, what the gap is.
- Include a "What this means for you" sentence in each section tied to their priorities.
- For income-based net price data, highlight the bracket closest to the user's situation if known.
- Footer must include this exact disclaimer:
  "Generated by AI using data from BLS (May 2024), College Scorecard, and O*NET. For informational purposes only, not financial or career advice. AI analysis may contain errors; verify figures before making decisions. Generated [today's date]."
- BLS caps reported salaries at $239,200/yr; note this where relevant.
- Be honest about limitations: medians vary by location, experience, and market conditions.

FINANCIAL ANALYSIS (when report_depth is "The whole picture"):
When the user's intake includes report_depth containing "whole picture", you MUST include a full financial breakdown section. Use these constants and formulas:

Reference values:
- Federal student loan interest rate: 6.5% (2026-2027 undergraduate rate)
- High school diploma median salary: $46,748/yr (baseline for opportunity cost and break-even)
- Standard repayment term: 10 years

For each career path or school option, calculate and display:
1. Total degree cost = annual net price (or tuition) x years of school
2. Opportunity cost = $46,748 x years of school (earnings foregone while in school)
3. Total investment = total degree cost + opportunity cost
4. Monthly loan payment = use standard amortization at 6.5% over 10 years
5. Total interest paid = (monthly payment x total months) - loan principal
6. Break-even point = total investment / (expected salary - $46,748). This is years after graduation until the degree pays for itself vs. working with only a HS diploma.

Present this as a comparison table or side-by-side cards (public vs. private, or across career paths). Include an SVG chart showing the break-even timeline.

When report_depth is "Just the numbers" or not present, skip the financial breakdown and show only salaries and career paths.

RESPOND WITH ONLY VALID JSON:
{"summary": "1-2 sentence plain text takeaway for chat", "html": "<!DOCTYPE html>..."}
"""


async def generate_report(
    intake_answers: dict,
    data_blocks: list[dict],
    agent_text: str,
) -> dict:
    logger.info("generate_report: %d data_blocks, intake_keys=%s", len(data_blocks), list(intake_answers.keys()))
    user_content = json.dumps({
        "intake_answers": intake_answers,
        "agent_summary": agent_text,
        "tool_results": data_blocks,
    }, default=_json_default)

    response = await client.messages.create(
        model=REPORT_MODEL,
        max_tokens=REPORT_MAX_TOKENS,
        system=REPORT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    text = "".join(b.text for b in response.content if b.type == "text")
    logger.info("Report response size: %d bytes, stop_reason=%s", len(text), response.stop_reason)
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    try:
        parsed = json.loads(text)
        logger.info("Report parsed OK: summary=%d chars, html=%d chars", len(parsed.get("summary", "")), len(parsed.get("html", "")))
        return parsed
    except json.JSONDecodeError:
        logger.error("Report generation returned invalid JSON: %s", text[:500])
        return {"summary": agent_text, "html": ""}


async def _call_claude(messages: list[dict]):
    """
    Call the Claude API with one retry on transient errors.
    Retriable: rate limit, connection error, 5xx. Non-retriable errors
    (auth, bad request) surface immediately so the caller sees the real cause.
    """
    last_exc: Exception | None = None
    for attempt in range(MAX_API_RETRIES + 1):
        try:
            return await client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )
        except (anthropic.APIConnectionError, anthropic.RateLimitError) as exc:
            last_exc = exc
            logger.warning("Anthropic transient error (attempt %d): %s", attempt + 1, exc)
        except anthropic.APIStatusError as exc:
            if exc.status_code and 500 <= exc.status_code < 600:
                last_exc = exc
                logger.warning("Anthropic 5xx (attempt %d): %s", attempt + 1, exc)
            else:
                raise
        if attempt < MAX_API_RETRIES:
            await asyncio.sleep(_retry_delay_for(last_exc))
    if last_exc is None:
        raise RuntimeError("_call_claude exited retry loop without a response or exception")
    raise last_exc


async def run_agent_stream(
    user_message: str,
    conversation_history: list[dict] | None = None,
    intake_answers: dict | None = None,
):
    """Async generator yielding progress events then a final result.

    Event shapes:
      {"event": "progress", "message": "Searching majors…"}
      {"event": "complete", "response": "...", "report_html": "...", "conversation_history": [...]}
    """
    messages = list(conversation_history) if conversation_history else []
    messages.append({"role": "user", "content": user_message})
    messages = _trim_history(messages)
    data_blocks: list[dict] = []

    for _ in range(MAX_TOOL_ITERATIONS):
        try:
            yield {"event": "progress", "message": "Thinking…"}
            response = await _call_claude(messages)
        except anthropic.APIError as exc:
            logger.error("Anthropic API failed after retries: %s", exc)
            yield {
                "event": "complete",
                "response": "Sorry, I'm having trouble right now. Please try again in a moment.",
                "data_blocks": [],
                "conversation_history": messages,
            }
            return

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": [b.model_dump() for b in response.content]})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input
                    tool_id = block.id

                    progress_start, progress_done = _TOOL_PROGRESS.get(
                        tool_name, (f"Running {tool_name}…", f"{tool_name} done")
                    )
                    yield {"event": "progress", "message": progress_start}

                    func = TOOL_DISPATCH.get(tool_name)
                    if not func:
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_id,
                                "content": f"Error: unknown tool '{tool_name}'",
                                "is_error": True,
                            }
                        )
                        continue

                    try:
                        result = await asyncio.to_thread(func, tool_input)
                        result_json = json.dumps(result, default=_json_default)
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_id,
                                "content": result_json,
                            }
                        )
                        if not (isinstance(result, dict) and "error" in result):
                            data_blocks.append({"type": tool_name, "data": result})
                        yield {"event": "progress", "message": progress_done}
                    except Exception as exc:
                        logger.exception("Tool %s failed", tool_name)
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_id,
                                "content": f"Error executing {tool_name}: {exc}",
                                "is_error": True,
                            }
                        )

            messages.append({"role": "user", "content": tool_results})

        else:
            text_response = "".join(
                block.text for block in response.content if block.type == "text"
            )
            messages.append({"role": "assistant", "content": [b.model_dump() for b in response.content]})

            report_html = ""
            report_status = "skipped"
            logger.info("Agent done. data_blocks=%d, intake_answers=%s", len(data_blocks), bool(intake_answers))
            if data_blocks and intake_answers:
                yield {"event": "progress", "message": "Generating report…"}
                report_status = "failed"
                try:
                    report = await generate_report(intake_answers, data_blocks, text_response)
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

            yield {
                "event": "complete",
                "response": text_response,
                "report_html": report_html,
                "report_status": report_status,
                "conversation_history": messages,
            }
            return

    logger.warning("Agent hit MAX_TOOL_ITERATIONS=%d without finishing", MAX_TOOL_ITERATIONS)
    yield {
        "event": "complete",
        "response": "I got stuck working through that. Try rephrasing your question or asking something simpler.",
        "report_html": "",
        "conversation_history": messages,
    }
