"""
Report input eval: checks the data the report model receives, not the report
it writes. Runs gathering for each case in input_cases.jsonl (code for path1
on medians, the agent otherwise), captures build_report_input() instead of
calling the report model, and compares it to the case's expectations.

    api/venv/bin/python evals/inputs.py
    api/venv/bin/python evals/inputs.py --case path1-lawyer-specific

Uses the same Gemini free-tier setup as run.py. Full inputs go to
evals/results/inputs-<timestamp>.json.
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import run  # noqa: F401  sets up the env (Gemini free tier) and imports the API
from run import agent

EVALS = Path(__file__).resolve().parent
RESULTS = EVALS / "results"
FLOW_TEXT = (
    "Compare these five options side by side: (1) HS diploma baseline, (2) Cashier, (3) Electrician, "
    "(4) Bachelor's degree median, (5) my chosen occupation. Include full financial analysis with payoff timeline."
)


def chat_message(intake: dict) -> str:
    """Same first message the chat page builds for path1 (buildPrompt in src/app/chat/page.tsx)."""
    lines = [
        "Decision point: College vs Vocational vs Working Now", "", "Here's my situation:",
        "- I'm deciding between college, a trade, or working right away",
    ]
    if intake.get("data_source") == "specific":
        lines.append("- Data preference: has specific numbers (tuition quotes, salary offers)")
        lines.append(f"- My specific numbers: {intake['specific_numbers']}")
    else:
        lines.append("- Data preference: use national medians")
    lines.append(f"- Occupation I'm interested in: {intake['occupation']}")
    return "\n".join(lines + ["", FLOW_TEXT])


def _numbers(value, skip_keys=("intake_answers",)) -> list[float]:
    """Every number in the structured input, outside the user's raw intake text."""
    if isinstance(value, dict):
        return [n for k, v in value.items() if k not in skip_keys for n in _numbers(v, skip_keys)]
    if isinstance(value, list):
        return [n for v in value for n in _numbers(v, skip_keys)]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return [float(value)]
    return []


def check(content: dict, fixed: list[dict] | None, data_blocks: list[dict], intake: dict, expect: dict) -> dict:
    results: dict[str, list[str]] = {}

    code = agent._chosen_occupation_code(intake, data_blocks)
    results["chosen_occupation"] = [] if code == expect["occupation_code"] else [f"got {code}, expected {expect['occupation_code']}"]

    if "rows" in expect:
        rows = {o["name"]: o for o in fixed or []}
        problems = [] if fixed else ["no path1_options in the report input"]
        for name, want in expect["rows"].items():
            got = rows.get(name)
            if not got:
                problems.append(f"missing row {name!r}")
                continue
            problems += [
                f"{name}.{k}: got {got.get(k)}, expected {v}"
                for k, v in want.items() if got.get(k) != v
            ]
        results["path1_rows"] = problems

    if "user_numbers" in expect:
        # The user's figures must reach the report as structured values, not
        # only as the raw intake text the report model has to parse.
        present = set(_numbers(content))
        results["user_numbers_structured"] = [
            f"{k}={v} not in the input outside the raw intake text"
            for k, v in expect["user_numbers"].items() if float(v) not in present
        ]
        results["official_data_present"] = [] if any(
            r.get("soc_code") == expect["occupation_code"]
            for b in data_blocks if b.get("type") == "search_occupations" and isinstance(b.get("data"), dict)
            for r in b["data"].get("results", [])
        ) else [f"no search result for {expect['occupation_code']} to compare against"]

    return {name: {"pass": not hits, "hits": hits} for name, hits in results.items()}


async def run_case(case: dict) -> dict:
    captured: dict = {}

    async def capture_report(intake_answers, data_blocks, agent_text):
        content, fixed = await agent.prepare_report_input(intake_answers, data_blocks, agent_text)
        captured.update(content=content, fixed=fixed, data_blocks=data_blocks)
        yield {"event": "report", "report": {"summary": agent_text, "html": ""}}

    agent.generate_report_stream = capture_report  # skip the report model; this eval stops at its input
    final = {}
    async for event in agent.run_agent_stream(chat_message(case["intake_answers"]), [], case["intake_answers"]):
        if event.get("event") == "complete":
            final = event
    tool_calls = [
        {"name": c["function"]["name"], "arguments": c["function"]["arguments"]}
        for m in final.get("conversation_history", []) if m.get("role") == "assistant"
        for c in m.get("tool_calls") or []
    ]
    if not captured:
        checks = {"report_input_built": {"pass": False, "hits": [f"no report input; reply: {final.get('response', '')[:200]}"]}}
    else:
        checks = check(captured["content"], captured["fixed"], captured["data_blocks"], case["intake_answers"], case["expect"])
    return {"id": case["id"], "tool_calls": tool_calls, "checks": checks, "report_input": captured.get("content")}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", help="run only the case with this id")
    args = parser.parse_args()

    cases = [json.loads(l) for l in (EVALS / "input_cases.jsonl").read_text().splitlines() if l.strip()]
    if args.case:
        cases = [c for c in cases if c["id"] == args.case] or sys.exit(f"No case {args.case!r}")

    results = []
    for case in cases:
        print(f"{case['id']}…", flush=True)
        r = await run_case(case)
        print(f"  tools: {[t['name'] + t['arguments'] for t in r['tool_calls']] or 'none (gathered in code)'}")
        for name, c in r["checks"].items():
            print(f"  {'PASS' if c['pass'] else 'FAIL'} {name}" + ("" if c["pass"] else f": {c['hits']}"))
        results.append(r)

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"inputs-{datetime.now():%Y%m%d-%H%M%S}.json"
    out.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nFull inputs: {out}")


if __name__ == "__main__":
    asyncio.run(main())
