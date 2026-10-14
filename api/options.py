"""
Option rows: the things a report compares (an occupation, a school, a program,
an education path), built in code from tool data so every number a report shows
or states comes from code, never from the model.

Data tools attach their rows under "options". The report model picks rows by
option_id and writes the text; code renders the charts and tables from the rows
it picked, and supplies the gap between every pair of rows so the model never
subtracts.

Every row has the same core fields, which the financial breakdown reads:
option_id, name, short_label, education, years_in_school, debt (total cost of
school, median student debt unless cost_basis says otherwise), cost_basis,
expected_salary, salary_basis. Extra facts go in "metrics" (see
report.METRIC_FORMATS), which the report can show as a table.
"""

import json
import logging

from career_cost import BACHELOR_SALARY, BACHELOR_YEARS, HS_SALARY, career_cost, career_option, national_bachelors_debt
from db import cip_occupations, school_programs

logger = logging.getLogger(__name__)

MAX_OCCUPATION_ROWS = 3  # per search: the top matches with a salary
MAX_PROGRAM_ROWS = 6  # per call: the highest-earning matches
TOP_PROGRAMS = 4  # path3 "not sure": the school's top bachelor's programs
PROGRAM_OCCUPATIONS = 3  # path3: occupations shown per program, highest paid first
MAX_CANDIDATES = 20  # rows sent to the report model (pairwise gaps grow fast)

AMOUNT_METRICS = ("avg_net_price", "tuition_in_state", "tuition_out_of_state", "median_debt",
                  "earnings_6yr_after_entry", "earnings_10yr_after_entry", "student_size")
RATE_METRICS = ("graduation_rate", "admission_rate", "retention_rate", "loan_repayment_rate_3yr")
SCHOOL_YEARS = {"certificate": 1, "associate": 2, "bachelor": 4, "graduate": 2}
# Length of the program itself, by Scorecard credential level.
PROGRAM_YEARS = {1: 1, 2: 2, 3: 4, 4: 1, 5: 2, 6: 5, 7: 4, 8: 1}
# Total years of school by credential level, for the occupations a program
# leads to (YEARS_BY_CREDENTIAL in src/app/api/schools/[id]/programs/route.ts).
YEARS_BY_CREDENTIAL = {1: 1, 2: 2, 3: 4, 4: 5, 5: 6, 6: 8, 7: 8, 8: 6}


# The user's own choices, enforced by code rather than left to the report model
# (like path1's fixed rows): which metrics to show (compare_metrics) and how to
# order the options (rank_by). Keys are the intake labels in src/app/chat/page.tsx.
CHOICE_METRICS = {
    "Earnings after graduation": ["earnings_6yr_after_entry", "earnings_10yr_after_entry"],
    "Net price / cost": ["avg_net_price", "tuition_in_state", "tuition_out_of_state"],
    "Graduation rate": ["graduation_rate"],
    "Debt at graduation": ["median_debt"],
    "Admission rate": ["admission_rate"],
    "Retention rate": ["retention_rate"],
    "Loan repayment rate": ["loan_repayment_rate_3yr"],
}
ALWAYS_SHOWN_METRICS = ["median_debt"]  # the cost behind every payoff, chosen or not
# rank_by -> (row field or metric, highest first)
RANK_ORDER = {
    "Earnings after graduation": ("expected_salary", True),
    "Net price / cost": ("avg_net_price", False),
    "Graduation rate": ("graduation_rate", True),
    "Debt at graduation": ("median_debt", False),
    "Admission rate": ("admission_rate", False),
    "Retention rate": ("retention_rate", True),
    "Loan repayment rate": ("loan_repayment_rate_3yr", True),
}
# path3 program_priority -> (row field or metric, highest first). "Job demand"
# (O*NET bright outlook) has no local data, so it isn't ranked in code.
PRIORITY_ORDER = {
    "Earning potential": ("expected_salary", True),
    "Many career options": ("career_options", True),
}


def _choices(intake_answers: dict | None) -> list[str]:
    return [m for m in ((intake_answers or {}).get("compare_metrics") or "").split("|") if m in CHOICE_METRICS]


def allowed_metrics(intake_answers: dict | None) -> list[str] | None:
    """Metric keys the report may show as table columns; None = any."""
    chosen = _choices(intake_answers)
    if not chosen:
        return None
    return list(dict.fromkeys([k for m in chosen for k in CHOICE_METRICS[m]] + ALWAYS_SHOWN_METRICS))


def _value(row: dict, key: str):
    return row.get(key) if key in row else (row.get("metrics") or {}).get(key)


def rank_order(intake_answers: dict | None) -> tuple[str, bool, str | None] | None:
    """(row field or metric, highest first, option_id prefix of the rows
    ranked) for the user's ranking choice, or None. path2 ranks by rank_by (the
    only chosen metric counts as rank_by); path3 ranks programs by
    program_priority, leaving the occupations they lead to in place."""
    answers = intake_answers or {}
    if answers.get("path_type") == "path3":
        order = PRIORITY_ORDER.get(answers.get("program_priority"))
        return (*order, "program:") if order else None
    chosen = _choices(answers)
    rank = answers.get("rank_by") or (chosen[0] if len(chosen) == 1 else None)
    return (*RANK_ORDER[rank], None) if rank in RANK_ORDER else None


def rank_rows(options: list[dict], intake_answers: dict | None) -> list[dict]:
    """Orders the options that have the user's ranking metric (rank_order);
    others (baselines) keep their places."""
    order = rank_order(intake_answers)
    if not order:
        return options
    key, highest_first, prefix = order
    slots = [i for i, o in enumerate(options) if not o["option_id"].startswith("baseline:")
             and (prefix is None or o["option_id"].startswith(prefix)) and _value(o, key) is not None]
    ranked = sorted((options[i] for i in slots), key=lambda o: _value(o, key), reverse=highest_first)
    ordered = list(options)
    for i, row in zip(slots, ranked):
        ordered[i] = row
    return ordered


def baseline_rows(intake_answers: dict | None) -> list[dict]:
    """Rows every report can compare against: high school, the bachelor's
    median, and the user's current salary when they gave one."""
    rows = [
        {
            "option_id": "baseline:hs",
            "name": "High school diploma",
            "short_label": "HS diploma",
            "education": "High school diploma",
            "years_in_school": 0,
            "debt": 0,
            "cost_basis": "No school required",
            "expected_salary": HS_SALARY,
            "salary_basis": "BLS median weekly earnings x 52",
        },
        {
            "option_id": "baseline:bachelors",
            "name": "Bachelor's degree (median)",
            "short_label": "Bachelor's",
            "education": "Bachelor's degree",
            "years_in_school": BACHELOR_YEARS,
            "debt": national_bachelors_debt(),
            "cost_basis": "National median bachelor's debt across all degree fields",
            "expected_salary": BACHELOR_SALARY,
            "salary_basis": "BLS median weekly earnings x 52",
        },
    ]
    try:
        current = float((intake_answers or {}).get("current_salary_value") or 0)
    except ValueError:
        current = 0
    if current > 0:
        role = (intake_answers or {}).get("current_role")
        rows.append({
            "option_id": "baseline:current",
            "name": f"Your current job ({role})" if role else "Your current job",
            "short_label": "Current job",
            "education": "No more school",
            "years_in_school": 0,
            "debt": 0,
            "cost_basis": "No school required",
            "expected_salary": current,
            "salary_basis": "Your current salary",
            "user_numbers": True,
        })
    return rows


def occupation_rows(result: dict) -> list[dict]:
    """search_occupations: the top matches with a salary, with years of school
    and median debt from career_cost."""
    rows, seen = [], set()
    for match in result.get("results") or []:
        if len(rows) == MAX_OCCUPATION_ROWS:
            break
        # O*NET lists specialties under one SOC code (29-1141.01, .02, ...).
        if not match.get("annual_salary") or match["soc_code"] in seen:
            continue
        seen.add(match["soc_code"])
        try:
            cost = career_cost(match["soc_code"])
        except Exception:
            logger.exception("career_cost failed for %s", match.get("soc_code"))
            continue
        if cost:
            row = career_option(cost)
            row["metrics"] = {"bright_outlook": bool(match.get("bright_outlook"))}
            rows.append(row)
    return rows


def school_missing(school: dict) -> list[str]:
    """What a school lacks for a comparison: earnings (every salary and payoff)
    and median debt (the education cost; without it payoff looks instant)."""
    missing = []
    if not (school.get("earnings_10yr_after_entry") or school.get("earnings_6yr_after_entry")):
        missing.append("earnings after graduation")
    if not school.get("median_debt"):
        missing.append("median debt at graduation")
    return missing


def school_rows(result: dict, degree_type: str | None) -> list[dict]:
    """search_schools: each school with the data to compare (school_missing).
    Cost is the school's median debt at graduation; salary is students'
    earnings 10 years after entry."""
    years = SCHOOL_YEARS.get((degree_type or "bachelor").lower(), BACHELOR_YEARS)
    rows = []
    for s in result.get("results") or []:
        if school_missing(s):
            continue
        salary = s.get("earnings_10yr_after_entry") or s.get("earnings_6yr_after_entry")
        rows.append({
            "option_id": f"school:{s['school_id']}",
            "name": s["name"],
            "state": s.get("state"),
            "short_label": s["name"],
            "education": f"{s.get('type') or ''} school, {s.get('city')}, {s.get('state')}".strip(", "),
            "years_in_school": years,
            "debt": s["median_debt"],
            "cost_basis": "This school's median debt at graduation (College Scorecard)",
            "expected_salary": salary,
            "salary_basis": "College Scorecard median earnings of this school's students "
            + ("10" if s.get("earnings_10yr_after_entry") else "6") + " years after entry",
            "metrics": {
                **{k: s[k] for k in AMOUNT_METRICS if s.get(k) is not None},
                # Scorecard rates are fractions; percents read (and get copied) as written.
                **{k: round(s[k] * 100, 1) for k in RATE_METRICS if s.get(k) is not None},
            },
        })
    return rows


def _program_row(p: dict, school_id, school: str) -> dict:
    """One program at a school. Cost is the program's median debt (else the
    national median for the field and credential); salary is its graduates'
    earnings 4 years out (else 1 year)."""
    salary = p.get("earnings_4yr_after_graduation") or p.get("earnings_1yr_after_graduation")
    level = p.get("credential_level")
    if p.get("median_debt"):
        debt, basis = p["median_debt"], f"Median debt for this program at {school} (College Scorecard)"
    elif p.get("national_median_debt"):
        debt, basis = p["national_median_debt"], f"National median debt for a {p['credential'].lower()} in this field ({school} reports none)"
    else:
        debt, basis = 0, "No debt data for this program"
    return {
        "option_id": f"program:{school_id}:{p['cip_code']}:{level}",
        "name": f"{p['title']} ({p['credential']})",
        "short_label": p["title"],
        "education": f"{p['credential']} at {school}",
        "years_in_school": PROGRAM_YEARS.get(level, BACHELOR_YEARS),
        "debt": debt,
        "cost_basis": basis,
        "expected_salary": salary,
        "salary_basis": "College Scorecard median earnings of this program's graduates "
        + ("4 years" if p.get("earnings_4yr_after_graduation") else "1 year") + " after graduating",
        "metrics": {k: p.get(k) for k in ("earnings_1yr_after_graduation", "earnings_4yr_after_graduation")
                    if p.get(k) is not None},
    }


def program_rows(result: dict) -> list[dict]:
    """get_school_programs: the highest-earning programs."""
    school = result.get("school_name") or "this school"
    return [_program_row(p, result.get("school_id"), school) for p in (result.get("programs") or [])[:MAX_PROGRAM_ROWS]]


def _has_earnings(p: dict) -> bool:
    return bool(p.get("earnings_4yr_after_graduation") or p.get("earnings_1yr_after_graduation"))


def _reachable(occupations: list[dict], level: int) -> list[dict]:
    """Occupations a graduate of this credential can typically enter (typical
    years of school within the credential's), one per SOC code."""
    years = YEARS_BY_CREDENTIAL.get(level)
    seen, out = set(), []
    for o in occupations:
        if o["soc_code"] in seen or (years is not None and (o.get("typical_years_of_school") or 0) > years):
            continue
        seen.add(o["soc_code"])
        out.append(o)
    return out


def path3_options(school_id: int, program_titles: list[str] | None, program_priority: str | None = None) -> dict:
    """compare_programs: the programs the user confirmed at their school (else
    the school's top bachelor's programs), each at its lowest credential with
    earnings data, and the occupations each leads to (CIP-SOC crosswalk) as
    occupation rows. The intake turns away programs without earnings."""
    result = school_programs(school_id)
    if "error" in result:
        return result
    school = result["school_name"] or "this school"
    programs = result["programs"]
    chosen = []
    if program_titles:
        for title in dict.fromkeys(program_titles):
            levels = [p for p in programs if p["title"].lower() == title.lower() and _has_earnings(p)]
            if levels:
                chosen.append(min(levels, key=lambda p: p["credential_level"]))
    else:
        chosen = [p for p in programs if p["credential_level"] == 3 and _has_earnings(p)]

    linked = cip_occupations(sorted({p["cip_code"] for p in chosen}))
    rows, occupation_rows_by_id = [], {}
    for p in chosen:
        row = _program_row(p, school_id, school)
        reachable = _reachable(linked.get(p["cip_code"], []), p["credential_level"])
        row["metrics"]["career_options"] = len(reachable)
        row["leads_to"] = []
        for o in reachable[:PROGRAM_OCCUPATIONS]:
            occ_id = f"occ:{o['soc_code']}"
            if occ_id not in occupation_rows_by_id:
                cost = career_cost(o["soc_code"])
                if not cost:
                    continue
                occupation_rows_by_id[occ_id] = career_option(cost)
            row["leads_to"].append(occ_id)
        rows.append(row)

    if not program_titles:
        # "Not sure": the top programs by what matters most to the user.
        key, _, _ = rank_order({"path_type": "path3", "program_priority": program_priority}) or ("expected_salary", True, None)
        rows = sorted(rows, key=lambda r: _value(r, key) or 0, reverse=True)[:TOP_PROGRAMS]
        keep = {i for r in rows for i in r["leads_to"]}
        occupation_rows_by_id = {k: v for k, v in occupation_rows_by_id.items() if k in keep}

    return {"school_id": school_id, "school_name": result["school_name"],
            "options": rows + list(occupation_rows_by_id.values())}


def includes_current_role(intake_answers: dict | None) -> bool:
    """path4: whether the user's matched current job is one of the careers compared."""
    answers = intake_answers or {}
    return bool(answers.get("current_role_code")) and "no" not in (
        answers.get("include_current_role"), answers.get("compare_to_current"))


def current_pay(intake_answers: dict | None) -> float | None:
    """path4: the yearly pay the user gave for their current job, if they chose to."""
    answers = intake_answers or {}
    if not includes_current_role(answers) or answers.get("include_salary") != "yes":
        return None
    try:
        pay = float(answers.get("current_salary_value") or 0)
    except ValueError:
        return None
    return pay if pay > 0 else None


def current_job_ids(intake_answers: dict | None) -> list[str]:
    """path4: the rows that stand for the user's current job. With their pay,
    a "current:pay" row, plus the job's national median if they asked for it;
    without, the median row alone."""
    answers = intake_answers or {}
    if not includes_current_role(answers):
        return []
    median = f"occ:{answers['current_role_code']}"
    if current_pay(answers) is None:
        return [median]
    return ["current:pay"] + ([median] if answers.get("compare_to_median") == "yes" else [])


def path4_options(intake_answers: dict) -> dict:
    """compare_careers: the careers the user confirmed (career_matches), each at
    its national median, and their current job when they included it: at their
    own pay if they gave it, at the national median otherwise or when they also
    asked for the median."""
    careers = [c for c in _parse_list(intake_answers.get("career_matches")) or [] if isinstance(c, dict) and c.get("soc_code")]
    codes = [c["soc_code"] for c in careers]
    if includes_current_role(intake_answers):
        codes.append(intake_answers["current_role_code"])
    current = intake_answers.get("current_role_code") if includes_current_role(intake_answers) else None
    rows, missing = [], []
    for code in dict.fromkeys(codes):
        cost = career_cost(code)
        if not cost:
            missing.append(code)
            continue
        row = career_option(cost)
        if code == current:
            # Named for the user, so the report says "your current job", not only the O*NET title.
            pay = current_pay(intake_answers)
            if pay is not None:
                rows.append({**row, "option_id": "current:pay", "name": f"Your current job ({cost['name']})",
                             "short_label": "Your pay", "expected_salary": pay, "salary_basis": "Your pay",
                             "user_numbers": True, "current_job": True})
                if f"occ:{code}" not in current_job_ids(intake_answers):
                    continue
                row.update(name=f"Your current job, national median ({cost['name']})", short_label="Your job (median)",
                           current_job=True)
            else:
                row.update(name=f"Your current job ({cost['name']})", short_label="Your current job", current_job=True)
        rows.append(row)
    if missing:
        return {"error": f"No salary or education data for {', '.join(missing)}"}
    if not rows:
        return {"error": "No confirmed careers in intake"}
    return {"options": rows}


def with_rows(tool_name: str, args: dict, result):
    """A tool's result with its option rows attached."""
    if not isinstance(result, dict) or "error" in result:
        return result
    builders = {
        "search_occupations": lambda: occupation_rows(result),
        "search_schools": lambda: school_rows(result, args.get("degree_type", "bachelor")),
        "get_school_programs": lambda: program_rows(result),
    }
    if tool_name in builders:
        return {**result, "options": builders[tool_name]()}
    return result


def candidate_rows(intake_answers: dict | None, data_blocks: list[dict]) -> list[dict]:
    """Every row the report can pick: baselines, then each tool's rows in the
    order gathered. A later row with the same option_id replaces an earlier one
    (e.g. compare_education_paths' version of an occupation, with its gaps)."""
    by_id: dict[str, dict] = {}
    # path3 compares programs with each other and with the occupations they
    # lead to; the report cited baseline gaps without showing the baselines.
    # path4 compares careers side by side, with no payoff to anchor.
    if (intake_answers or {}).get("path_type") not in ("path3", "path4"):
        for row in baseline_rows(intake_answers):
            by_id[row["option_id"]] = row
    for block in data_blocks:
        data = block.get("data")
        for row in (data.get("options") or []) if isinstance(data, dict) else []:
            if isinstance(row, dict) and row.get("option_id") and row.get("expected_salary") is not None:
                by_id[row["option_id"]] = row
    rows = [_whole_numbers(r) for r in by_id.values()]
    if len(rows) > MAX_CANDIDATES:
        logger.warning("Dropping %d candidate rows over MAX_CANDIDATES", len(rows) - MAX_CANDIDATES)
    return rows[:MAX_CANDIDATES]


def _parse_list(value: str | None) -> list | None:
    try:
        parsed = json.loads(value or "null")
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, list) else None


def check_rows(intake_answers: dict | None, data_blocks: list[dict]) -> tuple[list[str], list[str]]:
    """What the gathered rows lack for this path: (required, expected).
    Required data missing means the report can't answer the question, so it is
    not written. Expected data missing still gets a report, and an alert."""
    answers = intake_answers or {}
    path = answers.get("path_type")
    rows = [r for b in data_blocks if isinstance(b.get("data"), dict) for r in b["data"].get("options") or []
            if isinstance(r, dict) and r.get("option_id")]
    ids = {r["option_id"] for r in rows}
    of_kind = lambda prefix: [r for r in rows if r["option_id"].startswith(prefix)]
    required: list[str] = []
    expected: list[str] = []

    if path == "path1":
        if not any(b.get("type") == "compare_education_paths" for b in data_blocks):
            required.append(f"education path comparison for {answers.get('occupation_title') or answers.get('occupation')}")

    elif path == "path2":
        picks = [p for p in (answers.get("school_picks") or "").split("|") if p]
        if picks:
            names = {str(c.get("value")): c.get("name") for c in _parse_list(answers.get("school_candidates")) or []
                     if isinstance(c, dict)}
            required += [f"school {names.get(p) or p}" for p in picks if f"school:{p}" not in ids]
        elif not of_kind("school:"):
            where = answers.get("target_places") or answers.get("target_location") or answers.get("target_states")
            required.append(f"schools in {where}" if where else "schools to compare")

    elif path == "path3":
        programs = of_kind("program:")
        titles = [t for t in _parse_list(answers.get("program_list")) or [] if isinstance(t, str)]
        have = {r["short_label"].lower() for r in programs}
        required += [f"program {t}" for t in dict.fromkeys(titles) if t.lower() not in have]
        if not titles and not programs:
            required.append(f"programs at {answers.get('school_matched_name') or answers.get('school_name') or 'the school'}")

    elif path in ("path4", "path5"):
        if path == "path4":
            careers = [c for c in _parse_list(answers.get("career_matches")) or [] if isinstance(c, dict)]
            wanted = [(c.get("soc_code"), c.get("title")) for c in careers]
        else:
            wanted = [(answers.get("target_career_code"), answers.get("target_career_title") or answers.get("target_career"))]
        required += [f"career {title or code}" for code, title in wanted if code and f"occ:{code}" not in ids]
        if not of_kind("occ:"):
            required.append("careers to compare")
        current = answers.get("current_role_title") or answers.get("current_role_code")
        expected += [f"current job {current}" for i in current_job_ids(answers) if i not in ids]

    return list(dict.fromkeys(required)), expected


def _whole_numbers(row: dict) -> dict:
    """145760.0 -> 145760: the model copies numbers as written, and a stray ".0"
    turns into garbled figures ("$132,70.0")."""
    return {k: int(v) if isinstance(v, float) and v.is_integer() else v for k, v in row.items()}


def pairwise_gaps(rows: list[dict]) -> list[dict]:
    """Differences between every pair of rows, each naming the higher option
    instead of carrying a sign: models misread "a minus b" (a negative gap
    became "earns less" for the higher earner)."""
    gaps = []
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            gap = {"options": [a["option_id"], b["option_id"]]}
            # Metrics both rows have (school vs school, program vs program).
            ma, mb = a.get("metrics") or {}, b.get("metrics") or {}
            shared = [(k, k) for k in ma if k in mb and not isinstance(ma[k], bool)]
            for field, label in (("expected_salary", "salary"), ("debt", "debt"), ("years_in_school", "years"), *shared):
                va = a.get(field) if field in a else ma.get(field)
                vb = b.get(field) if field in b else mb.get(field)
                if va is None or vb is None or va == vb:
                    continue
                higher = a if va > vb else b
                diff = abs(va - vb)
                gap[f"higher_{label}"] = higher["option_id"]
                gap[f"{label}_difference"] = diff if label == "years" or label in RATE_METRICS else round(diff)
            gaps.append(gap)
    return gaps
