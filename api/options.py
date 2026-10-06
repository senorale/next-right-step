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

import logging

from career_cost import BACHELOR_SALARY, BACHELOR_YEARS, HS_SALARY, career_cost, career_option, national_bachelors_debt

logger = logging.getLogger(__name__)

MAX_OCCUPATION_ROWS = 3  # per search: the top matches with a salary
MAX_PROGRAM_ROWS = 6  # per call: the highest-earning matches
MAX_CANDIDATES = 20  # rows sent to the report model (pairwise gaps grow fast)

AMOUNT_METRICS = ("avg_net_price", "tuition_in_state", "tuition_out_of_state", "median_debt",
                  "earnings_6yr_after_entry", "earnings_10yr_after_entry", "student_size")
RATE_METRICS = ("graduation_rate", "admission_rate", "retention_rate", "loan_repayment_rate_3yr")
SCHOOL_YEARS = {"certificate": 1, "associate": 2, "bachelor": 4, "graduate": 2}
# Length of the program itself, by Scorecard credential level.
PROGRAM_YEARS = {1: 1, 2: 2, 3: 4, 4: 1, 5: 2, 6: 5, 7: 4, 8: 1}


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


def school_rows(result: dict, degree_type: str | None) -> list[dict]:
    """search_schools: each school with earnings data. Cost is the school's
    median debt at graduation; salary is graduates' earnings 10 years after entry."""
    years = SCHOOL_YEARS.get((degree_type or "bachelor").lower(), BACHELOR_YEARS)
    rows = []
    for s in result.get("results") or []:
        salary = s.get("earnings_10yr_after_entry") or s.get("earnings_6yr_after_entry")
        if not salary:
            continue
        rows.append({
            "option_id": f"school:{s['school_id']}",
            "name": s["name"],
            "short_label": s["name"],
            "education": f"{s.get('type') or ''} school, {s.get('city')}, {s.get('state')}".strip(", "),
            "years_in_school": years,
            "debt": s.get("median_debt") or 0,
            "cost_basis": "This school's median debt at graduation (College Scorecard)" if s.get("median_debt")
            else "No debt data for this school",
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


def program_rows(result: dict) -> list[dict]:
    """get_school_programs: the highest-earning programs. Cost is the program's
    median debt; salary is its graduates' earnings 4 years out (else 1 year)."""
    school_id, school = result.get("school_id"), result.get("school_name") or "this school"
    rows = []
    for p in (result.get("programs") or [])[:MAX_PROGRAM_ROWS]:
        salary = p.get("earnings_4yr_after_graduation") or p.get("earnings_1yr_after_graduation")
        level = p.get("credential_level")
        rows.append({
            "option_id": f"program:{school_id}:{p['cip_code']}:{level}",
            "name": f"{p['title']} ({p['credential']})",
            "short_label": p["title"],
            "education": f"{p['credential']} at {school}",
            "years_in_school": PROGRAM_YEARS.get(level, BACHELOR_YEARS),
            "debt": p.get("median_debt") or 0,
            "cost_basis": f"Median debt for this program at {school} (College Scorecard)" if p.get("median_debt")
            else "No debt data for this program",
            "expected_salary": salary,
            "salary_basis": f"College Scorecard median earnings of this program's graduates "
            + ("4 years" if p.get("earnings_4yr_after_graduation") else "1 year") + " after graduating",
            "metrics": {k: p.get(k) for k in ("earnings_1yr_after_graduation", "earnings_4yr_after_graduation")
                        if p.get(k) is not None},
        })
    return rows


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
            for field, label in (("expected_salary", "salary"), ("debt", "debt"), ("years_in_school", "years")):
                va, vb = a.get(field), b.get(field)
                if va is None or vb is None or va == vb:
                    continue
                higher = a if va > vb else b
                diff = abs(va - vb)
                gap[f"higher_{label}"] = higher["option_id"]
                gap[f"{label}_difference"] = round(diff) if label != "years" else diff
            gaps.append(gap)
    return gaps
