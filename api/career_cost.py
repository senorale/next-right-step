"""
Education cost per occupation and the path1 (college vs alternatives) options,
ported from the web app (src/lib/career-cost.ts and
src/app/college-vs-alternatives/CollegeVsAlternatives.tsx) so the chat report
and the College vs alternatives page show the same numbers.

Cost is median student debt, not tuition: debt is what students actually
borrow after grants and family help, and College Scorecard reports it per
degree field and credential (ProgramDebt).
"""

from sqlalchemy import text

from db import _connect_with_retry

HS_SALARY = 46_748  # BLS median weekly earnings, high school diploma, x 52
BACHELOR_SALARY = 77_636  # BLS median weekly earnings, bachelor's degree, x 52
BACHELOR_YEARS = 4
CASHIER_CODE = "41-2011"
ELECTRICIAN_CODE = "47-2111"

CREDENTIAL_LABELS = {
    1: "certificate",
    2: "associate's degree",
    3: "bachelor's degree",
    5: "master's degree",
    6: "doctoral or professional degree",
    7: "doctoral or professional degree",
}


def _credential_levels(years: float) -> list[int]:
    """ProgramDebt / Scorecard credential levels by typical years of school."""
    if years <= 0:
        return []
    if years <= 1:
        return [1]
    if years <= 2:
        return [2]
    if years <= 4:
        return [3]
    if years <= 6:
        return [5]
    return [6, 7]


def _weighted_debt(rows) -> tuple[int, int] | None:
    n = sum(r.sample_size for r in rows)
    if n == 0:
        return None
    return round(sum(r.median_debt * r.sample_size for r in rows) / n), n


def national_bachelors_debt() -> int:
    """Median bachelor's debt across all degree fields, weighted by schools reporting."""
    with _connect_with_retry() as conn:
        rows = conn.execute(text(
            """SELECT median_debt, sample_size FROM "ProgramDebt"
               WHERE school_type = 'all' AND credential_level = 3 AND sample_size > 0"""
        )).all()
    result = _weighted_debt(rows)
    return result[0] if result else 0


def career_cost(occupation_code: str) -> dict | None:
    """Salary, years of school, and education debt for one occupation.

    Debt is the median debt across every degree field linked to the occupation
    (CIP-SOC crosswalk), weighted by sample size, at the credential level that
    matches its typical years of school. With no linked field data, it falls
    back to the fields' 2-digit CIP families. Graduate credentials add the
    national median bachelor's debt, since they require a bachelor's first.
    """
    with _connect_with_retry() as conn:
        occ = conn.execute(text(
            """SELECT id, name, annual_salary, typical_years_of_school
               FROM "OccupationSubCategory" WHERE occupation_code = :code LIMIT 1"""
        ), {"code": occupation_code}).first()
        if occ is None:
            return None
        years = float(occ.typical_years_of_school or 0)
        years = int(years) if years.is_integer() else years
        levels = _credential_levels(years)
        debt, estimated = (0, False) if not levels else (None, False)
        if levels:
            cips = [r.code for r in conn.execute(text(
                """SELECT c.code FROM "CipOccupation" co JOIN "CipCode" c ON c.id = co.cip_id
                   WHERE co.occupation_id = :id"""
            ), {"id": occ.id})]
            rows = conn.execute(text(
                """SELECT pd.median_debt, pd.sample_size FROM "ProgramDebt" pd
                   JOIN "CipOccupation" co ON co.cip_id = pd.cip_id
                   WHERE co.occupation_id = :id AND pd.school_type = 'all'
                     AND pd.credential_level = ANY(:levels) AND pd.sample_size > 0"""
            ), {"id": occ.id, "levels": levels}).all()
            result = _weighted_debt(rows)
            if result is None and cips:
                families = sorted({c[:2] for c in cips})
                rows = conn.execute(text(
                    """SELECT pd.median_debt, pd.sample_size FROM "ProgramDebt" pd
                       JOIN "CipCode" c ON c.id = pd.cip_id
                       WHERE pd.school_type = 'all' AND pd.credential_level = ANY(:levels)
                         AND pd.sample_size > 0 AND LEFT(c.code, 2) = ANY(:families)"""
                ), {"levels": levels, "families": families}).all()
                result = _weighted_debt(rows)
                estimated = result is not None
            debt = result[0] if result else None

    graduate = any(level >= 5 for level in levels)
    undergrad = national_bachelors_debt() if graduate else 0
    label = CREDENTIAL_LABELS[levels[0]] if levels else None
    if not levels:
        basis = "No school required"
    elif debt is None:
        basis = f"No debt data for a {label} in related fields"
    else:
        basis = (
            f"{'Estimated from median' if estimated else 'Median'} debt for a {label} in "
            f"{'the broader field family' if estimated else 'related fields'}"
            + (", plus the national median bachelor's debt" if graduate else "")
        )
    return {
        "name": occ.name,
        "occupation_code": occupation_code,
        "salary": float(occ.annual_salary),
        "years_in_school": years,
        "credential": label,
        "debt": None if debt is None else debt + undergrad,
        "cost_basis": basis,
    }


def career_option(cost: dict) -> dict:
    """An occupation as an option row (see options.py)."""
    return {
        "option_id": f"occ:{cost['occupation_code']}",
        "name": cost["name"],
        "short_label": cost["name"],
        "education": (cost["credential"] or "No degree required").capitalize(),
        "years_in_school": cost["years_in_school"],
        "debt": cost["debt"],
        "cost_basis": cost["cost_basis"],
        "expected_salary": cost["salary"],
        "salary_basis": "BLS median annual wage",
    }


def _user_option(median: dict, numbers: dict, bachelors_debt: int) -> dict | None:
    """The chosen occupation with the user's own numbers. Years of school come
    from the data; tuition the user gave counts as fully borrowed (like Compare
    schools), and anything they left out comes from the medians, labeled."""
    if not numbers:
        return None
    years = median["years_in_school"]
    undergrad_years = min(years, BACHELOR_YEARS)
    grad_years = max(years - BACHELOR_YEARS, 0)
    tuition_given = any(k in numbers for k in ("total_education_cost", "undergrad_tuition_per_year", "graduate_tuition_per_year"))
    if not years:
        cost, basis = 0, "No school required"
    elif "total_education_cost" in numbers:
        cost = numbers["total_education_cost"]
        basis = f"Your total school cost (${cost:,.0f}), assumed fully borrowed"
    elif not tuition_given:
        cost, basis = median["debt"] or 0, f"{median['cost_basis']} (no tuition given)"
    else:
        cost, parts = 0.0, []
        if "undergrad_tuition_per_year" in numbers:
            cost += numbers["undergrad_tuition_per_year"] * undergrad_years
            parts.append(f"your undergrad tuition (${numbers['undergrad_tuition_per_year']:,.0f}/yr) x {undergrad_years:g} yrs")
        else:
            cost += bachelors_debt
            parts.append("national median bachelor's debt")
        if grad_years and "graduate_tuition_per_year" in numbers:
            cost += numbers["graduate_tuition_per_year"] * grad_years
            parts.append(f"your graduate tuition (${numbers['graduate_tuition_per_year']:,.0f}/yr) x {grad_years:g} yrs")
        elif grad_years:
            cost += (median["debt"] or 0) - bachelors_debt
            parts.append("median graduate debt")
        basis = ", plus ".join(parts) + "; tuition assumed fully borrowed"
    salary = numbers.get("expected_salary")
    return {
        **median,
        "option_id": f"{median['option_id']}:yours",
        "name": f"{median['name']} (your numbers)",
        "short_label": f"{median['short_label']} (yours)",
        "debt": round(cost),
        "cost_basis": basis,
        "expected_salary": salary if salary is not None else median["expected_salary"],
        "salary_basis": "Your expected salary" if salary is not None else median["salary_basis"],
        "user_numbers": True,
        "your_inputs": dict(numbers),
    }


def path1_options(occupation_code: str | None, user_numbers: dict | None = None) -> list[dict]:
    """The five path1 rows, same as the College vs alternatives page, plus a
    sixth with the user's own numbers for their chosen occupation when given."""
    options = [{
        "option_id": "baseline:hs",
        "name": "High school diploma",
        "short_label": "HS diploma",
        "education": "High school diploma",
        "years_in_school": 0,
        "debt": 0,
        "cost_basis": "No school required",
        "expected_salary": HS_SALARY,
        "salary_basis": "BLS median weekly earnings x 52",
    }]
    for code in (CASHIER_CODE, ELECTRICIAN_CODE):
        cost = career_cost(code)
        if cost:
            options.append(career_option(cost))
    bachelors = {
        "option_id": "baseline:bachelors",
        "name": "Bachelor's degree (median)",
        "short_label": "Bachelor's",
        "education": "Bachelor's degree",
        "years_in_school": BACHELOR_YEARS,
        "debt": national_bachelors_debt(),
        "cost_basis": "National median bachelor's debt across all degree fields",
        "expected_salary": BACHELOR_SALARY,
        "salary_basis": "BLS median weekly earnings x 52",
    }
    options.append(bachelors)
    chosen = career_cost(occupation_code) if occupation_code else None
    if chosen:
        option = career_option(chosen)
        mine = _user_option(option, user_numbers or {}, bachelors["debt"])
        # Stated outright so the report never computes a number itself.
        option["graduate_school_required"] = chosen["years_in_school"] > BACHELOR_YEARS
        option["years_beyond_bachelors"] = max(chosen["years_in_school"] - BACHELOR_YEARS, 0)
        option["salary_gap_vs_bachelors"] = round(option["expected_salary"] - bachelors["expected_salary"])
        if option["debt"] is not None:
            option["debt_gap_vs_bachelors"] = round(option["debt"] - bachelors["debt"])
        if mine:
            option["name"] = f"{option['name']} (national median)"
            mine["graduate_school_required"] = option["graduate_school_required"]
            mine["years_beyond_bachelors"] = option["years_beyond_bachelors"]
            mine["salary_gap_vs_median"] = round(mine["expected_salary"] - option["expected_salary"])
            if option["debt"] is not None:
                mine["debt_gap_vs_median"] = round(mine["debt"] - option["debt"])
        options.append(option)
        if mine:
            options.append(mine)
    return options
