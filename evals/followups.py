"""
Follow-up and fallback eval (data gathering): the turns where the gathering
model runs. A first turn with complete intake is gathered in code
(agent._planned_calls), so the gathering prompt only matters for:
- follow-ups: a question about what was gathered (answered in chat, no new
  report) or a request to add something (new tools, report rebuilt);
- fallback first turns: intake without its confirmed keys (the intake check
  failed), so the model gathers from the first message.

Each case starts from an input case's intake (input_cases.jsonl, by "base").
Follow-up cases run that first turn as-is, then the follow-up; fallback cases
drop the "strip" keys and run the first turn only.

    api/venv/bin/python evals/followups.py
    api/venv/bin/python evals/followups.py --case add-school --repeats 3

Local runs use the free-tier key (api/llm.py). Full outputs go to
evals/results/followups-<timestamp>.json.
"""

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import run  # noqa: F401  loads .env, puts api/ on the import path, collects warnings
from run import WARNINGS, agent
from inputs import chat_message
from report_checks import _same

EVALS = Path(__file__).resolve().parent
RESULTS = EVALS / "results"
FAILED = ("Sorry, I'm having trouble", "I got stuck")

_captured: dict = {}
_prepare = agent.prepare_report_input


async def _capture_rows(intake_answers, data_blocks, agent_text=""):
    content, rows = await _prepare(intake_answers, data_blocks, agent_text)
    _captured["rows"] = rows
    return content, rows


agent.prepare_report_input = _capture_rows  # record the rows each report shows


async def _turn(message: str, history: list, intake: dict) -> dict:
    _captured.clear()
    final = {}
    async for event in agent.run_agent_stream(message, history, intake):
        if event.get("event") == "complete":
            final = event
    new = final.get("conversation_history", [])[len(history):]
    return {
        "response": final.get("response", ""),
        "status": final.get("report_status"),
        "tools": [c["function"]["name"] for m in new if m.get("role") == "assistant" for c in m.get("tool_calls") or []],
        "rows": [r["option_id"] for r in _captured.get("rows") or []],
        "row_names": [r["name"] for r in _captured.get("rows") or []],
        "history": final.get("conversation_history", []),
    }


def _data_numbers(history: list) -> list[float]:
    """Every number in the tool results, plus rates as percents (0.938 -> 93.8)."""
    found: list[float] = []

    def walk(v):
        if isinstance(v, bool):
            return
        if isinstance(v, (int, float)):
            found.append(float(v))
            if 0 < v <= 1:
                found.append(float(v) * 100)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    for m in history:
        if m.get("role") == "tool":
            try:
                walk(json.loads(m.get("content") or ""))
            except json.JSONDecodeError:
                pass
    return found


def _matches(value: float, data: list[float]) -> bool:
    return any(_same(value, d) or round(d, 1) == value or round(d) == value for d in data)


def unsupported_figures(answer: str, history: list) -> list[str]:
    """Figures in the answer that are neither in the tool data nor the exact
    difference between two of its figures. Small counts (1-3 sentences, top 3)
    are words, not data, so numbers under 10 are skipped."""
    data = sorted(set(_data_numbers(history)))
    big = [d for d in data if d >= 1000]
    gaps = [abs(a - b) for i, a in enumerate(big) for b in big[i + 1:]]
    out = []
    for raw in re.findall(r"\$?\d[\d,]*(?:\.\d+)?%?", answer):
        value = float(raw.strip("$%").replace(",", ""))
        if value < 10 or 1900 <= value <= 2100:  # counts, years
            continue
        if not (_matches(value, data) or any(_same(value, g) for g in gaps)):
            out.append(raw)
    return out


def check(case: dict, turn: dict) -> dict:
    expect = case["expect"]
    results: dict[str, list[str]] = {}
    results["completed"] = [f"agent failed: {turn['response'][:80]}"] if turn["response"].startswith(FAILED) else []
    if "status" in expect:
        results["status"] = [] if turn["status"] in expect["status"] else [f"status {turn['status']}, expected {expect['status']}"]
    if expect.get("no_tools"):
        results["no_tools"] = [f"called {t}" for t in turn["tools"]]
    if expect.get("answer_figures_in_data"):
        results["answer_figures_in_data"] = [f"{f} not in data: {turn['response'][:160]}"
                                             for f in unsupported_figures(turn["response"], turn["history"])]
    if "answer_mentions" in expect:
        results["answer_mentions"] = [f"doesn't mention {w!r}: {turn['response'][:160]}" for w in expect["answer_mentions"]
                                      if w.lower() not in turn["response"].lower()]
    if "rows_include" in expect:
        results["rows_include"] = [f"missing {i}" for i in expect["rows_include"] if i not in turn["rows"]]
    if "row_names_include" in expect:
        names = " | ".join(turn["row_names"]).lower()
        results["row_names_include"] = [f"no row named like {w!r}" for w in expect["row_names_include"] if w not in names]
    return {name: {"pass": not hits, "hits": hits} for name, hits in results.items()}


async def run_case(case: dict, bases: dict) -> dict:
    intake = {k: v for k, v in bases[case["base"]]["intake_answers"].items() if k not in case.get("strip", [])}
    WARNINGS.lines = []
    first = await _turn(chat_message(intake), [], intake)
    turn = await _turn(case["follow_up"], first["history"], intake) if "follow_up" in case else first
    return {"id": case["id"], "tools": turn["tools"], "status": turn["status"], "rows": turn["rows"],
            "response": turn["response"], "checks": check(case, turn), "warnings": list(WARNINGS.lines)}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", help="run only the case with this id")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--pause", type=float, default=10, help="seconds between runs, to stay under the free-tier rate limit")
    args = parser.parse_args()

    bases = {c["id"]: c for c in (json.loads(l) for l in (EVALS / "input_cases.jsonl").read_text().splitlines() if l.strip())}
    cases = [json.loads(l) for l in (EVALS / "followup_cases.jsonl").read_text().splitlines() if l.strip()]
    if args.case:
        cases = [c for c in cases if c["id"] == args.case] or sys.exit(f"No case {args.case!r}")

    runs = []
    for case in cases:
        for _ in range(args.repeats):
            if runs:
                await asyncio.sleep(args.pause)
            r = await run_case(case, bases)
            for _ in range(2):
                if not any("429" in w for w in r["warnings"]):
                    break
                # The free tier's quota, not the model: wait for it to reset and run the case again.
                print(f"  {case['id']}: rate limited, retrying in 60s…", flush=True)
                await asyncio.sleep(60)
                r = await run_case(case, bases)
            r["rate_limited"] = any("429" in w for w in r["warnings"])
            failed = {n: c["hits"] for n, c in r["checks"].items() if not c["pass"]}
            print(f"{'PASS' if not failed else 'FAIL'} {r['id']} tools={r['tools']} status={r['status']}"
                  + (f": {failed}" if failed else ""), flush=True)
            runs.append(r)

    names = list(dict.fromkeys(n for r in runs for n in r["checks"]))
    print(f"\n{len(runs)} runs")
    for n in names:
        had = [r["checks"][n]["pass"] for r in runs if n in r["checks"]]
        print(f"  {n:<26} {sum(had) / len(had):.2f}  ({len(had)} runs)")
    for case_id in dict.fromkeys(r["id"] for r in runs):
        mine = [r for r in runs if r["id"] == case_id]
        print(f"  {case_id:<26} {sum(all(c['pass'] for c in r['checks'].values()) for r in mine)}/{len(mine)}")
    print(f"  {'ALL CHECKS PASS':<26} {sum(all(c['pass'] for c in r['checks'].values()) for r in runs) / len(runs):.2f}")
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"followups-{datetime.now():%Y%m%d-%H%M%S}.json"
    out.write_text(json.dumps(runs, indent=2, default=str))
    print(f"Full outputs: {out}")


if __name__ == "__main__":
    asyncio.run(main())
