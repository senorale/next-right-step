"""
Report output eval. Runs each case in cases.jsonl through the full agent
(data gathering + report), scores the output with checks.py, and compares to
baseline.json.

Runs on Gemini's free tier (GEMINI_FREE_TIER_API_KEY in .env) so evals cost nothing.
Free-tier prompts may be used by Google and read by reviewers, so cases must
be made up, never real user data. Free-tier speed differs from paid, so the
timings are rough; use them for comparisons between runs, not as user latency.

    api/venv/bin/python evals/run.py               # 3 runs per case, compare to baseline
    api/venv/bin/python evals/run.py --repeats 5
    api/venv/bin/python evals/run.py --case path1-lawyer --repeats 1
    api/venv/bin/python evals/run.py --save-baseline
    api/venv/bin/python evals/run.py --api-dir <path>/api --repeats 1   # benchmark another commit
    api/venv/bin/python evals/run.py --rescore evals/results/<file>.json   # re-check saved outputs, no API calls

Full outputs go to evals/results/ (gitignored).
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

EVALS = Path(__file__).resolve().parent
# --api-dir runs another copy of the API (e.g. a git worktree of an older commit).
API = Path(sys.argv[sys.argv.index("--api-dir") + 1]).resolve() if "--api-dir" in sys.argv else EVALS.parent / "api"
sys.path.insert(0, str(API))
sys.path.insert(0, str(EVALS))
CALLER_CWD = Path.cwd()
os.chdir(API)  # agent.py loads ../.env relative to the working directory

from dotenv import load_dotenv  # noqa: E402

load_dotenv("../.env")
if not os.environ.get("GEMINI_FREE_TIER_API_KEY") and "--rescore" not in sys.argv:
    sys.exit("Set GEMINI_FREE_TIER_API_KEY in .env (a free-tier key from Google AI Studio).")
# Local runs always use the free-tier key (api/llm.py); never run evals inside a Railway deployment.

logging.basicConfig(level=logging.INFO, format="    %(message)s")


class _WarningCollector(logging.Handler):
    """Keeps WARNING and above per run so failures can be diagnosed from results."""

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.lines: list[str] = []

    def emit(self, record):
        self.lines.append(f"{record.levelname}: {record.getMessage()[:500]}")


WARNINGS = _WarningCollector()
logging.getLogger().addHandler(WARNINGS)
for noisy in ("httpx", "anthropic", "db"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

import agent  # noqa: E402
import report  # noqa: E402
from checks import run_checks  # noqa: E402

BASELINE = EVALS / "baseline.json"
RESULTS = EVALS / "results"
FAILED_REPLY = "Sorry, I'm having trouble right now."


def load_cases() -> list[dict]:
    return [json.loads(line) for line in (EVALS / "cases.jsonl").read_text().splitlines() if line.strip()]


async def run_case(case: dict) -> dict:
    final = {}
    WARNINGS.lines = []
    for attempt in range(2):
        start = time.perf_counter()
        async for event in agent.run_agent_stream(case["message"], [], case["intake_answers"]):
            if event.get("event") == "complete":
                final = event
        if not final.get("response", "").startswith(FAILED_REPLY):
            break
        # Runs go back to back. The agent already retries a rate-limited call once
        # after the delay the API asks for; if the run still fails (error logged
        # above), give the free-tier quota time to reset and retry the run once.
        print("  model API failed, retrying in 30s…", flush=True)
        await asyncio.sleep(30)
    response, report_html = final.get("response", ""), final.get("report_html", "")
    return {
        "id": case["id"],
        "seconds": round(time.perf_counter() - start, 1),
        "model": agent.MODEL,
        "report_status": final.get("report_status"),
        "log_warnings": WARNINGS.lines,
        "tool_calls": [
            {"name": c["function"]["name"], "arguments": c["function"]["arguments"]}
            for m in final.get("conversation_history", []) if m.get("role") == "assistant"
            for c in m.get("tool_calls") or []
        ],
        "checks": run_checks(response, report_html, case.get("expect")),
        "response": response,
        "report_html": report_html,
    }


def summarize(runs: list[dict]) -> dict:
    names = list(runs[0]["checks"])
    return {
        "runs": len(runs),
        "prompt_chars": {
            "agent_system": len(agent.SYSTEM_PROMPT),
            "agent_tools": len(json.dumps(agent.TOOLS)),
            "report_system": len(report.REPORT_SPEC_SYSTEM_PROMPT),
        },
        "pass_rate": {n: round(sum(r["checks"][n]["pass"] for r in runs) / len(runs), 2) for n in names},
        "all_pass_rate": round(sum(all(c["pass"] for c in r["checks"].values()) for r in runs) / len(runs), 2),
        "avg_seconds": round(sum(r["seconds"] for r in runs) / len(runs), 1),
    }


def print_table(current: dict, baseline: dict | None) -> None:
    def row(name: str, now, before) -> None:
        delta = "" if before is None or before == now else f"  (baseline {before})"
        print(f"  {name:<26} {now}{delta}")

    b = baseline or {}
    print(f"\n{current['runs']} runs")
    for name, rate in current["pass_rate"].items():
        row(name, rate, b.get("pass_rate", {}).get(name))
    row("ALL CHECKS PASS", current["all_pass_rate"], b.get("all_pass_rate"))
    row("avg seconds", current["avg_seconds"], b.get("avg_seconds"))
    for name, chars in current["prompt_chars"].items():
        row(f"{name} chars", chars, b.get("prompt_chars", {}).get(name))


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--case", help="run only the case with this id")
    parser.add_argument("--save-baseline", action="store_true")
    parser.add_argument("--api-dir", help="run a different copy of the api/ directory")
    parser.add_argument("--rescore", type=Path, help="re-run checks on a saved results file instead of calling the API")
    args = parser.parse_args()

    if args.rescore:
        runs = json.loads((CALLER_CWD / args.rescore).read_text())["runs"]
        expects = {c["id"]: c.get("expect") for c in load_cases()}
        for r in runs:
            r["checks"] = run_checks(r["response"], r["report_html"], expects.get(r["id"]))
        finish(runs, args.save_baseline, (CALLER_CWD / args.rescore))
        return

    cases = load_cases()
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            sys.exit(f"No case with id {args.case!r} in cases.jsonl")
    runs = []
    for case in cases:
        for i in range(args.repeats):
            print(f"{case['id']} run {i + 1}/{args.repeats}…", flush=True)
            result = await run_case(case)
            failed = [n for n, c in result["checks"].items() if not c["pass"]]
            print(f"  {result['seconds']}s, failed: {', '.join(failed) or 'none'}", flush=True)
            runs.append(result)

    RESULTS.mkdir(exist_ok=True)
    finish(runs, args.save_baseline, RESULTS / f"{datetime.now():%Y%m%d-%H%M%S}.json")


def finish(runs: list[dict], save_baseline: bool, out: Path) -> None:
    summary = summarize(runs)
    out.write_text(json.dumps({"summary": summary, "runs": runs}, indent=2))

    baseline = json.loads(BASELINE.read_text()) if BASELINE.exists() else None
    print_table(summary, baseline)
    if save_baseline:
        BASELINE.write_text(json.dumps(summary, indent=2) + "\n")
        print(f"\nSaved baseline to {BASELINE}")
    print(f"Full outputs: {out}")


if __name__ == "__main__":
    asyncio.run(main())
