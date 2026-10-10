"""
Checks a free-text intake answer when the user submits that step, so problems
are fixed before any data is gathered (follow-up chat messages resend the same
intake, so it can't be corrected later).

Every free-text answer is confirmed before the intake moves on: the user sees
how it was understood (the matched occupation, school, programs, ...) and
either accepts it or edits the answer. Each check returns one of:
- {"status": "confirm", "message": ..., "choices": [...]}: the user picks one.
  Usually "Looks right" (whose "set" stores the normalized answers, e.g. the
  matched occupation code) or "Let me edit"; when the answer could mean
  several things, one choice per meaning.
- {"status": "fix", "message": ..., "choices": [...]}: the user edits the
  answer; choices are optional ways out (e.g. switch to national medians).
- {"status": "ok", "set": {...}}: continue. Only target_schools returns it,
  because the school_picks step that follows is its confirmation.

A choice is {"label", "set": {...}, "clear": [...], "draft": {...},
"revalidate": bool, "edit": bool}: the frontend applies "set" and "clear" to
the answers, prefills later steps with "draft", then either revalidates the
step (when the choice replaced the answer itself) or moves on. "edit" returns
the user to the answer.

Checks are registered per (path_type, answer key) in VALIDATORS, or per
(None, key) for a step several paths share. A free-text step with no check
still gets a plain confirmation.
"""

import asyncio
import json
import logging
import re

from db import school_program_titles, search_occupations, search_schools
from options import school_missing
from llm import MODEL, client
from user_numbers import _numbers_in, extract_user_numbers

logger = logging.getLogger(__name__)


def _confirm(message: str, set_: dict | None = None) -> dict:
    """Shows how the answer was understood; "Looks right" stores set_ and moves on."""
    return {
        "status": "confirm",
        "message": message,
        "choices": [
            {"label": "Looks right", "set": set_ or {}, "revalidate": False},
            {"label": "Let me edit", "edit": True},
        ],
    }


async def _ask_json(name: str, schema: dict, prompt: str, text: str, max_tokens: int = 256) -> dict | None:
    """One structured model call over the user's answer; None when it fails."""
    try:
        response = await client.chat.completions.create(
            model=MODEL,
            max_tokens=max_tokens,
            temperature=0,
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": text}],
            response_format={"type": "json_schema", "json_schema": {"name": name, "schema": schema}},
        )
        parsed = json.loads(response.choices[0].message.content or "{}")
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        logger.exception("Intake model call %s failed", name)
        return None


def _split(value: str) -> list[str]:
    """Names in a list the user typed, for when the model call fails."""
    return [n.strip() for n in re.split(r",|;|/|\band\b|\bor\b", value) if n.strip()]


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


def _salary(result: dict) -> str:
    return f"median ${result['annual_salary']:,.0f}"


def _occupation_set(result: dict, keys: tuple[str, str]) -> dict:
    code_key, title_key = keys
    return {code_key: result["soc_code"], title_key: result["title"]}


def _occupation_choice(result: dict, keys: tuple[str, str]) -> dict:
    return {"label": f"{result['title']} ({_salary(result)})", "set": _occupation_set(result, keys), "revalidate": False}


async def _validate_one_occupation(value: str, key: str, keys: tuple[str, str], ask: str,
                                   switch_clear: list[str], what: str) -> dict:
    """One occupation, matched to O*NET and confirmed. Several occupations:
    pick one, or switch to path4 to compare them (the careers step is
    prefilled and checked there). keys names the (code, title) answers to set;
    what describes the comparison for the "pick one" message."""
    names = await extract_occupations(value)
    if names is None:
        # Model call failed: split on obvious separators rather than block the user.
        names = _split(value)
    if not names:
        return {"status": "fix", "message": ask}
    if len(names) > 1:
        return {
            "status": "confirm",
            "message": f"{what} Pick one, or compare them side by side instead.",
            "choices": [{"label": n, "set": {key: n}, "revalidate": True} for n in names]
            + [{
                "label": "Compare them side by side",
                "set": {"path_type": "path4"},
                "clear": switch_clear,
                "draft": {"careers_to_compare": ", ".join(names)},
                "revalidate": False,
            }],
        }
    match, candidates = await asyncio.to_thread(match_occupation, names[0])
    if match:
        return _confirm(f"I'll use {match['title']} ({_salary(match)}).", _occupation_set(match, keys))
    if not candidates:
        return {"status": "fix", "message": f"I couldn't find salary data for \"{names[0]}\". Try another name for the job."}
    return {
        "status": "confirm",
        "message": f"Which of these is closest to \"{names[0]}\"?",
        "choices": [_occupation_choice(c, keys) for c in candidates],
    }


async def validate_single_occupation(value: str, answers: dict) -> dict:
    """Path1 compares one occupation against the high school, trade, and
    bachelor's benchmarks; several occupations belong in path4."""
    return await _validate_one_occupation(
        value, "occupation", ("occupation_code", "occupation_title"),
        ask="Which job are you thinking about? Name one specific occupation, like nurse or electrician.",
        switch_clear=["data_source", "specific_numbers", "occupation", "user_numbers"],
        what="This comparison looks at one occupation against high school, trade, and bachelor's degree benchmarks.",
    )


async def validate_target_career(value: str, answers: dict) -> dict:
    """Path5 maps the way to one career; several belong in path4."""
    return await _validate_one_occupation(
        value, "target_career", ("target_career_code", "target_career_title"),
        ask="Which career do you want to reach? Name one, like pharmacist or electrician.",
        switch_clear=["target_career"],
        what="This maps out the path to one career.",
    )


async def validate_current_role(value: str, answers: dict) -> dict:
    """The user's current job (path4 and path5). A role O*NET doesn't know is
    kept as typed, since it only labels the user's starting point."""
    keys = ("current_role_code", "current_role_title")
    names = await extract_occupations(value)
    if names is None:
        names = [value.strip()]
    if not names:
        return {"status": "fix", "message": "What's your job? Name it, like retail manager or IT support."}
    if len(names) > 1:
        return {
            "status": "confirm",
            "message": "Which one is your main job?",
            "choices": [{"label": n, "set": {"current_role": n}, "revalidate": True} for n in names],
        }
    name = names[0]
    as_typed = {"label": f"Keep \"{name}\"", "set": {"current_role_title": name}, "revalidate": False}
    match, candidates = await asyncio.to_thread(match_occupation, name)
    if match:
        return _confirm(f"Your current job: {match['title']} ({_salary(match)}).", _occupation_set(match, keys))
    if not candidates:
        return _confirm(f"Your current job: {name}.", {"current_role_title": name})
    return {
        "status": "confirm",
        "message": f"Which of these is closest to \"{name}\"?",
        "choices": [_occupation_choice(c, keys) for c in candidates] + [as_typed],
    }


async def validate_careers_to_compare(value: str, answers: dict) -> dict:
    """Path4 careers, each matched to O*NET in one pass (one model call, the
    lookups in parallel). When some are unclear, "picks" carries every career:
    the match, or the candidates to pick from. The frontend asks about the
    unclear ones one at a time, confirms the whole list, and stores
    career_matches, with no further calls."""
    names = await extract_occupations(value)
    if names is None:
        names = _split(value)
    if len(names) < 2:
        return {"status": "fix", "message": "Name at least two careers to compare, separated by commas."}
    found = await asyncio.gather(*(asyncio.to_thread(match_occupation, n) for n in names))

    def entry(typed: str, result: dict) -> dict:
        return {"typed": typed, "soc_code": result["soc_code"], "title": result["title"]}

    items = []
    for name, (match, candidates) in zip(names, found):
        if match:
            items.append({"typed": name, "match": entry(name, match)})
        elif candidates:
            items.append({"typed": name, "options": [{"label": f"{c['title']} ({_salary(c)})", "entry": entry(name, c)}
                                                      for c in candidates]})
        else:
            return {"status": "fix", "message": f"I couldn't find salary data for \"{name}\". Try another name for that career."}
    if all("match" in i for i in items):
        unique = list({i["match"]["soc_code"]: i["match"] for i in items}.values())
        if len(unique) < 2:
            return {"status": "fix", "message": f"Those all match {unique[0]['title']}. Name at least two different careers."}
        return _confirm(f"I'll compare: {', '.join(m['title'] for m in unique)}.", {"career_matches": json.dumps(unique)})
    return {"status": "confirm", "picks": {"key": "career_matches", "items": items}}


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
        # Model call failed; the report step extracts again.
        return _confirm(f"I'll use the numbers you gave: \"{value.strip()}\".")
    if not numbers:
        return {
            "status": "fix",
            "message": "I couldn't find tuition or salary numbers in that. Add them, like \"tuition $12,000 a year, offer $95,000\".",
            "choices": [{"label": "Use national medians instead", "set": {"data_source": "medians"}, "clear": ["specific_numbers"], "revalidate": False}],
        }
    return _confirm(f"I'll use: {_describe_numbers(numbers)}.", {"user_numbers": json.dumps(numbers)})


async def validate_salary(value: str, answers: dict) -> dict:
    """A yearly salary typed as text ("$55,000", "55k"). One number in a sane
    range; no model call needed."""
    salaries = [n for n in _numbers_in(value) if 10_000 <= n <= 1_000_000]
    if len(salaries) != 1:
        return {"status": "fix", "message": "Enter your yearly salary as one number, like $55,000."}
    salary = round(salaries[0])
    return _confirm(f"I'll use ${salary:,} a year.", {"current_salary_value": str(salary)})


def _school_label(school: dict) -> str:
    return f"{school['name']} ({school['city']}, {school['state']})"


def _school_set(school: dict) -> dict:
    return {"school_id": str(school["school_id"]), "school_matched_name": school["name"]}


async def validate_school_name(value: str, answers: dict) -> dict:
    """Path3: the one school whose programs get compared."""
    named = await guess_schools(value)
    if named is None:
        named = [{"typed": value.strip(), "candidates": [value.strip()]}]
    if not named:
        return {"status": "fix", "message": "Which school? Name it, like University of Florida."}
    if len(named) > 1:
        return {"status": "fix", "message": "Name one school. To compare schools, go back and pick \"comparing schools\"."}
    item = named[0]
    guesses = [c for c in item.get("candidates") or [] if isinstance(c, str) and c.strip()][:MAX_GUESSES] or [item["typed"]]
    schools = (await asyncio.to_thread(_find_schools, guesses))[:4]
    if not schools:
        return {"status": "fix", "message": f"I couldn't find \"{item['typed']}\". Check the spelling or use the school's full name."}
    if len(schools) == 1:
        return _confirm(f"I'll use {_school_label(schools[0])}.", _school_set(schools[0]))
    return {
        "status": "confirm",
        "message": f"Which school do you mean by \"{item['typed']}\"?",
        "choices": [{"label": _school_label(s), "set": _school_set(s), "revalidate": False} for s in schools],
    }


PROGRAMS_SCHEMA = {
    "type": "object",
    "properties": {
        "not_sure": {"type": "boolean", "description": "True if the user isn't sure which programs and names none"},
        "programs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "typed": {"type": "string", "description": "The program as the user wrote it"},
                    "title": {"type": "string", "description": "The school's program title it means, copied exactly, or empty if none fits"},
                },
                "required": ["typed", "title"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["not_sure", "programs"],
    "additionalProperties": False,
}
PROGRAMS_PROMPT = (
    "The user names programs or majors at a school. For each one, give the program title from the school's list "
    "below that it means (CS -> Computer Science; pre-med -> Biology, General), copied exactly, or an empty title "
    "if none fits. Set not_sure when they say they aren't sure and name no program.\n\nThe school's programs:\n"
)


async def validate_programs(value: str, answers: dict) -> dict:
    """Path3 programs, matched to the programs the chosen school offers.
    "Not sure" is confirmed as the school's top programs."""
    school = answers.get("school_matched_name") or answers.get("school_name") or "your school"
    titles = None
    if (answers.get("school_id") or "").isdigit():
        titles = await asyncio.to_thread(school_program_titles, int(answers["school_id"]))
    parsed = await _ask_json("programs", PROGRAMS_SCHEMA, PROGRAMS_PROMPT + "\n".join(titles or []), value, max_tokens=512)
    if parsed is None:
        return _confirm(f"I'll compare: {value.strip()}.", {"program_list": json.dumps(_split(value))})
    named = [p for p in parsed.get("programs") or [] if isinstance(p, dict) and (p.get("typed") or "").strip()]
    if parsed.get("not_sure") and not named:
        return _confirm(f"I'll show the top programs at {school}.", {"program_list": "[]"})
    if not named:
        return {"status": "fix", "message": "Which programs? Name them, like computer science, biology, or say \"not sure\"."}
    if not titles:
        # No program list for this school: confirm the names as typed.
        return _confirm(f"I'll compare: {', '.join(p['typed'] for p in named)}.",
                        {"program_list": json.dumps([p["typed"] for p in named])})
    offered = set(titles)
    found = list(dict.fromkeys(p["title"] for p in named if p.get("title") in offered))
    missing = [p["typed"] for p in named if p.get("title") not in offered]
    if not missing:
        return _confirm(f"I'll compare at {school}: {'; '.join(found)}.", {"program_list": json.dumps(found)})
    message = f"I couldn't find {', '.join(missing)} at {school}. Check the name, or use another program."
    choices = [{"label": f"Continue with {'; '.join(found)}", "set": {"program_list": json.dumps(found)}, "revalidate": False}] if found else []
    return {"status": "fix", "message": message, "choices": choices}


US_STATES = set(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND "
    "OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY AS GU MP PR VI".split()
)
PLACES_SCHEMA = {
    "type": "object",
    "properties": {
        "places": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "The state or city, spelled out (Miami, California)"},
                    "kind": {"type": "string", "enum": ["state", "city"]},
                    "state": {"type": "string", "description": "Two-letter US postal code of its state"},
                },
                "required": ["name", "kind", "state"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["places"],
    "additionalProperties": False,
}
PLACES_PROMPT = (
    "List each US state or city the user names, with the two-letter postal code of its state "
    "(Miami -> FL, Cali -> California, CA). Return an empty list if they name no US place."
)


async def validate_target_location(value: str, answers: dict) -> dict:
    """Path2 without named schools: the states (and cities) to search."""
    parsed = await _ask_json("places", PLACES_SCHEMA, PLACES_PROMPT, value)
    if parsed is None:
        return _confirm(f"I'll look for schools in {value.strip()}.")
    places = [p for p in parsed.get("places") or []
              if isinstance(p, dict) and (p.get("name") or "").strip() and (p.get("state") or "").upper() in US_STATES]
    if not places:
        return {"status": "fix", "message": "Which US states or cities? Name at least one, like Florida or Austin, TX."}
    labels = list(dict.fromkeys(
        p["name"].strip() if p.get("kind") == "state" else f"{p['name'].strip()}, {p['state'].upper()}" for p in places
    ))
    states = ",".join(dict.fromkeys(p["state"].upper() for p in places))
    return _confirm(f"I'll look for schools in {'; '.join(labels)}.",
                    {"target_places": "; ".join(labels), "target_states": states})


FIELD_SCHEMA = {
    "type": "object",
    "properties": {
        "field": {"type": "string", "description": "The field of study, as a common program name, or empty if none"},
    },
    "required": ["field"],
    "additionalProperties": False,
}
FIELD_PROMPT = (
    "Give the field of study the user names, as a common program or major name (psych -> Psychology, "
    "CS -> Computer Science). Use Undeclared if they haven't picked one. Empty if they name no field."
)


async def validate_current_field(value: str, answers: dict) -> dict:
    """What the user studies or studied (path4 and path5)."""
    parsed = await _ask_json("field", FIELD_SCHEMA, FIELD_PROMPT, value)
    field = value.strip() if parsed is None else (parsed.get("field") or "").strip()
    if not field:
        return {"status": "fix", "message": "What's the field? Name it, like psychology, nursing, or undeclared."}
    return _confirm(f"Field of study: {field}.", {"current_field_normalized": field})


VALIDATORS = {
    ("path1", "occupation"): validate_single_occupation,
    ("path1", "specific_numbers"): validate_user_numbers,
    ("path2", "target_schools"): validate_target_schools,
    ("path2", "target_location"): validate_target_location,
    ("path3", "school_name"): validate_school_name,
    ("path3", "programs"): validate_programs,
    ("path4", "careers_to_compare"): validate_careers_to_compare,
    ("path4", "current_salary"): validate_salary,
    ("path5", "target_career"): validate_target_career,
    (None, "current_field"): validate_current_field,
    (None, "current_role"): validate_current_role,
}


async def validate_intake(key: str, value: str, answers: dict) -> dict:
    """Runs the check for this step. A step with no check is still confirmed."""
    if not value.strip():
        return {"status": "fix", "message": "Type an answer to continue."}
    check = VALIDATORS.get((answers.get("path_type"), key)) or VALIDATORS.get((None, key))
    if check is None:
        return _confirm(f"I'll use: \"{value.strip()}\".")
    return await check(value, answers)
