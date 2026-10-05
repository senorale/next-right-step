"""
Checks a free-text intake answer when the user submits that step, so problems
are fixed before any data is gathered (follow-up chat messages resend the same
intake, so it can't be corrected later).

Each check returns one of:
- {"status": "ok", "set": {...}}: continue; "set" adds normalized answers
  (e.g. the matched occupation code).
- {"status": "confirm", "message": ..., "choices": [...]}: the user picks one.
- {"status": "fix", "message": ..., "choices": [...]}: the user edits the
  answer; choices are optional ways out (e.g. switch to national medians).

A choice is {"label", "set": {...}, "clear": [...], "revalidate": bool}: the
frontend applies "set" and "clear" to the answers, then either revalidates the
step (when the choice replaced the answer itself) or moves on.

Checks are registered per (path_type, answer key) in VALIDATORS; the helpers
(extract_occupations, match_occupation) are meant for other paths' steps too.
"""

import asyncio
import json
import logging
import re

from db import search_occupations
from llm import MODEL, client
from user_numbers import _numbers_in, extract_user_numbers

logger = logging.getLogger(__name__)

OCCUPATIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "occupations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Each distinct job or career the user names, in their words",
        },
    },
    "required": ["occupations"],
    "additionalProperties": False,
}
OCCUPATIONS_PROMPT = (
    "List each distinct job or career the user names, in their own words. Several jobs listed together "
    "are separate entries. Return an empty list if they name no specific job (e.g. 'something that pays well')."
)


async def extract_occupations(text: str) -> list[str] | None:
    """Occupations named in free text; None when the model call fails."""
    try:
        response = await client.chat.completions.create(
            model=MODEL,
            max_tokens=256,
            messages=[{"role": "system", "content": OCCUPATIONS_PROMPT}, {"role": "user", "content": text}],
            response_format={"type": "json_schema", "json_schema": {"name": "occupations", "schema": OCCUPATIONS_SCHEMA}},
        )
        names = json.loads(response.choices[0].message.content or "{}").get("occupations", [])
        return [n.strip() for n in names if isinstance(n, str) and n.strip()]
    except Exception:
        logger.exception("Extracting occupations failed")
        return None


def _stem(text: str) -> str:
    return re.sub(r"s\b", "", text.lower()).strip()


def match_occupation(keyword: str, max_choices: int = 3) -> tuple[dict | None, list[dict]]:
    """O*NET search for one occupation. Returns (clear_match, candidates): a
    clear match when the top result's title contains what the user typed
    (e.g. "lawyer" and "Lawyers"), else up to max_choices candidates to confirm."""
    results = [r for r in search_occupations(keyword).get("results", []) if r.get("annual_salary")]
    if not results:
        return None, []
    top = results[0]
    if _stem(keyword) in _stem(top["title"]):
        return top, []
    return None, results[:max_choices]


def _occupation_choice(result: dict) -> dict:
    return {
        "label": f"{result['title']} (median ${result['annual_salary']:,.0f})",
        "set": {"occupation_code": result["soc_code"], "occupation_title": result["title"]},
        "revalidate": False,
    }


async def validate_single_occupation(value: str, answers: dict) -> dict:
    """Path1 compares one occupation against the high school, trade, and
    bachelor's benchmarks; several occupations belong in path4."""
    names = await extract_occupations(value)
    if names is None:
        # Model call failed: split on obvious separators rather than block the user.
        names = [n.strip() for n in re.split(r",|;|/|\band\b|\bor\b", value) if n.strip()]
    if not names:
        return {"status": "fix", "message": "Which job are you thinking about? Name one specific occupation, like nurse or electrician."}
    if len(names) > 1:
        return {
            "status": "confirm",
            "message": (
                "This comparison looks at one occupation against high school, trade, and bachelor's degree benchmarks. "
                "Pick one, or compare them side by side instead."
            ),
            "choices": [{"label": n, "set": {"occupation": n}, "revalidate": True} for n in names]
            + [{
                "label": "Compare them side by side",
                "set": {"path_type": "path4", "careers_to_compare": ", ".join(names)},
                "clear": ["data_source", "specific_numbers", "occupation"],
                "revalidate": False,
            }],
        }
    match, candidates = await asyncio.to_thread(match_occupation, names[0])
    if match:
        return {"status": "ok", "set": {"occupation_code": match["soc_code"], "occupation_title": match["title"]}}
    if not candidates:
        return {"status": "fix", "message": f"I couldn't find salary data for \"{names[0]}\". Try another name for the job."}
    return {
        "status": "confirm",
        "message": f"Which of these is closest to \"{names[0]}\"?",
        "choices": [_occupation_choice(c) for c in candidates],
    }


def _describe_numbers(numbers: dict) -> str:
    labels = {
        "undergrad_tuition_per_year": "undergrad tuition {}/yr",
        "graduate_tuition_per_year": "graduate tuition {}/yr",
        "total_education_cost": "total school cost {}",
        "expected_salary": "expected salary {}",
    }
    return ", ".join(labels[k].format(f"${v:,.0f}") for k, v in numbers.items() if k in labels)


async def validate_user_numbers(value: str, answers: dict) -> dict:
    """Path1 "specific numbers": confirm what we'll use, or ask again."""
    numbers = await extract_user_numbers(client, MODEL, value)
    if numbers is None:
        return {"status": "ok", "set": {}}  # model call failed; the report step extracts again
    if not numbers:
        return {
            "status": "fix",
            "message": "I couldn't find tuition or salary numbers in that. Add them, like \"tuition $12,000 a year, offer $95,000\".",
            "choices": [{"label": "Use national medians instead", "set": {"data_source": "medians"}, "clear": ["specific_numbers"], "revalidate": False}],
        }
    stored = {"user_numbers": json.dumps(numbers)}
    return {
        "status": "confirm",
        "message": f"I'll use: {_describe_numbers(numbers)}.",
        "choices": [
            {"label": "Looks right", "set": stored, "revalidate": False},
            {"label": "Let me edit", "edit": True},
        ],
    }


async def validate_salary(value: str, answers: dict) -> dict:
    """A yearly salary typed as text ("$55,000", "55k"). One number in a sane
    range; no model call needed."""
    salaries = [n for n in _numbers_in(value) if 10_000 <= n <= 1_000_000]
    if len(salaries) != 1:
        return {"status": "fix", "message": "Enter your yearly salary as one number, like $55,000."}
    return {"status": "ok", "set": {"current_salary_value": str(round(salaries[0]))}}


VALIDATORS = {
    ("path1", "occupation"): validate_single_occupation,
    ("path1", "specific_numbers"): validate_user_numbers,
    ("path4", "current_salary"): validate_salary,
}


async def validate_intake(key: str, value: str, answers: dict) -> dict:
    """Runs the check for this step, or passes it through when there is none."""
    check = VALIDATORS.get((answers.get("path_type"), key))
    if check is None or not value.strip():
        return {"status": "ok", "set": {}}
    return await check(value, answers)

