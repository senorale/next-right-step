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
from options import path5_choices

EVALS = Path(__file__).resolve().parent

LABELS = {
    "path2": "Comparing Schools", "path3": "Comparing Programs at a School",
    "path4": "Compare Career Tracks", "path5": "Best Schools for a Career",
}
# CREDENTIAL_LEVELS and RANK_BY_OPTIONS in src/app/chat/page.tsx
CREDENTIALS = {"1": "Undergraduate certificate", "2": "Associate's degree", "3": "Bachelor's degree",
               "4": "Post-baccalaureate certificate", "5": "Master's degree", "6": "Doctoral degree",
               "7": "Professional degree (JD, MD, PharmD)", "8": "Graduate certificate"}
RANK_BY = {"debt_to_pay": "Debt compared with pay", "earnings_4yr": "Pay 4 years after graduating",
           "earnings_1yr": "Pay 1 year after graduating", "debt": "Lowest debt"}
SITUATIONS = {"deciding": "Deciding between programs", "current": "Already in a program, exploring outcomes",
              "switching": "Thinking about switching programs"}
# METRIC_TO_SORT in src/app/chat/page.tsx
SORT = {"Earnings after graduation": "earnings", "Graduation rate": "graduation_rate", "Net price / cost": "net_price",
        "Debt at graduation": "median_debt", "Admission rate": "admission_rate", "Retention rate": "retention_rate",
        "Loan repayment rate": "loan_repayment"}


def with_soc(title: str, code: str | None) -> str:
    """withSoc in src/app/chat/page.tsx."""
    return f"{title} (SOC {code})" if code else title


def current_job(a: dict) -> str:
    """currentJob in src/app/chat/page.tsx."""
    return with_soc(a.get("current_role_title") or a["current_role"], a.get("current_role_code"))


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
        school_id = f" (school_id {a['school_id']})" if a.get("school_id") else ""
        # programsLine in src/app/chat/page.tsx: confirmed titles, else what they typed.
        programs = json.loads(a["program_list"]) if a.get("program_list") else None
        if programs is not None:
            programs = "; ".join(programs) or "Not sure, show me the top programs"
        lines += ["- I'm at or committed to a specific school, comparing programs",
                  f"- School: {a.get('school_matched_name') or a['school_name']}{school_id}",
                  f"- Situation: {SITUATIONS[a['school_situation']]}",
                  f"- Programs: {programs or a['programs']}"]
        if a.get("switch_reason"):
            lines.append(f"- Reason for switching: {a['switch_reason']}")
        lines += [f"- What matters most: {a['program_priority']}", "",
                  "Compare programs at my school. Show school-specific earnings (Scorecard) and national occupation salary (BLS) "
                  "for each. Include career options, demand, and bright outlook. Full financial analysis."]
    elif path == "path4":
        # careersLine in src/app/chat/page.tsx: confirmed careers with SOC codes, else what they typed.
        matches = json.loads(a["career_matches"]) if a.get("career_matches") else None
        careers = ", ".join(with_soc(m["title"], m["soc_code"]) for m in matches) if matches else a["careers_to_compare"]
        lines += ["- I want to compare career paths side by side", f"- Careers to compare: {careers}"]
        if a.get("include_current_role") == "yes" and a.get("current_role"):
            lines.append(f"- Include my current job: {current_job(a)}")
            if a.get("include_salary") == "yes" and a.get("current_salary_value"):
                lines.append(f"- My pay: ${int(a['current_salary_value']):,} a year")
                if a.get("compare_to_median") == "yes":
                    lines.append("- Also show the national median for my job")
        lines += ["", "Compare these careers side by side: education required, years of school, median debt, and salary."]
    else:
        # path5 in buildPrompt (src/app/chat/page.tsx)
        target = with_soc(a.get("target_career_title") or a["target_career"], a.get("target_career_code"))
        fields, _, level = path5_choices(a)
        where = (a.get("target_places") or a.get("target_location")) if a.get("location_scope") == "states" else "Anywhere in the US"
        fields_line = "; ".join(f"{f['title']} (CIP {f['cip']})" for f in fields)
        lines += ["- I want to find the schools whose graduates do best in a specific career", f"- Target career: {target}",
                  f"- Fields of study: {fields_line}", f"- Degree level: {CREDENTIALS.get(str(level), level)}",
                  f"- Location: {where}"]
        if a.get("min_pay_value"):
            lines.append(f"- Minimum pay 4 years after graduating: ${int(a['min_pay_value']):,}")
        if a.get("max_debt_value"):
            lines.append(f"- Maximum median debt: ${int(a['max_debt_value']):,}")
        lines += [f"- Rank by: {RANK_BY[a['rank_by']]}", "",
                  "Rank the schools whose graduates in this program do best: pay 1 and 4 years after graduating, and median debt."]
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
