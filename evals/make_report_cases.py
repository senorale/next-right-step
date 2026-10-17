"""
Builds report_cases.jsonl: fixed report inputs for the report-generation eval
(evals/report_eval.py), made from the current data with fixed intake answers and
user numbers. No model calls. Rerun when the data or the input shape changes,
then review the diff; expectations live in CASES below.

    api/venv/bin/python evals/make_report_cases.py
"""

import json
from pathlib import Path

import run  # noqa: F401  loads .env and puts api/ on the import path
from run import agent
import db
import options

EVALS = Path(__file__).resolve().parent

PATH1 = {"path_type": "path1", "data_source": "medians"}
def path2(case_id: str, intake: dict, expect: dict) -> dict:
    """A path2 case: the calls code makes from intake (agent._planned_calls),
    plus expectations; allowed_metrics come from the user's compare_metrics."""
    intake = {"path_type": "path2", **intake}
    allowed = options.allowed_metrics(intake)
    return {"id": case_id, "intake": intake, "calls": agent._planned_calls(intake),
            "expect": {"allowed_metrics": allowed, **expect}}


def path3(case_id: str, intake: dict, expect: dict) -> dict:
    """A path3 case: the compare_programs call a correct agent makes; programs
    are ranked by program_priority in code."""
    intake = {"path_type": "path3", **intake}
    return {"id": case_id, "intake": intake, "calls": [("compare_programs", {"school_id": int(intake["school_id"])})],
            "expect": expect}


def path4(case_id: str, intake: dict, careers: list[tuple[str, str, str]], expect: dict) -> dict:
    """A path4 case: the compare_careers call a correct agent makes. careers are
    (typed, soc_code, title), as career_matches stores them."""
    intake = {"path_type": "path4", "careers_to_compare": ", ".join(t for t, _, _ in careers),
              "career_matches": json.dumps([{"typed": t, "soc_code": c, "title": n} for t, c, n in careers]), **intake}
    return {"id": case_id, "intake": intake, "calls": [("compare_careers", {})], "expect": expect}


def path5(case_id: str, intake: dict, expect: dict) -> dict:
    """A path5 case: the rank_schools_for_career call a correct agent makes,
    with the career's programs as the target_career check stores them."""
    intake = {"path_type": "path5", "career_programs": json.dumps(db.career_programs(intake["target_career_code"])),
              "location_scope": "states" if intake.get("target_states") else "national", "requirements": "none", **intake}
    return {"id": case_id, "intake": intake, "calls": [("rank_schools_for_career", {})], "expect": expect}


# Every path5 report: the code-built caveats, no payoff, and pay 1 year out never called starting salary.
PATH5_EXPECT = {"no_payoff": True, "forbidden_words": ["starting salary"],
                "required_text": ["federal student loan debt", "whole institution", "already working in the field"]}

NO_JOB = {"include_current_role": "no"}
RETAIL_MANAGER = {"include_current_role": "yes", "current_role": "retail store manager", "current_role_code": "41-1011",
                  "current_role_title": "First-Line Supervisors of Retail Sales Workers"}
RETAIL_MANAGER_PAY = {**RETAIL_MANAGER, "include_salary": "yes", "current_salary": "$25/hr, 40 hours",
                      "current_salary_value": "52000", "compare_to_median": "yes"}
ELECTRICIAN = ("electrician", "47-2111", "Electricians")

UF = {"school_name": "UF", "school_id": "134130", "school_matched_name": "University of Florida"}
GT = {"school_name": "Georgia Tech", "school_id": "139755", "school_matched_name": "Georgia Institute of Technology-Main Campus"}
CS = "Computer and Information Sciences, General"
NURSING = "Registered Nursing, Nursing Administration, Nursing Research and Clinical Nursing"

CASES = [
    # required_figures: numbers the report's text must state (exact, or rounded for dollar amounts).
    {"id": "path1-lawyer-medians", "intake": {**PATH1, "occupation": "lawyer", "occupation_code": "23-1011"},
     "expect": {"required_figures": [7, 3, 68124, 107333]}},
    {"id": "path1-doctor-medians", "intake": {**PATH1, "occupation": "doctor", "occupation_code": "29-1216"},
     "expect": {"required_figures": [10, 6, 145674, 196351]}},
    {"id": "path1-software-medians", "intake": {**PATH1, "occupation": "software developer", "occupation_code": "15-1252"},
     "expect": {"required_figures": [4, 132270]}},
    {"id": "path1-lawyer-your-numbers",
     "intake": {"path_type": "path1", "data_source": "specific", "occupation": "lawyer", "occupation_code": "23-1011",
                "specific_numbers": "undergrad tuition is $10,000 a year, law school tuition is $55,000 a year, and I expect to make $110,000 after law school"},
     "user_numbers": {"undergrad_tuition_per_year": 10000, "graduate_tuition_per_year": 55000, "expected_salary": 110000},
     "expect": {"required_figures": [7, 110000, 205000], "headline_figures": [110000, 205000]}},
    {"id": "path1-software-your-numbers-low-salary",
     "intake": {"path_type": "path1", "data_source": "specific", "occupation": "software developer", "occupation_code": "15-1252",
                "specific_numbers": "tuition $12,000 a year, and my offer is $40,000"},
     "user_numbers": {"undergrad_tuition_per_year": 12000, "expected_salary": 40000},
     "expect": {"required_figures": [40000, 48000]}},
    {"id": "path1-electrician-chosen", "intake": {**PATH1, "occupation": "electrician", "occupation_code": "47-2111"},
     "expect": {"required_figures": [61590]}},
    {"id": "path1-capped-salary", "intake": {**PATH1, "occupation": "pathologist", "occupation_code": "29-1222"},
     "expect": {"required_figures": [10, 6]}},
    # ranked_by: [row field or metric, "asc" | "desc"] the shown schools must follow.
    path2("path2-named-schools",
          {"has_specific_schools": "yes", "target_schools": "University of Florida, Georgia Tech, NYU",
           "compare_metrics": "Earnings after graduation|Net price / cost|Graduation rate", "rank_by": "Earnings after graduation",
           "school_picks": "134130|139755|193900"},
          {"required_options": ["school:134130", "school:139755", "school:193900"], "forbidden_options": ["school:484473"],
           "ranked_by": ["expected_salary", "desc"], "required_figures": [114210]}),
    path2("path2-abbreviations",
          {"has_specific_schools": "yes", "target_schools": "UF and FSU",
           "compare_metrics": "Net price / cost|Debt at graduation", "rank_by": "Net price / cost",
           "school_picks": "134130|134097"},
          {"required_options": ["school:134130", "school:134097"], "forbidden_options": ["school:484473"],
           "ranked_by": ["avg_net_price", "asc"]}),
    path2("path2-by-state",
          {"has_specific_schools": "no", "target_location": "Colorado",
           "compare_metrics": "Net price / cost|Graduation rate", "rank_by": "Net price / cost",
           "target_places": "Colorado", "target_states": "CO"},
          {"min_options": ["school:", 3], "ranked_by": ["avg_net_price", "asc"]}),
    path3("path3-cs-nursing",
          {**UF, "school_situation": "deciding", "programs": "computer science, nursing",
           "program_list": json.dumps([CS, NURSING]), "program_priority": "Earning potential"},
          {"required_options": ["program:134130:1101:3", "program:134130:5138:3", "occ:15-1252", "occ:29-1141"],
           "ranked_by": ["expected_salary", "desc", "program:"], "required_figures": [46429]}),
    path3("path3-not-sure-career-options",
          {**UF, "school_situation": "deciding", "programs": "not sure", "program_list": "[]",
           "program_priority": "Many career options"},
          {"min_options": ["program:", 3], "ranked_by": ["career_options", "desc", "program:"]}),
    # Mathematics at Georgia Tech has no debt data: its cost is the national median for the field.
    path3("path3-national-debt",
          {**GT, "school_situation": "current", "programs": "math, CS",
           "program_list": json.dumps(["Mathematics", CS]), "program_priority": "Earning potential"},
          {"required_options": ["program:139755:2701:3", "program:139755:1101:3"],
           "ranked_by": ["expected_salary", "desc", "program:"], "required_figures": [28529]}),
    # path4: careers side by side, no payoff.
    path4("path4-trade-vs-law", NO_JOB, [ELECTRICIAN, ("lawyer", "23-1011", "Lawyers")],
          {"required_options": ["occ:47-2111", "occ:23-1011"], "no_payoff": True}),
    path4("path4-three-careers", NO_JOB,
          [("registered nurse", "29-1141", "Registered Nurses"), ("pharmacist", "29-1051", "Pharmacists"),
           ("software developer", "15-1252", "Software Developers")],
          {"required_options": ["occ:29-1141", "occ:29-1051", "occ:15-1252"], "no_payoff": True}),
    path4("path4-current-job", RETAIL_MANAGER, [ELECTRICIAN],
          {"required_options": ["occ:47-2111", "occ:41-1011"], "no_payoff": True}),
    path4("path4-current-job-pay", RETAIL_MANAGER_PAY, [ELECTRICIAN],
          {"required_options": ["occ:47-2111", "current:pay", "occ:41-1011"], "no_payoff": True}),
    # path5: schools ranked for one career; code orders them by rank_by.
    path5("path5-lawyer-national",
          {"target_career": "lawyer", "target_career_code": "23-1011", "target_career_title": "Lawyers",
           "target_fields": "2201", "target_level": "7", "rank_by": "debt_to_pay"},
          {**PATH5_EXPECT, "required_options": ["program:166027:2201:7", "program:215062:2201:7", "program:134130:2201:7"],
           "ranked_by": ["debt_to_4yr_earnings", "asc", "program:"]}),
    path5("path5-nurse-florida",
          {"target_career": "registered nurse", "target_career_code": "29-1141", "target_career_title": "Registered Nurses",
           "target_level": "3", "target_location": "Florida", "target_places": "Florida", "target_states": "FL",
           "rank_by": "earnings_4yr"},
          {**PATH5_EXPECT, "min_options": ["program:", 10], "ranked_by": ["earnings_4yr_after_graduation", "desc", "program:"]}),
    path5("path5-software-california",
          {"target_career": "software developer", "target_career_code": "15-1252", "target_career_title": "Software Developers",
           "target_fields": "1107|1409", "target_level": "3", "target_location": "California", "target_places": "California",
           "target_states": "CA", "rank_by": "debt_to_pay"},
          {**PATH5_EXPECT, "required_options": ["program:243744:1107:3", "program:110662:1409:3"],
           "ranked_by": ["debt_to_4yr_earnings", "asc", "program:"]}),
    path5("path5-pharmacist-max-debt",
          {"target_career": "pharmacist", "target_career_code": "29-1051", "target_career_title": "Pharmacists",
           "target_fields": "5120", "target_level": "7", "requirements": "max_debt", "max_debt": "$50,000",
           "max_debt_value": "50000", "rank_by": "debt_to_pay"},
          {**PATH5_EXPECT, "required_options": ["program:215293:5120:7", "program:212106:5120:7"]}),
]


def main() -> None:
    lines = []
    for case in CASES:
        intake = case["intake"]
        # What the agent gets back from the calls a correct run makes.
        tools = agent._dispatch_for(case.get("user_numbers") or {}, intake)
        calls = case.get("calls") or [("compare_education_paths", {"occupation_code": intake["occupation_code"]})]
        data_blocks = [{"type": name, "data": tools[name](args)} for name, args in calls]
        for block in data_blocks:
            if "error" in block["data"]:
                raise SystemExit(f"{case['id']}: {block['data']['error']}")
        content, rows = agent.build_report_input(intake, data_blocks)
        lines.append(json.dumps({"id": case["id"], "report_input": content, "expect": case["expect"]}, default=str))
        shown = (f"occ:{intake.get('occupation_code')}", "school:", "program:") + (("occ:", "current:") if intake["path_type"] == "path4" else ())
        chosen = [r for r in rows if r["option_id"].startswith(shown)]
        print(case["id"], [(o["name"], o["years_in_school"], o["debt"], o["expected_salary"]) for o in chosen])
    (EVALS / "report_cases.jsonl").write_text("\n".join(lines) + "\n")
    print(f"wrote {len(lines)} cases")


if __name__ == "__main__":
    main()
