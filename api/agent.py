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
        "name": "run_sql",
        "description": """Run a read-only SQL SELECT query against the database. Only SELECT statements are allowed. Results are capped at 50 rows.

Database schema (PostgreSQL, all table/column names are double-quoted):

"OccupationCategory" (id UUID PK, name TEXT UNIQUE, occupation_code TEXT UNIQUE, created_at, updated_at)
  Sample: id='def-456', name='Computer and Mathematical Occupations', occupation_code='15-0000'

"OccupationSubCategory" (id UUID PK, name TEXT, occupation_code TEXT, annual_salary FLOAT, category_id UUID FK->OccupationCategory.id, typical_years_of_school FLOAT NULL, created_at, updated_at)
  Sample: id='ghi-789', name='Software Developers', occupation_code='15-1252', annual_salary=132270.0, typical_years_of_school=4.0

"CipCode" (id UUID PK, code TEXT UNIQUE, title TEXT, created_at, updated_at)
  Degree fields. code is a 4-digit CIP code with no dot. Sample: code='1107', title='Computer Science.'

"CipOccupation" (id UUID PK, cip_id UUID FK->CipCode.id, occupation_id UUID FK->OccupationSubCategory.id)
  Links degree fields to occupations (CIP-SOC crosswalk).

"ProgramDebt" (id UUID PK, cip_id UUID FK->CipCode.id, credential_level INT, credential_label TEXT, school_type TEXT, median_debt INT, mean_debt INT NULL, sample_size INT, source TEXT, created_at, updated_at)
  National median debt by degree field. credential_level: 1=Undergrad Cert, 2=Associate, 3=Bachelor, 5=Master, 6=Doctoral, 7=First Professional, 8=Grad/Prof Cert. school_type: public | private_nonprofit | all

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
    "search_occupations": ("Searching occupations…", "Found matching occupations"),
    "search_schools": ("Looking up schools…", "Found schools"),
    "get_school_programs": ("Pulling program earnings…", "Got program data"),
    "get_tuition_medians": ("Getting tuition data…", "Got tuition data"),
    "run_sql": ("Querying database…", "Query complete"),
}

TOOL_DISPATCH = {
    "search_occupations": lambda args: search_occupations(args["keyword"]),
    "get_tuition_medians": lambda _args: get_tuition_medians(),
    "search_schools": lambda args: search_schools(
        args.get("name"), args.get("state"), args.get("ownership"),
        args.get("max_net_price"), args.get("size"), args.get("sort_by"),
        args.get("degree_type", "bachelor"),
    ),
    "get_school_programs": lambda args: get_school_programs(args["school_id"], args.get("program_search")),
    "run_sql": lambda args: run_sql(args["query"]),
}

SYSTEM_PROMPT = """You are a data-gathering agent for the "Should I Go?" college advisor app. Your job is to collect all relevant data for a user's situation by calling tools. A separate step will synthesize and present the data.

TOOLS:

1. search_occupations(keyword) - Search occupations by keyword via O*NET. Returns SOC codes, bright outlook, education years, BLS salary. Use when user names a career, occupation, OR degree/field of study (e.g. "computer science" returns related occupations like Software Developers).
2. get_tuition_medians() - National median tuition by school type (public in-state, out-of-state, private).
3. search_schools(name, state, ownership, max_net_price, size, sort_by) - Search schools with filters. Returns graduation rate, earnings, debt, admission rate, retention rate, loan repayment. Only schools with graduation rate >= 70%.
4. get_school_programs(school_id, program_search?) - Per-program earnings at a specific school. Requires school_id from search_schools.
5. run_sql(query) - Read-only SQL for analytical questions the other tools can't answer.

The user's intake_answers include a "path_type" field (one of: path1, path2, path3, path4, path5). Gather data based on their path:

path1 - COLLEGE VS VOCATIONAL VS WORKING NOW:
User is undecided. Build a five-row comparison: HS diploma baseline, Cashier, Electrician, Bachelor's degree median, and user's chosen occupation.
- search_occupations for user's chosen occupation
- search_occupations for "electrician"
- search_occupations for "cashier"
- get_tuition_medians for cost baseline
- run_sql to get average annual salary for occupations where typical_years_of_school = 4 (bachelor's degree median)

path2 - COMPARING SCHOOLS:
User has decided on college, wants to compare schools.
- search_schools for each named school, OR search_schools by state if exploring by location
- Use their compare_metrics and rank_by preferences as sort_by param
- get_tuition_medians for national baseline

path3 - COMPARING PROGRAMS AT A SCHOOL:
User is at or committed to a specific school, comparing programs.
- search_schools for their school (to get school_id)
- get_school_programs for their school, filtered by each program they named
- search_occupations for occupations linked to their programs (for bright outlook, education data, BLS salary)

path4 - COMPARE CAREER TRACKS:
User wants to compare 2+ career paths side by side. Check current_position and current_field for their starting point.
- search_occupations for EACH career they named
- If user is working: search_occupations for their current role (for baseline comparison)
- get_tuition_medians for cost baseline (education paths may require degrees)
- search_occupations for related occupations in each field

path5 - PATH TO A SPECIFIC CAREER:
User has a target occupation and needs the roadmap from current position.
- search_occupations for target occupation
- If user is working: search_occupations for their current role (to show gap)
- get_tuition_medians if degree path is needed
- search_schools by state or find relevant programs if degree required

RULES:

- Call ALL relevant tools for the user's path in the first turn. Gather broadly.
- When a user mentions a degree, program, or career, call search_occupations. When they name a school, call search_schools.
- To get program earnings, call search_schools first (for school_id), then get_school_programs.
- If search_occupations returns no results, try broader/alternative keywords.
- BLS caps reported salaries at $239,200/yr.

RESPONSE:

After gathering data, respond with 2-3 short sentences:
1. Confirm what data you found (one sentence). Example: "I pulled salary and education data for pharmacist, electrician, and cashier, plus national tuition benchmarks."
2. Point the user to the report: "Your personalized report is ready — take a look and let me know what stands out or what you want to dig into."
3. If relevant, suggest a specific follow-up angle based on their situation.

Do not narrate the data. Do not list numbers. Do not use markdown. A report will be generated separately from your tool results.
"""

REPORT_SYSTEM_PROMPT = """You generate HTML reports for a college advisor app. You receive raw data from tool calls and the user's intake profile.

Generate a single self-contained HTML page that presents the findings as a clear, personalized report.

HTML RULES:
- All CSS in a single <style> tag. No external stylesheets except Google Fonts (one clean font).
- Charts as inline SVG. Follow these SVG chart rules strictly:
  * HORIZONTAL BAR CHARTS: school/occupation names go OUTSIDE the bar on the LEFT (text-anchor: end), values go OUTSIDE the bar on the RIGHT. Never place text inside bars.
  * Use short labels (e.g. "CO Mines" not "Colorado School of Mines"). Full names belong in the table, not the chart.
  * Always label both axes. X-axis: what the bars measure (e.g. "Annual Salary ($)"). Y-axis: what the rows are (e.g. "School").
  * Sort bars by value (largest at top for horizontal bars).
  * Add gridlines at regular intervals on the value axis. Label gridline values.
  * Use viewBox="0 0 700 N" where N scales with bar count. Reserve 150px left margin for labels.
  * Bars should be 28px tall with 12px gaps between them.
  * Use contrasting fill colors only when comparing categories (e.g. different bar color per group). Same category = same color.
- Clean, professional design. White background. Good contrast. Readable at 14-16px base.
- Responsive: works on phone (320px) and desktop.
- Print-friendly: no fixed positioning, no dark backgrounds, page breaks between sections.
- Include a fixed-position "Save Report" button (top-right corner) that triggers a download of the page as an HTML file. Use this exact script:
  <button onclick="(function(){var a=document.createElement('a');a.href='data:text/html,'+encodeURIComponent(document.documentElement.outerHTML);a.download='should-i-go-report.html';a.click()})()">Save Report</button>
  Style it to match the report design. Hide it in print (@media print { .save-btn { display: none } }).

CONTENT RULES:
- Open with a bold 1-2 sentence personalized headline takeaway.
- Group data into logical sections with clear headings. Order by importance to this user.
- Highlight comparisons: which option costs least, pays most, pays off fastest.
- Never use the words "major" or "break-even". Say "degree" or "program", and "payoff timeline".
- Include a "What this means for you" sentence in each section.
- For income-based net price data, highlight the bracket closest to the user's situation if known.
- Footer must include this exact disclaimer:
  "Generated by AI using data from BLS (May 2024), College Scorecard, and O*NET. For informational purposes only, not financial or career advice. AI analysis may contain errors; verify figures before making decisions. Generated [today's date]."
- BLS caps reported salaries at $239,200/yr; note this where relevant.
- Be honest about limitations: medians vary by location, experience, and market conditions.

FINANCIAL ANALYSIS (always included):
Every report MUST include a full financial breakdown. Use these constants and formulas:

Reference values:
- Federal student loan interest rate: 6.53% (2026-2027 undergraduate rate)
- High school diploma median salary: $46,748/yr (default baseline for opportunity cost and payoff timeline)
- Standard repayment term: 10 years

For each career path or school option, calculate and display:
1. Total education cost = annual net price (or tuition) x years of school (or program cost)
2. Opportunity cost = $46,748 x years in school (earnings foregone)
3. Total investment = education cost + opportunity cost
4. Monthly loan payment = standard amortization at 6.53% over 10 years
5. Payoff timeline = total investment / (expected salary - baseline salary). Years after graduation until the education pays for itself. Baseline is $46,748 (HS diploma) unless the user gave a current salary; then use their current salary as the baseline and for opportunity cost. If expected salary <= baseline, say it does not pay off at that salary.

Present as a comparison table or side-by-side cards. Include an SVG chart showing the payoff timeline.

PATH-SPECIFIC REPORT FORMAT:

The user's intake includes a "path_type" field (one of: path1, path2, path3, path4, path5). Use it to structure the report:

path1 (college vs vocational vs work):
Five-row comparison table. Each row: occupation (or baseline), education required + timeline, estimated cost (tuition + opportunity cost), expected salary, payoff timeline vs HS diploma baseline. Rows: (1) HS diploma baseline ($46,748/yr, zero cost), (2) Cashier (entry-level, no post-secondary), (3) Electrician (vocational/trade path), (4) Bachelor's degree median, (5) User's chosen occupation. SVG bar chart comparing all five.

path2 (comparing schools):
Top 5 schools ranked by user's chosen metric. Show ONLY the metrics the user toggled in compare_metrics. Full financial analysis per school.

path3 (comparing programs at school):
Program comparison at user's school. Each program shows: school-specific earnings (from Scorecard program data) AND national occupation salary (from BLS). Label each data point by source. Career options, demand indicators, bright outlook status from O*NET. If user is switching, side-by-side of current vs considered programs.

path4 (compare career tracks):
Side-by-side cards or table. Each occupation: education path required, timeline, estimated cost, expected salary, bright outlook status, payoff timeline vs the user's baseline. Use user's current_position and current_field to contextualize (e.g. credit for existing education, gap from current role).

path5 (path to career):
Roadmap from current position to target. Steps, timeline, education needed, estimated cost. Show gap analysis between current education and required education. If user already has relevant education, show how far along they are. End with expected salary and time to recoup vs current income.

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
      {"event": "progress", "message": "Searching occupations…"}
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
