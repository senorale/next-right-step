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

from alerts import send_alert

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
            send_alert("O*NET education lookup failed", {"occupation_code": onet_code, "status": resp.status_code})
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
    except Exception as exc:
        logger.exception("O*NET fetch failed for %s", occupation_code)
        send_alert("O*NET education lookup failed", {"occupation_code": occupation_code, "error": repr(exc)})
        return None


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
    except requests.RequestException as exc:
        logger.exception("O*NET search failed for '%s'", keyword)
        send_alert("O*NET search failed", {"keyword": keyword, "error": repr(exc)})
        return {"error": "O*NET search request failed", "results": []}

    if resp.status_code != 200:
        send_alert("O*NET search failed", {"keyword": keyword, "status": resp.status_code, "body": resp.text[:500]})
        return {"error": f"O*NET search returned {resp.status_code}", "results": []}

    data = resp.json()
    raw_occupations = data.get("occupation", [])
    if not raw_occupations:
        return {"error": f"No occupations found for '{keyword}'", "results": [], "keyword": keyword}

    soc_codes = list({occ["code"].split(".")[0] for occ in raw_occupations})

    bls_data: dict = {}
    warning = None
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
        except Exception as exc:
            logger.exception("BLS cross-reference failed")
            warning = "BLS salaries unavailable"
            send_alert("BLS salary lookup failed", {"keyword": keyword, "soc_codes": soc_codes, "error": repr(exc)})

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

    out = {"results": results, "keyword": keyword}
    if warning:
        out["warning"] = warning
    return out


_INCOME_BRACKETS = ["0-30000", "30001-48000", "48001-75000", "75001-110000", "110001-plus"]

_SCHOOL_FIELDS = ",".join([
    "id",
    "ope6_id",
    "school.name",
    "school.city",
    "school.state",
    "school.school_url",
    "school.ownership",
    "school.degrees_awarded.predominant",
    "school.degrees_awarded.highest",
    "school.operating",
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
        "highest_degree": _int(r.get("school.degrees_awarded.highest")),
        "ope6_id": r.get("ope6_id") or None,
        "operating": _int(r.get("school.operating")) != 0,
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
    "school_id", "name", "city", "state", "school_type", "predominant_degree", "highest_degree", "ope6_id",
    "operating", "url", "student_size", "tuition_in_state", "tuition_out_of_state", "avg_net_price",
    "net_price_by_income", "graduation_rate", "median_debt", "earnings_6yr", "earnings_10yr", "admission_rate", "retention_rate", "repayment_rate_3yr",
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
    # Browsing (by state) keeps to schools with full data, and to those with a
    # 70%+ graduation rate when enough of them match. A school the user names is
    # always found; callers check its data.
    where = ["operating"] + ([] if name else [
        "median_debt IS NOT NULL",
        "earnings_10yr IS NOT NULL",
        "avg_net_price IS NOT NULL",
    ])
    params: dict = {"limit": MAX_SCHOOL_RESULTS, "min_grad": MIN_GRADUATION_RATE}
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

    def select(conditions: list[str]) -> list[dict]:
        rows = conn.execute(
            text(f'SELECT * FROM "School" WHERE {" AND ".join(conditions)} ORDER BY {order} LIMIT :limit'),
            params,
        )
        return [dict(r._mapping) for r in rows]

    with _connect_with_retry() as conn:
        if not name:
            graduating = select(where + ["graduation_rate >= :min_grad"])
            if len(graduating) == MAX_SCHOOL_RESULTS:
                return graduating
        return select(where)


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
        send_alert("College Scorecard API key not configured", {"search": "schools"})
        return {"error": "College Scorecard API key not configured", "results": []}

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

    filters = {k: v for k, v in zip(("name", "state", "ownership", "max_net_price", "size", "sort_by", "degree"), args) if v}
    try:
        resp = requests.get(SCORECARD_BASE_URL, params=params, timeout=15)
    except requests.RequestException as exc:
        send_alert("College Scorecard school search failed", {"filters": filters, "error": repr(exc)})
        return {"error": "College Scorecard request failed", "results": []}
    if resp.status_code != 200:
        send_alert("College Scorecard school search failed",
                   {"filters": filters, "status": resp.status_code, "body": resp.text[:500]})
        return {"error": f"Scorecard API returned {resp.status_code}", "results": []}

    rows = [s for s in (_map_school(r) for r in resp.json().get("results", [])) if s is not None and _has_school_data(s)]
    _insert_schools(rows, update_existing=True)
    schools = _query_local_schools(*args)
    if not schools:
        return {"error": f"No schools found for {filters}", "results": []}
    return {"results": [_school_result(s) for s in _prefer_exact(schools, name)], "source": "scorecard"}


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


def _has_school_data(school: dict) -> bool:
    """Whether a school can be compared on its own (Compare schools): school-wide
    earnings and debt. Mirrors hasSchoolData in src/lib/scorecard.ts."""
    return school.get("earnings_10yr") is not None and school.get("median_debt") is not None


def _map_programs(school_id: int, raw: list) -> list[dict]:
    """Scorecard programs with earnings -> SchoolProgram rows; one without them
    can't be compared, so it isn't stored. Mirrors mapPrograms in src/lib/scorecard.ts."""
    rows: dict[str, dict] = {}
    for p in raw or []:
        cip_code = p.get("code")
        level = _int(_nested(p, "credential.level"))
        earnings_1yr = _int(_nested(p, "earnings.1_yr.overall_median_earnings"))
        earnings_4yr = _int(_nested(p, "earnings.4_yr.overall_median_earnings"))
        if not cip_code or level is None or (earnings_1yr is None and earnings_4yr is None):
            continue
        rows[f"{cip_code}:{level}"] = {
            "id": str(uuid.uuid4()),
            "school_id": school_id,
            "cip_code": cip_code,
            "title": (p.get("title") or cip_code).rstrip("."),
            "credential_level": level,
            "earnings_1yr": earnings_1yr,
            "earnings_4yr": earnings_4yr,
            "median_debt": _int(_nested(p, "debt.staff_grad_plus.all.eval_inst.median")),
        }
    return list(rows.values())


def _ensure_programs(school_id: int) -> str | None:
    """Fetch and store a school's programs the first time they are needed, same as
    the app's /api/schools/[id]/programs. Additive: stored rows are never changed.
    Only programs with earnings are stored, and the school only if it has some.
    Returns an error message, or None when programs are available locally."""
    with _connect_with_retry() as conn:
        stored = conn.execute(
            text('SELECT 1 FROM "SchoolProgram" WHERE school_id = :id LIMIT 1'), {"id": school_id}
        ).first()
    if stored:
        return None
    if not SCORECARD_API_KEY:
        send_alert("College Scorecard API key not configured", {"search": "programs", "school_id": school_id})
        return "College Scorecard API key not configured"

    try:
        resp = requests.get(SCORECARD_BASE_URL, params={
            "id": school_id,
            "api_key": SCORECARD_API_KEY,
            "fields": f"{_SCHOOL_FIELDS},{_PROGRAM_FIELDS}",
            "per_page": 1,
        }, timeout=15)
    except requests.RequestException as exc:
        send_alert("College Scorecard program fetch failed", {"school_id": school_id, "error": repr(exc)})
        return "College Scorecard request failed"
    if resp.status_code != 200:
        send_alert("College Scorecard program fetch failed",
                   {"school_id": school_id, "status": resp.status_code, "body": resp.text[:500]})
        return f"Scorecard API returned {resp.status_code}"

    results = resp.json().get("results", [])
    school = _map_school(results[0]) if results else None
    if school is None:
        return f"No school found with id {school_id}"
    programs = _map_programs(school_id, results[0].get(_PROGRAM_PREFIX))
    # Schools with nothing to compare aren't stored.
    if not programs and not _has_school_data(school):
        return f"No earnings data for {school['name']}"
    _insert_schools([school], update_existing=False)
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
    if not programs:
        search = f" matching '{program_search}'" if program_search else ""
        return {"error": f"No programs with earnings data at school_id {school_id}{search}"}

    return {
        "school_id": school_id,
        "school_name": school.name if school else None,
        "programs": programs,
    }


def school_program_titles(school_id: int) -> dict[str, bool] | None:
    """Every program title a school offers -> whether any credential level has
    earnings data, so the intake can match what the user typed and turn away
    programs it can't compare. None when programs can't load."""
    if _ensure_programs(school_id):
        return None
    with _connect_with_retry() as conn:
        rows = conn.execute(
            text("""SELECT title, bool_or(earnings_1yr IS NOT NULL OR earnings_4yr IS NOT NULL) AS has_earnings
                    FROM "SchoolProgram" WHERE school_id = :id GROUP BY title ORDER BY title"""),
            {"id": school_id},
        )
        return {r.title: bool(r.has_earnings) for r in rows}


def school_programs(school_id: int) -> dict:
    """Every program a school offers, at each credential level, with its
    earnings, its median debt, and the national median debt for the same
    field and credential (a fallback when the school reports none)."""
    error = _ensure_programs(school_id)
    if error:
        return {"error": error}
    with _connect_with_retry() as conn:
        school = conn.execute(text('SELECT name FROM "School" WHERE school_id = :id'), {"id": school_id}).first()
        rows = conn.execute(
            text("""
                SELECT p.cip_code, p.title, p.credential_level, p.earnings_1yr, p.earnings_4yr, p.median_debt,
                       pd.median_debt AS national_median_debt
                FROM "SchoolProgram" p
                LEFT JOIN "CipCode" c ON c.code = p.cip_code
                LEFT JOIN "ProgramDebt" pd ON pd.cip_id = c.id AND pd.credential_level = p.credential_level
                     AND pd.school_type = 'all'
                WHERE p.school_id = :id
                ORDER BY p.title, p.credential_level
            """),
            {"id": school_id},
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
                "national_median_debt": r.national_median_debt,
            }
            for r in rows
        ]
    if not programs:
        return {"error": f"No programs stored for school_id {school_id}"}
    return {"school_id": school_id, "school_name": school.name if school else None, "programs": programs}


def cip_occupations(cip_codes: list[str]) -> dict[str, list[dict]]:
    """Occupations each degree field leads to (CIP-SOC crosswalk), highest
    BLS salary first."""
    if not cip_codes:
        return {}
    with _connect_with_retry() as conn:
        rows = conn.execute(
            text("""
                SELECT c.code, o.occupation_code, o.name, o.annual_salary, o.typical_years_of_school
                FROM "CipOccupation" co
                JOIN "CipCode" c ON c.id = co.cip_id
                JOIN "OccupationSubCategory" o ON o.id = co.occupation_id
                WHERE c.code = ANY(:codes)
                ORDER BY o.annual_salary DESC
            """),
            {"codes": list(cip_codes)},
        )
        out: dict[str, list[dict]] = {}
        for r in rows:
            out.setdefault(r.code, []).append({
                "soc_code": r.occupation_code, "title": r.name, "annual_salary": float(r.annual_salary),
                "typical_years_of_school": _safe_float(r.typical_years_of_school),
            })
    return out


def occupations_by_title(titles: list[str]) -> list[dict]:
    """Occupations whose SOC title is exactly one of titles (any case), in the
    order given, with BLS salary. Titles that match nothing are dropped."""
    wanted = [t.strip().lower() for t in titles if t and t.strip()]
    if not wanted:
        return []
    params = {f"t{i}": t for i, t in enumerate(wanted)}
    names_sql = ", ".join(f":t{i}" for i in range(len(wanted)))
    with _connect_with_retry() as conn:
        rows = conn.execute(
            text(f'SELECT occupation_code, name, annual_salary FROM "OccupationSubCategory" '
                 f'WHERE lower(name) IN ({names_sql}) AND annual_salary IS NOT NULL'),
            params,
        )
        found = {r.name.lower(): {"soc_code": r.occupation_code, "title": r.name, "annual_salary": float(r.annual_salary)}
                 for r in rows}
    return [found[t] for t in dict.fromkeys(wanted) if t in found]


# path5 rank_by -> (ORDER BY on SchoolProgram p, columns a program needs to be ranked)
PROGRAM_RANK = {
    "debt_to_pay": ("p.median_debt::float / p.earnings_4yr ASC", ["earnings_4yr", "median_debt"]),
    "earnings_4yr": ("p.earnings_4yr DESC", ["earnings_4yr"]),
    "earnings_1yr": ("p.earnings_1yr DESC", ["earnings_1yr"]),
    "debt": ("p.median_debt ASC", ["median_debt", "earnings_4yr"]),
}

# Branch campuses share one family's program data (ope6_id); a school with no
# ope6_id is its own family. in_state: the campus is in a chosen state, or no
# states were chosen.
_PROGRAM_FAMILIES = """
    fam AS (
        SELECT s.school_id, s.name, s.city, s.state, s.student_size,
               coalesce(s.ope6_id, s.school_id::text) AS fam,
               (cast(:states AS text[]) IS NULL OR s.state = ANY(cast(:states AS text[]))) AS in_state
        FROM "School" s WHERE s.operating
    )"""


def rank_programs(cip_codes: list[str], level: int, states: list[str] | None, rank_by: str,
                  min_earnings_4yr: int | None, max_debt: int | None, limit: int) -> list[dict]:
    """path5: the top programs in these fields at one credential level, one per
    school family. A family counts when any campus is in the chosen states. Its
    figures come from its best program by rank_by (the in-state campus's row
    first, then the largest campus's); its name is the in-state campus, else
    the largest one."""
    order, needs = PROGRAM_RANK[rank_by]
    present = " AND ".join(f"p.{c} IS NOT NULL" for c in needs)
    with _connect_with_retry() as conn:
        rows = conn.execute(text(f"""
            WITH {_PROGRAM_FAMILIES},
            progs AS (
                SELECT p.*, f.fam, f.in_state, f.student_size FROM "SchoolProgram" p
                JOIN fam f ON f.school_id = p.school_id
                WHERE p.cip_code = ANY(:cips) AND p.credential_level = :level AND {present}
                  AND (cast(:min_pay AS int) IS NULL OR p.earnings_4yr >= cast(:min_pay AS int))
                  AND (cast(:max_debt AS int) IS NULL OR p.median_debt <= cast(:max_debt AS int))
            ),
            best AS (
                SELECT DISTINCT ON (p.fam) p.* FROM progs p
                WHERE EXISTS (SELECT 1 FROM fam f WHERE f.fam = p.fam AND f.in_state)
                ORDER BY p.fam, {order}, p.in_state DESC, p.student_size DESC NULLS LAST
            ),
            shown AS (
                SELECT DISTINCT ON (f.fam) f.fam, f.name, f.city, f.state FROM fam f
                WHERE f.fam IN (SELECT fam FROM best)
                ORDER BY f.fam, f.in_state DESC, f.student_size DESC NULLS LAST
            )
            SELECT p.school_id, p.cip_code, p.title, p.credential_level, p.earnings_1yr, p.earnings_4yr,
                   p.median_debt, sh.name AS school_name, sh.city, sh.state
            FROM best p JOIN shown sh ON sh.fam = p.fam
            ORDER BY {order}, p.school_id
            LIMIT :limit
        """), {"cips": list(cip_codes), "level": level, "states": states, "min_pay": min_earnings_4yr,
               "max_debt": max_debt, "limit": limit})
        return [{**dict(r._mapping), "credential": _CREDENTIAL_LEVELS.get(r.credential_level)} for r in rows]


def program_spread(cip_codes: list[str], level: int) -> dict:
    """path5: where every school's program in these fields sits nationally, one
    program per school family (its largest campus's): count, min, median, max
    of 1-yr and 4-yr earnings and median debt."""
    stats = ", ".join(
        f"count({c}) AS {c}_count, min({c}) AS {c}_min, "
        f"percentile_cont(0.5) WITHIN GROUP (ORDER BY {c}) AS {c}_median, max({c}) AS {c}_max"
        for c in ("earnings_1yr", "earnings_4yr", "median_debt"))
    with _connect_with_retry() as conn:
        r = conn.execute(text(f"""
            WITH {_PROGRAM_FAMILIES},
            one AS (
                SELECT DISTINCT ON (f.fam, p.cip_code) p.earnings_1yr, p.earnings_4yr, p.median_debt
                FROM "SchoolProgram" p JOIN fam f ON f.school_id = p.school_id
                WHERE p.cip_code = ANY(:cips) AND p.credential_level = :level
                  AND (p.earnings_1yr IS NOT NULL OR p.earnings_4yr IS NOT NULL)
                ORDER BY f.fam, p.cip_code, f.student_size DESC NULLS LAST
            )
            SELECT count(*) AS programs, {stats} FROM one
        """), {"cips": list(cip_codes), "level": level, "states": None}).first()
    m = r._mapping
    spread = {"programs": m["programs"]}
    for c in ("earnings_1yr", "earnings_4yr", "median_debt"):
        if m[f"{c}_count"]:
            spread[c] = {k: round(m[f"{c}_{k}"]) if k != "count" else m[f"{c}_{k}"]
                         for k in ("count", "min", "median", "max")}
    return spread
