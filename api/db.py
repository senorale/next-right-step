import logging
import os
import re
import time

import requests
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)

ONET_API_KEY = os.environ.get("O_NET_API_KEY", "")
ONET_BASE_URL = "https://api-v2.onetcenter.org"

SCORECARD_API_KEY = os.environ.get("COLLEGE_SCORECARD_API_KEY", "")
SCORECARD_BASE_URL = "https://api.data.gov/ed/collegescorecard/v1/schools"

EDUCATION_CODE_TO_YEARS = {
    1: 0,    # Less than high school
    2: 0,    # High school diploma or equivalent
    3: 0,    # Post-secondary certificate
    4: 1,    # Some college, no degree
    5: 2,    # Associate's degree
    6: 4,    # Bachelor's degree
    7: 4,    # Post-baccalaureate certificate
    8: 6,    # Master's degree
    9: 6,    # Post-master's certificate
    10: 8,   # First professional degree (JD, MD, etc.)
    11: 8,   # Doctoral degree
    12: 10,  # Post-doctoral training
}


def _fetch_typical_years(occupation_code: str) -> float | None:
    """Call O*NET education endpoint, return years for highest-percentage education level."""
    if not ONET_API_KEY:
        return None
    onet_code = occupation_code + ".00"
    url = f"{ONET_BASE_URL}/online/occupations/{onet_code}/summary/education"
    try:
        resp = requests.get(url, headers={
            "X-API-Key": ONET_API_KEY,
            "Accept": "application/json",
            "User-Agent": "should-i-go/1.0",
        }, timeout=10)
        if resp.status_code != 200:
            logger.warning("O*NET returned %d for %s", resp.status_code, onet_code)
            return None
        data = resp.json().get("response", [])
        if not data:
            return None
        has_percentages = any("percentage_of_respondents" in d for d in data)
        if has_percentages:
            top = max(data, key=lambda d: d.get("percentage_of_respondents", 0))
        else:
            top = max(data, key=lambda d: d.get("code", 0))
        return EDUCATION_CODE_TO_YEARS.get(top["code"])
    except Exception:
        logger.exception("O*NET fetch failed for %s", occupation_code)
        return None


def _backfill_years(occupation_code: str) -> float | None:
    """Fetch from O*NET and write to DB. Returns the value or None."""
    years = _fetch_typical_years(occupation_code)
    if years is None:
        return None
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE "OccupationSubCategory"
                SET typical_years_of_school = :years, updated_at = NOW()
                WHERE occupation_code = :code
            """),
            {"years": years, "code": occupation_code},
        )
    return years


MAX_SQL_ROWS = 50

_SELECT_ONLY_RE = re.compile(
    r"^\s*SELECT\b",
    re.IGNORECASE | re.DOTALL,
)

_FORBIDDEN_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|COPY)\b",
    re.IGNORECASE,
)


_DB_RETRY_DELAYS = [1, 2, 4]


def _connect_with_retry():
    for attempt, delay in enumerate(_DB_RETRY_DELAYS):
        try:
            return engine.connect()
        except OperationalError:
            if attempt == len(_DB_RETRY_DELAYS) - 1:
                raise
            logger.warning("DB connection failed, retrying in %ds", delay)
            time.sleep(delay)


def run_sql(query: str) -> list[dict]:
    """Execute a read-only SQL query. Only SELECT statements allowed."""
    if not _SELECT_ONLY_RE.match(query):
        raise ValueError("Only SELECT statements are allowed.")
    if _FORBIDDEN_RE.search(query):
        raise ValueError("Write operations are not allowed.")
    with _connect_with_retry() as conn:
        rows = conn.execute(text(query))
        results = [dict(r._mapping) for r in rows]
    if len(results) > MAX_SQL_ROWS:
        return results[:MAX_SQL_ROWS]
    return results


def find_degrees_with_occupations(query: str) -> list[dict]:
    """Search degrees (CIP codes) by title and return each match with all linked occupations and salaries."""
    with _connect_with_retry() as conn:
        rows = conn.execute(
            text("""
                SELECT c.code AS cip_code,
                       c.title AS degree,
                       o.name AS occupation,
                       o.occupation_code,
                       o.annual_salary,
                       o.typical_years_of_school
                FROM "CipCode" c
                JOIN "CipOccupation" co ON co.cip_id = c.id
                JOIN "OccupationSubCategory" o ON o.id = co.occupation_id
                WHERE c.title ILIKE :q
                ORDER BY c.title, o.annual_salary DESC
            """),
            {"q": f"%{query}%"},
        )
        flat = [dict(r._mapping) for r in rows]

    grouped: dict[str, dict] = {}
    for row in flat:
        cip_code = row["cip_code"]
        if cip_code not in grouped:
            grouped[cip_code] = {"cip_code": cip_code, "degree": row["degree"], "occupations": []}

        years = row["typical_years_of_school"]
        if years is None:
            years = _backfill_years(row["occupation_code"])

        grouped[cip_code]["occupations"].append({
            "occupation": row["occupation"],
            "annual_salary": float(row["annual_salary"]),
            "typical_years_of_school": float(years) if years is not None else None,
        })

    return list(grouped.values())


def get_tuition_medians() -> list[dict]:
    """Get median tuition data by school type."""
    with _connect_with_retry() as conn:
        rows = conn.execute(
            text("""
                SELECT cohort, label, sticker_annual, net_price_annual,
                       cost_of_attendance_annual
                FROM "TuitionMedian"
                ORDER BY cohort
            """)
        )
        return [dict(r._mapping) for r in rows]


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def search_occupations(keyword: str) -> dict:
    """Search occupations by keyword via O*NET API. Returns matched occupations
    with bright outlook status, education requirements, and BLS salary when available."""
    if not ONET_API_KEY:
        return {"error": "O*NET API key not configured", "results": []}

    try:
        resp = requests.get(f"{ONET_BASE_URL}/online/search", params={
            "keyword": keyword,
            "start": 1,
            "end": 10,
        }, headers={
            "X-API-Key": ONET_API_KEY,
            "Accept": "application/json",
            "User-Agent": "should-i-go/1.0",
        }, timeout=10)
    except requests.RequestException:
        logger.exception("O*NET search failed for '%s'", keyword)
        return {"error": "O*NET search request failed", "results": []}

    if resp.status_code != 200:
        logger.warning("O*NET search returned %d for '%s'", resp.status_code, keyword)
        return {"error": f"O*NET search returned {resp.status_code}", "results": []}

    data = resp.json()
    raw_occupations = data.get("occupation", [])
    if not raw_occupations:
        return {"results": [], "keyword": keyword}

    soc_codes = list({occ["code"].split(".")[0] for occ in raw_occupations})

    bls_data: dict = {}
    if soc_codes:
        try:
            codes_params = {f"c{i}": code for i, code in enumerate(soc_codes)}
            codes_sql = ", ".join(f":c{i}" for i in range(len(soc_codes)))
            with _connect_with_retry() as conn:
                rows = conn.execute(
                    text(f'SELECT occupation_code, name, annual_salary, typical_years_of_school FROM "OccupationSubCategory" WHERE occupation_code IN ({codes_sql})'),
                    codes_params,
                )
                bls_data = {r.occupation_code: dict(r._mapping) for r in rows}
        except Exception:
            logger.exception("BLS cross-reference failed")

    results = []
    fallback_count = 0
    for occ in raw_occupations[:10]:
        code = occ["code"]
        short_code = code.split(".")[0]
        tags = occ.get("tags", {})
        bls = bls_data.get(short_code, {})

        years = bls.get("typical_years_of_school")
        if years is None and fallback_count < 3:
            years = _fetch_typical_years(short_code)
            fallback_count += 1

        results.append({
            "soc_code": short_code,
            "onet_code": code,
            "title": occ.get("title", ""),
            "bright_outlook": tags.get("bright_outlook", False),
            "annual_salary": _safe_float(bls.get("annual_salary")),
            "typical_years_of_school": _safe_float(years),
        })

    return {"results": results, "keyword": keyword}


_SCHOOL_FIELDS = ",".join([
    "id",
    "school.name",
    "school.city",
    "school.state",
    "school.school_url",
    "school.ownership",
    "latest.student.size",
    "latest.cost.tuition.in_state",
    "latest.cost.tuition.out_of_state",
    "latest.cost.avg_net_price.overall",
    "latest.cost.net_price.consumer.by_income_level.0-30000",
    "latest.cost.net_price.consumer.by_income_level.30001-48000",
    "latest.cost.net_price.consumer.by_income_level.48001-75000",
    "latest.cost.net_price.consumer.by_income_level.75001-110000",
    "latest.cost.net_price.consumer.by_income_level.110001-plus",
    "latest.completion.rate_suppressed.overall",
    "latest.aid.median_debt_suppressed.overall",
    "latest.earnings.6_yrs_after_entry.median",
    "latest.earnings.10_yrs_after_entry.median",
    "latest.admissions.admission_rate.overall",
    "latest.student.retention_rate.four_year.full_time",
    # No overall 3-year repayment rate exists (3_yr_repayment.overall is a
    # borrower count), so it is derived from the completer/noncompleter splits.
    "latest.repayment.3_yr_repayment.completers",
    "latest.repayment.3_yr_repayment.completers_rate",
    "latest.repayment.3_yr_repayment.noncompleters",
    "latest.repayment.3_yr_repayment.noncompleters_rate",
])


def _repayment_rate_3yr(r: dict) -> float | None:
    completers = _safe_float(r.get("latest.repayment.3_yr_repayment.completers"))
    completers_rate = _safe_float(r.get("latest.repayment.3_yr_repayment.completers_rate"))
    noncompleters = _safe_float(r.get("latest.repayment.3_yr_repayment.noncompleters"))
    noncompleters_rate = _safe_float(r.get("latest.repayment.3_yr_repayment.noncompleters_rate"))
    if None in (completers, completers_rate, noncompleters, noncompleters_rate):
        return None
    borrowers = completers + noncompleters
    if borrowers == 0:
        return None
    return (completers * completers_rate + noncompleters * noncompleters_rate) / borrowers

_OWNERSHIP_LABELS = {1: "Public", 2: "Private nonprofit", 3: "Private for-profit"}


_OWNERSHIP_FILTER = {
    "public": 1,
    "private": 2,
}

_DEGREE_TYPE_FILTER = {
    "certificate": 1,
    "associate": 2,
    "bachelor": 3,
    "graduate": 4,
}


def search_schools(
    name: str | None = None,
    state: str | None = None,
    ownership: str | None = None,
    max_net_price: int | None = None,
    size: str | None = None,
    sort_by: str | None = None,
    degree_type: str | None = "bachelor",
) -> dict:
    """Search schools by name and/or state via College Scorecard API. Supports
    filtering by ownership (public/private), max net price, and sorting by
    earnings, graduation_rate, net_price, or median_debt."""
    if not SCORECARD_API_KEY:
        return {"error": "College Scorecard API key not configured", "results": []}
    if not name and not state:
        return {"error": "Provide at least a school name or state", "results": []}
    if state and (len(state) != 2 or not state.isalpha()):
        return {"error": "State must be a two-letter code (e.g. 'FL', 'CA')", "results": []}

    params: dict = {
        "api_key": SCORECARD_API_KEY,
        "fields": _SCHOOL_FIELDS,
        "per_page": 25,
        "latest.completion.rate_suppressed.overall__range": "0.70..",
    }
    if name:
        params["school.name"] = name
    if state:
        params["school.state"] = state.upper()
    if ownership and ownership.lower() in _OWNERSHIP_FILTER:
        params["school.ownership"] = _OWNERSHIP_FILTER[ownership.lower()]
    if max_net_price and max_net_price > 0:
        params["latest.cost.avg_net_price.overall__range"] = f"..{max_net_price}"
    if size == "small":
        params["latest.student.size__range"] = "..5000"
    elif size == "medium":
        params["latest.student.size__range"] = "5000..15000"
    elif size == "large":
        params["latest.student.size__range"] = "15000.."
    if degree_type and degree_type.lower() in _DEGREE_TYPE_FILTER:
        params["school.degrees_awarded.predominant"] = _DEGREE_TYPE_FILTER[degree_type.lower()]

    sort_key = sort_by or ""

    resp = requests.get(SCORECARD_BASE_URL, params=params, timeout=15)

    if resp.status_code != 200:
        logger.warning("College Scorecard returned %d for '%s'", resp.status_code, name)
        return {"error": f"Scorecard API returned {resp.status_code}", "results": []}

    results = resp.json().get("results", [])
    schools = []
    for r in results:
        grad_rate = r.get("latest.completion.rate_suppressed.overall")
        median_debt = r.get("latest.aid.median_debt_suppressed.overall")
        earnings = r.get("latest.earnings.10_yrs_after_entry.median")
        avg_net_price = r.get("latest.cost.avg_net_price.overall")

        if grad_rate is None or median_debt is None or earnings is None or avg_net_price is None:
            continue

        schools.append({
            "school_id": r.get("id"),
            "name": r.get("school.name"),
            "city": r.get("school.city"),
            "state": r.get("school.state"),
            "url": r.get("school.school_url"),
            "type": _OWNERSHIP_LABELS.get(r.get("school.ownership"), "Unknown"),
            "student_size": r.get("latest.student.size"),
            "tuition_in_state": r.get("latest.cost.tuition.in_state"),
            "tuition_out_of_state": r.get("latest.cost.tuition.out_of_state"),
            "avg_net_price": avg_net_price,
            "net_price_by_income": {
                "0-30000": r.get("latest.cost.net_price.consumer.by_income_level.0-30000"),
                "30001-48000": r.get("latest.cost.net_price.consumer.by_income_level.30001-48000"),
                "48001-75000": r.get("latest.cost.net_price.consumer.by_income_level.48001-75000"),
                "75001-110000": r.get("latest.cost.net_price.consumer.by_income_level.75001-110000"),
                "110001-plus": r.get("latest.cost.net_price.consumer.by_income_level.110001-plus"),
            },
            "graduation_rate": grad_rate,
            "median_debt": median_debt,
            "earnings_6yr_after_entry": r.get("latest.earnings.6_yrs_after_entry.median"),
            "earnings_10yr_after_entry": earnings,
            "admission_rate": r.get("latest.admissions.admission_rate.overall"),
            "retention_rate": r.get("latest.student.retention_rate.four_year.full_time"),
            "loan_repayment_rate_3yr": _repayment_rate_3yr(r),
        })
        if len(schools) >= 5:
            break

    sort_field_map = {
        "earnings": ("earnings_10yr_after_entry", True),
        "graduation_rate": ("graduation_rate", True),
        "net_price": ("avg_net_price", False),
        "median_debt": ("median_debt", False),
        "admission_rate": ("admission_rate", False),
        "retention_rate": ("retention_rate", True),
        "loan_repayment": ("loan_repayment_rate_3yr", True),
    }
    if sort_key in sort_field_map:
        field, descending = sort_field_map[sort_key]
        schools.sort(key=lambda s: s.get(field) or 0, reverse=descending)

    return {"results": schools}


_PROGRAM_FIELDS = ",".join([
    "id",
    "school.name",
    "latest.programs.cip_4_digit.code",
    "latest.programs.cip_4_digit.title",
    "latest.programs.cip_4_digit.credential.level",
    "latest.programs.cip_4_digit.earnings.1_yr.overall_median_earnings",
    "latest.programs.cip_4_digit.earnings.4_yr.overall_median_earnings",
])

# Scorecard field-of-study CREDLEV codes
_CREDENTIAL_LEVELS = {
    1: "Undergraduate certificate",
    2: "Associate's",
    3: "Bachelor's",
    4: "Post-baccalaureate certificate",
    5: "Master's",
    6: "Doctoral",
    7: "First professional degree",
    8: "Graduate/professional certificate",
}


def get_school_programs(school_id: int, program_search: str | None = None) -> dict:
    """Get per-program earnings at a specific school. Optionally filter by program name.
    Returns 1yr and 4yr post-graduation median earnings by program."""
    if not SCORECARD_API_KEY:
        return {"error": "College Scorecard API key not configured"}

    resp = requests.get(SCORECARD_BASE_URL, params={
        "id": school_id,
        "api_key": SCORECARD_API_KEY,
        "fields": _PROGRAM_FIELDS,
        "per_page": 1,
    }, timeout=15)

    if resp.status_code != 200:
        logger.warning("College Scorecard returned %d for school %d", resp.status_code, school_id)
        return {"error": f"Scorecard API returned {resp.status_code}"}

    results = resp.json().get("results", [])
    if not results:
        return {"error": f"No school found with id {school_id}"}

    school = results[0]
    programs_raw = school.get("latest.programs.cip_4_digit", []) or []

    programs = []
    search_lower = program_search.lower() if program_search else None
    for p in programs_raw:
        title = p.get("title", "")
        if search_lower and search_lower not in title.lower():
            continue
        earnings = p.get("earnings") or {}
        earnings_1yr = (earnings.get("1_yr") or {}).get("overall_median_earnings")
        earnings_4yr = (earnings.get("4_yr") or {}).get("overall_median_earnings")
        if earnings_1yr is None and earnings_4yr is None:
            continue
        cred_level = p.get("credential", {}).get("level")
        programs.append({
            "cip_code": p.get("code"),
            "title": title,
            "credential": _CREDENTIAL_LEVELS.get(cred_level, f"Level {cred_level}"),
            "earnings_1yr_after_graduation": earnings_1yr,
            "earnings_4yr_after_graduation": earnings_4yr,
        })

    programs.sort(key=lambda x: x.get("earnings_4yr_after_graduation") or x.get("earnings_1yr_after_graduation") or 0, reverse=True)

    return {
        "school_id": school.get("id"),
        "school_name": school.get("school.name"),
        "programs": programs[:25],
    }
