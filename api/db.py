import json
import logging
import os
import re
import time
import uuid

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


_INCOME_BRACKETS = ["0-30000", "30001-48000", "48001-75000", "75001-110000", "110001-plus"]

_SCHOOL_FIELDS = ",".join([
    "id",
    "school.name",
    "school.city",
    "school.state",
    "school.school_url",
    "school.ownership",
    "school.degrees_awarded.predominant",
    "latest.student.size",
    "latest.cost.tuition.in_state",
    "latest.cost.tuition.out_of_state",
    "latest.cost.avg_net_price.overall",
    *[f"latest.cost.net_price.consumer.by_income_level.{b}" for b in _INCOME_BRACKETS],
    "latest.completion.rate_suppressed.overall",
    "latest.aid.median_debt_suppressed.completers.overall",
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

_SIZE_FILTER = {
    "small": ("..5000", "student_size <= 5000"),
    "medium": ("5000..15000", "student_size BETWEEN 5000 AND 15000"),
    "large": ("15000..", "student_size >= 15000"),
}

# sort_by -> (School column, descending)
_SCHOOL_SORT = {
    "earnings": ("earnings_10yr", True),
    "graduation_rate": ("graduation_rate", True),
    "net_price": ("avg_net_price", False),
    "median_debt": ("median_debt", False),
    "admission_rate": ("admission_rate", False),
    "retention_rate": ("retention_rate", True),
    "loan_repayment": ("repayment_rate_3yr", True),
}

MIN_GRADUATION_RATE = 0.70
MAX_SCHOOL_RESULTS = 5


def _int(val) -> int | None:
    f = _safe_float(val)
    return None if f is None else round(f)


def _map_school(r: dict) -> dict | None:
    """Scorecard row -> School columns. Mirrors mapSchool in src/lib/scorecard.ts.
    Returns None when the row lacks the fields School requires."""
    school_id = _int(r.get("id"))
    name, city, state = r.get("school.name"), r.get("school.city"), r.get("school.state")
    if school_id is None or not name or not city or not state:
        return None
    return {
        "school_id": school_id,
        "name": name,
        "city": city,
        "state": state,
        "school_type": _OWNERSHIP_LABELS.get(r.get("school.ownership"), "Unknown"),
        "predominant_degree": _int(r.get("school.degrees_awarded.predominant")),
        "url": r.get("school.school_url") or None,
        "student_size": _int(r.get("latest.student.size")),
        "tuition_in_state": _int(r.get("latest.cost.tuition.in_state")),
        "tuition_out_of_state": _int(r.get("latest.cost.tuition.out_of_state")),
        "avg_net_price": _int(r.get("latest.cost.avg_net_price.overall")),
        "net_price_by_income": json.dumps({
            b: _int(r.get(f"latest.cost.net_price.consumer.by_income_level.{b}")) for b in _INCOME_BRACKETS
        }),
        "graduation_rate": _safe_float(r.get("latest.completion.rate_suppressed.overall")),
        "median_debt": _int(r.get("latest.aid.median_debt_suppressed.completers.overall")),
        "earnings_6yr": _int(r.get("latest.earnings.6_yrs_after_entry.median")),
        "earnings_10yr": _int(r.get("latest.earnings.10_yrs_after_entry.median")),
        "admission_rate": _safe_float(r.get("latest.admissions.admission_rate.overall")),
        "retention_rate": _safe_float(r.get("latest.student.retention_rate.four_year.full_time")),
        "repayment_rate_3yr": _repayment_rate_3yr(r),
    }


_SCHOOL_COLUMNS = [
    "school_id", "name", "city", "state", "school_type", "predominant_degree", "url", "student_size",
    "tuition_in_state", "tuition_out_of_state", "avg_net_price", "net_price_by_income", "graduation_rate",
    "median_debt", "earnings_6yr", "earnings_10yr", "admission_rate", "retention_rate", "repayment_rate_3yr",
]


def _insert_schools(rows: list[dict], update_existing: bool) -> None:
    """Additive write to School. update_existing refreshes rows that are already
    stored (same as upsertSchools in the app); otherwise they are left as is."""
    if not rows:
        return
    cols = ", ".join(f'"{c}"' for c in _SCHOOL_COLUMNS)
    values = ", ".join(
        "CAST(:net_price_by_income AS JSONB)" if c == "net_price_by_income" else f":{c}" for c in _SCHOOL_COLUMNS
    )
    now = "(NOW() AT TIME ZONE 'UTC')"
    if update_existing:
        updates = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in _SCHOOL_COLUMNS if c != "school_id")
        conflict = f'DO UPDATE SET {updates}, "fetched_at" = {now}, "updated_at" = {now}'
    else:
        conflict = "DO NOTHING"
    with engine.begin() as conn:
        conn.execute(
            text(f"""
                INSERT INTO "School" ({cols}, "fetched_at", "updated_at")
                VALUES ({values}, {now}, {now})
                ON CONFLICT ("school_id") {conflict}
            """),
            rows,
        )


def _query_local_schools(
    name: str | None,
    state: str | None,
    ownership: str | None,
    max_net_price: int | None,
    size: str | None,
    sort_by: str | None,
    degree: int | None,
) -> list[dict]:
    # Browsing (by state) keeps to schools with a 70%+ graduation rate and full
    # data. A school the user names is always found; callers check its data.
    where = [] if name else [
        "graduation_rate >= :min_grad",
        "median_debt IS NOT NULL",
        "earnings_10yr IS NOT NULL",
        "avg_net_price IS NOT NULL",
    ]
    params: dict = {"min_grad": MIN_GRADUATION_RATE, "limit": MAX_SCHOOL_RESULTS}
    if name:
        where.append("name ILIKE :name")
        params["name"] = f"%{name}%"
    if state:
        where.append("state = :state")
        params["state"] = state.upper()
    if ownership and ownership.lower() in _OWNERSHIP_FILTER:
        where.append("school_type = :school_type")
        params["school_type"] = _OWNERSHIP_LABELS[_OWNERSHIP_FILTER[ownership.lower()]]
    if max_net_price and max_net_price > 0:
        where.append("avg_net_price <= :max_net_price")
        params["max_net_price"] = max_net_price
    if size in _SIZE_FILTER:
        where.append(_SIZE_FILTER[size][1])
    if degree is not None:
        where.append("predominant_degree = :degree")
        params["degree"] = degree

    if sort_by in _SCHOOL_SORT:
        column, descending = _SCHOOL_SORT[sort_by]
        order = f'"{column}" {"DESC" if descending else "ASC"} NULLS LAST'
    else:
        order = '"student_size" DESC NULLS LAST, "name" ASC'

    with _connect_with_retry() as conn:
        rows = conn.execute(
            text(f'SELECT * FROM "School" WHERE {" AND ".join(where)} ORDER BY {order} LIMIT :limit'),
            params,
        )
        return [dict(r._mapping) for r in rows]


def _school_result(s: dict) -> dict:
    return {
        "school_id": s["school_id"],
        "name": s["name"],
        "city": s["city"],
        "state": s["state"],
        "url": s["url"],
        "type": s["school_type"],
        "student_size": s["student_size"],
        "tuition_in_state": s["tuition_in_state"],
        "tuition_out_of_state": s["tuition_out_of_state"],
        "avg_net_price": s["avg_net_price"],
        "net_price_by_income": s["net_price_by_income"],
        "graduation_rate": s["graduation_rate"],
        "median_debt": s["median_debt"],
        "earnings_6yr_after_entry": s["earnings_6yr"],
        "earnings_10yr_after_entry": s["earnings_10yr"],
        "admission_rate": s["admission_rate"],
        "retention_rate": s["retention_rate"],
        "loan_repayment_rate_3yr": s["repayment_rate_3yr"],
    }


def _prefer_exact(schools: list[dict], name: str | None) -> list[dict]:
    """A name search matches substrings, so "University of Florida" also finds
    "University of Florida-Online". When a school's name is exactly the search,
    return only it."""
    exact = [s for s in schools if name and s["name"].lower() == name.strip().lower()]
    return exact or schools


def search_schools(
    name: str | None = None,
    state: str | None = None,
    ownership: str | None = None,
    max_net_price: int | None = None,
    size: str | None = None,
    sort_by: str | None = None,
    degree_type: str | None = "bachelor",
) -> dict:
    """Search schools by name and/or state in the local School table. Supports
    filtering by ownership (public/private), max net price, size, and predominant
    degree, and sorting by earnings, graduation_rate, net_price, or median_debt.
    With no local match, falls back to the College Scorecard API and stores what
    it finds, same as the app's /api/schools/search."""
    if not name and not state:
        return {"error": "Provide at least a school name or state", "results": []}
    if state and (len(state) != 2 or not state.isalpha()):
        return {"error": "State must be a two-letter code (e.g. 'FL', 'CA')", "results": []}

    degree = _DEGREE_TYPE_FILTER.get(degree_type.lower()) if degree_type else None
    args = (name, state, ownership, max_net_price, size, sort_by, degree)
    schools = _query_local_schools(*args)
    if schools:
        return {"results": [_school_result(s) for s in _prefer_exact(schools, name)], "source": "db"}

    if not SCORECARD_API_KEY:
        return {"results": [], "source": "db"}

    params: dict = {
        "api_key": SCORECARD_API_KEY,
        "fields": _SCHOOL_FIELDS,
        "per_page": 25,
        "school.operating": 1,
    }
    if name:
        params["school.name"] = name
    if state:
        params["school.state"] = state.upper()
    if ownership and ownership.lower() in _OWNERSHIP_FILTER:
        params["school.ownership"] = _OWNERSHIP_FILTER[ownership.lower()]
    if max_net_price and max_net_price > 0:
        params["latest.cost.avg_net_price.overall__range"] = f"..{max_net_price}"
    if size in _SIZE_FILTER:
        params["latest.student.size__range"] = _SIZE_FILTER[size][0]
    if degree is not None:
        params["school.degrees_awarded.predominant"] = degree

    resp = requests.get(SCORECARD_BASE_URL, params=params, timeout=15)
    if resp.status_code != 200:
        logger.warning("College Scorecard returned %d for '%s'", resp.status_code, name)
        return {"error": f"Scorecard API returned {resp.status_code}", "results": []}

    rows = [s for s in (_map_school(r) for r in resp.json().get("results", [])) if s is not None]
    _insert_schools(rows, update_existing=True)
    return {"results": [_school_result(s) for s in _prefer_exact(_query_local_schools(*args), name)], "source": "scorecard"}


_PROGRAM_PREFIX = "latest.programs.cip_4_digit"
_PROGRAM_FIELDS = ",".join([
    "id",
    f"{_PROGRAM_PREFIX}.code",
    f"{_PROGRAM_PREFIX}.title",
    f"{_PROGRAM_PREFIX}.credential.level",
    f"{_PROGRAM_PREFIX}.earnings.1_yr.overall_median_earnings",
    f"{_PROGRAM_PREFIX}.earnings.4_yr.overall_median_earnings",
    f"{_PROGRAM_PREFIX}.debt.staff_grad_plus.all.eval_inst.median",
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


def _nested(d: dict, path: str):
    for key in path.split("."):
        d = d.get(key) if isinstance(d, dict) else None
    return d


def _map_programs(school_id: int, raw: list) -> list[dict]:
    """Scorecard programs -> SchoolProgram rows. Mirrors mapPrograms in src/lib/scorecard.ts."""
    rows: dict[str, dict] = {}
    for p in raw or []:
        cip_code = p.get("code")
        level = _int(_nested(p, "credential.level"))
        if not cip_code or level is None:
            continue
        rows[f"{cip_code}:{level}"] = {
            "id": str(uuid.uuid4()),
            "school_id": school_id,
            "cip_code": cip_code,
            "title": (p.get("title") or cip_code).rstrip("."),
            "credential_level": level,
            "earnings_1yr": _int(_nested(p, "earnings.1_yr.overall_median_earnings")),
            "earnings_4yr": _int(_nested(p, "earnings.4_yr.overall_median_earnings")),
            "median_debt": _int(_nested(p, "debt.staff_grad_plus.all.eval_inst.median")),
        }
    return list(rows.values())


def _ensure_programs(school_id: int) -> str | None:
    """Fetch and store a school's programs the first time they are needed, same as
    the app's /api/schools/[id]/programs. Additive: stored rows are never changed.
    Returns an error message, or None when programs are available locally."""
    with _connect_with_retry() as conn:
        stored = conn.execute(
            text('SELECT 1 FROM "SchoolProgram" WHERE school_id = :id LIMIT 1'), {"id": school_id}
        ).first()
    if stored:
        return None
    if not SCORECARD_API_KEY:
        return "College Scorecard API key not configured"

    resp = requests.get(SCORECARD_BASE_URL, params={
        "id": school_id,
        "api_key": SCORECARD_API_KEY,
        "fields": f"{_SCHOOL_FIELDS},{_PROGRAM_FIELDS}",
        "per_page": 1,
    }, timeout=15)
    if resp.status_code != 200:
        logger.warning("College Scorecard returned %d for school %d", resp.status_code, school_id)
        return f"Scorecard API returned {resp.status_code}"

    results = resp.json().get("results", [])
    school = _map_school(results[0]) if results else None
    if school is None:
        return f"No school found with id {school_id}"
    _insert_schools([school], update_existing=False)

    programs = _map_programs(school_id, results[0].get(_PROGRAM_PREFIX))
    if programs:
        now = "(NOW() AT TIME ZONE 'UTC')"
        with engine.begin() as conn:
            conn.execute(
                text(f"""
                    INSERT INTO "SchoolProgram" (id, school_id, cip_code, title, credential_level,
                        earnings_1yr, earnings_4yr, median_debt, fetched_at, updated_at)
                    VALUES (:id, :school_id, :cip_code, :title, :credential_level,
                        :earnings_1yr, :earnings_4yr, :median_debt, {now}, {now})
                    ON CONFLICT (school_id, cip_code, credential_level) DO NOTHING
                """),
                programs,
            )
    return None


def get_school_programs(school_id: int, program_search: str | None = None) -> dict:
    """Get per-program earnings at a specific school from the local SchoolProgram
    table, fetching from College Scorecard the first time. Optionally filter by
    program name. Returns 1yr and 4yr post-graduation median earnings by program."""
    error = _ensure_programs(school_id)
    if error:
        return {"error": error}

    params: dict = {"id": school_id}
    search_sql = ""
    if program_search:
        search_sql = "AND p.title ILIKE :search"
        params["search"] = f"%{program_search}%"
    with _connect_with_retry() as conn:
        school = conn.execute(text('SELECT name FROM "School" WHERE school_id = :id'), {"id": school_id}).first()
        rows = conn.execute(
            text(f"""
                SELECT p.cip_code, p.title, p.credential_level, p.earnings_1yr, p.earnings_4yr, p.median_debt
                FROM "SchoolProgram" p
                WHERE p.school_id = :id
                  AND (p.earnings_1yr IS NOT NULL OR p.earnings_4yr IS NOT NULL)
                  {search_sql}
                ORDER BY COALESCE(p.earnings_4yr, p.earnings_1yr) DESC
                LIMIT 25
            """),
            params,
        )
        programs = [
            {
                "cip_code": r.cip_code,
                "title": r.title,
                "credential": _CREDENTIAL_LEVELS.get(r.credential_level, f"Level {r.credential_level}"),
                "credential_level": r.credential_level,
                "earnings_1yr_after_graduation": r.earnings_1yr,
                "earnings_4yr_after_graduation": r.earnings_4yr,
                "median_debt": r.median_debt,
            }
            for r in rows
        ]

    return {
        "school_id": school_id,
        "school_name": school.name if school else None,
        "programs": programs,
    }
