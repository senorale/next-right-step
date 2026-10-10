"""
Intake check eval (data gathering): runs each free-text answer in
intake_cases.jsonl through validate_intake() and compares the result with what
the step should hand off: status, normalized answers, and choices.

    api/venv/bin/python evals/intake.py
    api/venv/bin/python evals/intake.py --case occupation-multiple --repeats 3

Local runs use the free-tier key (api/llm.py). The occupation and numbers
checks call a model, so repeat cases to see how stable they are.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

import run  # noqa: F401  loads .env and puts api/ on the import path
from intake_validation import validate_intake

EVALS = Path(__file__).resolve().parent


def check(result: dict, expect: dict) -> list[str]:
    problems = []
    if result.get("status") != expect["status"]:
        problems.append(f"status {result.get('status')!r}, expected {expect['status']!r} ({result.get('message', '')})")
    candidates = json.loads((result.get("set") or {}).get("school_candidates") or "[]")
    picked = [int(o["value"]) for o in candidates if o.get("preselect")]
    if "preselected" in expect and picked != expect["preselected"]:
        problems.append(f"preselected {picked}, expected {expect['preselected']}")
    offered = {int(o["value"]) for o in candidates}
    problems += [f"not offered: {i}" for i in expect.get("offered_include", []) if i not in offered]
    disabled = {int(o["value"]) for o in candidates if o.get("disabled")}
    problems += [f"not marked ineligible: {i}" for i in expect.get("disabled_include", []) if i not in disabled]
    choices = result.get("choices") or []
    # What the step stores: "set" on ok, or the "Looks right" choice on a confirmation.
    stored_set = result.get("set") or next((c.get("set") or {} for c in choices if c.get("label") == "Looks right"), {})
    for key, value in expect.get("set", {}).items():
        if stored_set.get(key) != value:
            problems.append(f"set.{key} = {stored_set.get(key)!r}, expected {value!r}")
    if "career_codes" in expect:
        codes = sorted(m["soc_code"] for m in json.loads(stored_set.get("career_matches") or "[]"))
        if codes != sorted(expect["career_codes"]):
            problems.append(f"career codes {codes}, expected {sorted(expect['career_codes'])}")
    items = (result.get("picks") or {}).get("items") or []
    if "pick_matched" in expect:
        matched = sorted(i["match"]["soc_code"] for i in items if i.get("match"))
        if matched != sorted(expect["pick_matched"]):
            problems.append(f"picks matched {matched}, expected {sorted(expect['pick_matched'])}")
    if "pick_unclear" in expect:
        unclear = sorted(i["typed"].lower() for i in items if not i.get("match"))
        if unclear != sorted(expect["pick_unclear"]):
            problems.append(f"picks unclear {unclear}, expected {sorted(expect['pick_unclear'])}")
    if "program_list" in expect:
        programs = json.loads(stored_set.get("program_list") or "null")
        if programs != expect["program_list"]:
            problems.append(f"program_list {programs}, expected {expect['program_list']}")
    labels = [c.get("label", "").lower() for c in choices]
    problems += [f"no choice {want!r}" for want in expect.get("choices_include", []) if want.lower() not in labels]
    # Occupation choices store the code under the step's key (occupation_code, target_career_code, ...).
    codes = [v for c in choices for k, v in (c.get("set") or {}).items() if k.endswith("_code")]
    problems += [f"no choice for {code}" for code in expect.get("choice_codes_include", []) if code not in codes]
    if "choice_count" in expect and len(choices) != expect["choice_count"]:
        problems.append(f"{len(choices)} choices, expected {expect['choice_count']}: {labels}")
    if expect.get("switch_to") and not any((c.get("set") or {}).get("path_type") == expect["switch_to"] for c in choices):
        problems.append(f"no choice to switch to {expect['switch_to']}")
    if "draft" in expect and not any(c.get("draft") == expect["draft"] for c in choices):
        problems.append(f"no choice drafting {expect['draft']}")
    if "user_numbers" in expect:
        stored = next((json.loads(c["set"]["user_numbers"]) for c in choices if "user_numbers" in (c.get("set") or {})), {})
        if stored != expect["user_numbers"]:
            problems.append(f"user_numbers {stored}, expected {expect['user_numbers']}")
    return problems


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", help="run only the case with this id")
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()

    cases = [json.loads(l) for l in (EVALS / "intake_cases.jsonl").read_text().splitlines() if l.strip()]
    if args.case:
        cases = [c for c in cases if c["id"] == args.case] or sys.exit(f"No case {args.case!r}")

    passed = total = 0
    for case in cases:
        for _ in range(args.repeats):
            result = await validate_intake(case["key"], case["value"], case["answers"])
            problems = check(result, case["expect"])
            total += 1
            passed += not problems
            print(f"{'PASS' if not problems else 'FAIL'} {case['id']}" + ("" if not problems else f": {problems}"), flush=True)
    print(f"\n{passed}/{total} passed")


if __name__ == "__main__":
    asyncio.run(main())
