"""
Report-generation eval: feeds each fixed report input in report_cases.jsonl
(built by make_report_cases.py) to the report step alone and checks the report
it produces with checks.py plus the case's expectations. No data gathering, so
results reflect only the report prompt, model, and rendering.

    api/venv/bin/python evals/report_eval.py
    api/venv/bin/python evals/report_eval.py --case path1-lawyer-medians --repeats 3

Local runs use the free-tier key (api/llm.py). Full outputs go to
evals/results/report-<timestamp>.json.
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import run  # noqa: F401  loads .env, puts api/ on the import path, collects warnings
from checks import choice_checks, run_checks
from run import WARNINGS, agent

EVALS = Path(__file__).resolve().parent
RESULTS = EVALS / "results"


async def run_case(case: dict) -> dict:
    content = case["report_input"]
    WARNINGS.lines = []
    start = time.perf_counter()
    report = {}
    async for event in agent.write_report(content, ""):
        if event.get("event") == "report":
            report = event["report"]
    summary, html = report.get("summary", ""), report.get("html", "")
    return {
        "id": case["id"],
        "seconds": round(time.perf_counter() - start, 1),
        "checks": {**run_checks(summary, html, case.get("expect")), **choice_checks(html, content["rows"], case.get("expect"))},
        "warnings": list(WARNINGS.lines),
        "summary": summary,
        "report_html": html,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", help="run only the case with this id")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--pause", type=float, default=15, help="seconds between runs, to stay well under the free-tier rate limit")
    args = parser.parse_args()

    cases = [json.loads(l) for l in (EVALS / "report_cases.jsonl").read_text().splitlines() if l.strip()]
    if args.case:
        cases = [c for c in cases if c["id"] == args.case] or sys.exit(f"No case {args.case!r}")

    runs = []
    for case in cases:
        for _ in range(args.repeats):
            if runs:
                await asyncio.sleep(args.pause)
            r = await run_case(case)
            failed = {n: c["hits"] for n, c in r["checks"].items() if not c["pass"]}
            print(f"{'PASS' if not failed else 'FAIL'} {r['id']} ({r['seconds']}s)" + (f": {failed}" if failed else ""), flush=True)
            runs.append(r)

    names = list(runs[0]["checks"])
    print(f"\n{len(runs)} runs")
    for n in names:
        print(f"  {n:<26} {sum(r['checks'][n]['pass'] for r in runs) / len(runs):.2f}")
    print(f"  {'ALL CHECKS PASS':<26} {sum(all(c['pass'] for c in r['checks'].values()) for r in runs) / len(runs):.2f}")
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"report-{datetime.now():%Y%m%d-%H%M%S}.json"
    out.write_text(json.dumps(runs, indent=2))
    print(f"Full outputs: {out}")


if __name__ == "__main__":
    asyncio.run(main())
