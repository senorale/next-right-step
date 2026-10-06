"""
Smoke test: runs one made-up case per path (smoke_cases.jsonl) through the full
chat pipeline and checks that it finishes, which tools ran, and that a report
renders, plus the report-number checks (checks.py): every figure in the text
comes from the rows code rendered.

    api/venv/bin/python evals/smoke.py
    api/venv/bin/python evals/smoke.py --case path3-programs

Local runs use the free-tier key (api/llm.py).
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import run  # noqa: F401  loads .env, puts api/ on the import path, collects warnings
from checks import run_checks
from run import WARNINGS, agent

EVALS = Path(__file__).resolve().parent

LABELS = {
    "path2": "Comparing Schools", "path3": "Comparing Programs at a School",
    "path4": "Compare Career Tracks", "path5": "Path to a Specific Career",
}
POSITIONS = {"working": "Working", "in_college": "In college", "high_school": "In high school", "looking_for_work": "Looking for work"}
LEVELS = {"some_college": "Some college, no degree", "associate": "Associate's", "bachelor": "Bachelor's", "hs": "High school diploma or GED"}
# METRIC_TO_SORT in src/app/chat/page.tsx
SORT = {"Earnings after graduation": "earnings", "Graduation rate": "graduation_rate", "Net price / cost": "net_price",
        "Debt at graduation": "median_debt", "Admission rate": "admission_rate", "Retention rate": "retention_rate",
        "Loan repayment rate": "loan_repayment"}


def chat_message(a: dict) -> str:
    """First chat message, same shape as buildPrompt in src/app/chat/page.tsx."""
    path = a["path_type"]
    lines = [f"Decision point: {LABELS[path]}", "", "Here's my situation:"]
    if path == "path2":
        lines.append("- I've decided on college, comparing schools")
        if a.get("target_schools"):
            lines.append(f"- Schools to compare: {a.get('school_names') or a['target_schools']}")
        if a.get("target_location"):
            lines.append(f"- Location: {a['target_location']}")
        lines.append(f"- Compare on: {', '.join(a['compare_metrics'].split('|'))}")
        lines += [f"- Rank by: {a['rank_by']}", f"- sort_by: {SORT[a['rank_by']]}", "",
                  "Show me up to 5 schools ranked by my chosen metric, with only the metrics I selected. Include full financial analysis."]
    elif path == "path3":
        lines += ["- I'm at or committed to a specific school, comparing programs", f"- School: {a['school_name']}",
                  "- Situation: Deciding between programs", f"- Programs: {a['programs']}",
                  f"- What matters most: {a['program_priority']}", "",
                  "Compare programs at my school. Show school-specific earnings (Scorecard) and national occupation salary (BLS) "
                  "for each. Include career options, demand, and bright outlook. Full financial analysis."]
    else:
        lines.append("- I want to compare career paths side by side" if path == "path4" else "- I have a specific career in mind")
        lines.append(f"- Careers to compare: {a['careers_to_compare']}" if path == "path4" else f"- Target career: {a['target_career']}")
        lines.append(f"- Current position: {POSITIONS[a['current_position']]}")
        if a.get("education_level"):
            lines.append(f"- Highest education: {LEVELS[a['education_level']]}")
        if a.get("current_field"):
            lines.append(f"- Field of study: {a['current_field']}")
        if a.get("current_role"):
            lines.append(f"- Current job: {a['current_role']}")
        lines += ["", "Compare each career path: education required, timeline, cost, salary, bright outlook, payoff timeline. "
                  "Full financial analysis for all paths." if path == "path4" else
                  "Map out the full path from where I am to the target career. Steps, timeline, education, cost, expected "
                  "salary, time to recoup. Show gap analysis if I have relevant education."]
    return "\n".join(lines)


async def run_case(case: dict) -> dict:
    WARNINGS.lines = []
    start = time.perf_counter()
    final = {}
    async for event in agent.run_agent_stream(chat_message(case["intake_answers"]), [], case["intake_answers"]):
        if event.get("event") == "complete":
            final = event
    tools = [
        f"{c['function']['name']}({c['function']['arguments']})"
        for m in final.get("conversation_history", []) if m.get("role") == "assistant"
        for c in m.get("tool_calls") or []
    ]
    problems = []
    if final.get("response", "").startswith(("Sorry, I'm having trouble", "I got stuck")):
        problems.append(f"agent failed: {final['response'][:80]}")
    if final.get("report_status") != "success" or not final.get("report_html"):
        problems.append(f"report {final.get('report_status')}")
    else:
        checks = run_checks(final.get("response", ""), final["report_html"])
        problems += [f"{name}: {c['hits']}" for name, c in checks.items() if not c["pass"]]
    return {"id": case["id"], "seconds": round(time.perf_counter() - start, 1), "tools": tools,
            "problems": problems, "warnings": list(WARNINGS.lines), "response": final.get("response", "")}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", help="run only the case with this id")
    args = parser.parse_args()
    cases = [json.loads(l) for l in (EVALS / "smoke_cases.jsonl").read_text().splitlines() if l.strip()]
    if args.case:
        cases = [c for c in cases if c["id"] == args.case] or sys.exit(f"No case {args.case!r}")
    for case in cases:
        r = await run_case(case)
        print(f"{'PASS' if not r['problems'] else 'FAIL'} {r['id']} ({r['seconds']}s)" + (f": {r['problems']}" if r["problems"] else ""))
        print(f"  tools: {r['tools']}")
        for w in r["warnings"]:
            print(f"  warning: {w[:200]}")
        print(f"  reply: {r['response'][:160]}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
