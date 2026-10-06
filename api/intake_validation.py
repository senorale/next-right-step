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

from db import search_occupations, search_schools
from options import school_missing
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


MAX_SCHOOLS = 5  # the schools step lets the user keep at most this many
MAX_GUESSES = 3  # candidate schools per name the user typed
MAX_OPTIONS = 12  # schools shown on the picks step
SCHOOLS_SCHEMA = {
    "type": "object",
    "properties": {
        "schools": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "typed": {"type": "string", "description": "The school as the user wrote it"},
                    "candidates": {"type": "array", "items": {"type": "string"},
                                   "description": "Full official names of schools it could mean, most likely first"},
                },
                "required": ["typed", "candidates"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["schools"],
    "additionalProperties": False,
}
SCHOOLS_PROMPT = (
    f"For each college or university the user names, list up to {MAX_GUESSES} full official names of schools "
    "it could mean, most likely first (UF -> University of Florida, University of Findlay). Expand abbreviations, "
    "nicknames, and typos. A name that is already a full official name gets only that name; keep campus and "
    "online designations. Return an empty list if they name no school."
)


async def guess_schools(text: str) -> list[dict] | None:
    """[{"typed", "candidates"}] for each school named in free text; None when the model call fails."""
    try:
        response = await client.chat.completions.create(
            model=MODEL,
            max_tokens=512,
            temperature=0,
            messages=[{"role": "system", "content": SCHOOLS_PROMPT}, {"role": "user", "content": text}],
            response_format={"type": "json_schema", "json_schema": {"name": "schools", "schema": SCHOOLS_SCHEMA}},
        )
        named = json.loads(response.choices[0].message.content or "{}").get("schools", [])
        return [n for n in named if isinstance(n, dict) and n.get("typed")]
    except Exception:
        logger.exception("Guessing schools failed")
        return None


def _school_option(school: dict) -> dict:
    option = {"value": str(school["school_id"]), "label": f"{school['name']} ({school['city']}, {school['state']})",
              "name": school["name"]}
    missing = school_missing(school)
    if missing:
        option["disabled"] = True
        option["reason"] = (
            f"Can't be compared: College Scorecard has no {' or '.join(missing)} for this school, "
            "and the report needs both to compare cost and pay."
        )
    return option


def _find_schools(names: list[str]) -> list[dict]:
    """Schools in the data for each candidate name, best match first, no repeats.
    An exact name returns only that school; a partial one ("University of
    Texas") can return several."""
    found: dict[int, dict] = {}
    for name in names:
        for school in search_schools(name).get("results", [])[:2]:
            found.setdefault(school["school_id"], school)
    return list(found.values())


async def validate_target_schools(value: str, answers: dict) -> dict:
    """Path2 named schools. Finds every school each name could mean ("UF":
    University of Florida, University of Findlay) for the next step
    (school_picks), with the best comparable match for each name preselected.
    Schools without the data to compare are shown but can't be picked."""
    named = await guess_schools(value)
    if named is None:
        # Model call failed: search what the user typed.
        named = [{"typed": n.strip(), "candidates": [n.strip()]} for n in re.split(r",|;|\band\b", value) if n.strip()]
    if not named:
        return {"status": "fix", "message": "Which schools? Name each one, like University of Florida, Georgia Tech."}
    if len(named) > MAX_SCHOOLS:
        return {"status": "fix", "message": f"I can compare up to {MAX_SCHOOLS} schools. Remove {len(named) - MAX_SCHOOLS}."}

    options: dict[str, dict] = {}
    best: list[str] = []
    for item in named:
        guesses = [c for c in item.get("candidates") or [] if isinstance(c, str) and c.strip()][:MAX_GUESSES] or [item["typed"]]
        schools = await asyncio.to_thread(_find_schools, guesses)
        if not schools:
            return {"status": "fix", "message": f"I couldn't find \"{item['typed']}\". Check the spelling or use the school's full name."}
        for school in schools:
            options.setdefault(str(school["school_id"]), _school_option(school))
        comparable = [str(s["school_id"]) for s in schools if not options[str(s["school_id"])].get("disabled")]
        if comparable and comparable[0] not in best:
            best.append(comparable[0])
    # The best guesses lead, so they're never cut by MAX_OPTIONS.
    ordered = [options[v] for v in best] + [o for v, o in options.items() if v not in best]
    for option in ordered:
        option["preselect"] = option["value"] in best
    return {"status": "ok", "set": {"school_candidates": json.dumps(ordered[:MAX_OPTIONS])}}


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
    ("path2", "target_schools"): validate_target_schools,
    ("path4", "current_salary"): validate_salary,
}


async def validate_intake(key: str, value: str, answers: dict) -> dict:
    """Runs the check for this step, or passes it through when there is none."""
    check = VALIDATORS.get((answers.get("path_type"), key))
    if check is None or not value.strip():
        return {"status": "ok", "set": {}}
    return await check(value, answers)

