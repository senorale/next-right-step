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
import options

EVALS = Path(__file__).resolve().parent

PATH1 = {"path_type": "path1", "data_source": "medians"}
def path2(case_id: str, intake: dict, calls: list[dict], expect: dict) -> dict:
    """A path2 case: the search_schools calls a correct agent makes, plus
    expectations; allowed_metrics come from the user's compare_metrics."""
    intake = {"path_type": "path2", **intake}
    allowed = options.allowed_metrics(intake)
    return {"id": case_id, "intake": intake, "calls": [("search_schools", c) for c in calls],
            "expect": {"allowed_metrics": allowed, **expect}}


def path3(case_id: str, intake: dict, expect: dict) -> dict:
    """A path3 case: the compare_programs call a correct agent makes; programs
    are ranked by program_priority in code."""
    intake = {"path_type": "path3", **intake}
    return {"id": case_id, "intake": intake, "calls": [("compare_programs", {"school_id": int(intake["school_id"])})],
            "expect": expect}


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
           "compare_metrics": "Earnings after graduation|Net price / cost|Graduation rate", "rank_by": "Earnings after graduation"},
          [{"name": "University of Florida", "sort_by": "earnings"}, {"name": "Georgia Institute of Technology", "sort_by": "earnings"},
           {"name": "New York University", "sort_by": "earnings"}],
          {"required_options": ["school:134130", "school:139755", "school:193900"], "forbidden_options": ["school:484473"],
           "ranked_by": ["expected_salary", "desc"], "required_figures": [102772]}),
    path2("path2-abbreviations",
          {"has_specific_schools": "yes", "target_schools": "UF and FSU",
           "compare_metrics": "Net price / cost|Debt at graduation", "rank_by": "Net price / cost"},
          [{"name": "University of Florida", "sort_by": "net_price"}, {"name": "Florida State University", "sort_by": "net_price"}],
          {"required_options": ["school:134130", "school:134097"], "forbidden_options": ["school:484473"],
           "ranked_by": ["avg_net_price", "asc"]}),
    path2("path2-by-state",
          {"has_specific_schools": "no", "target_location": "Colorado",
           "compare_metrics": "Net price / cost|Graduation rate", "rank_by": "Net price / cost"},
          [{"state": "CO", "sort_by": "net_price"}],
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
        chosen = [r for r in rows if r["option_id"].startswith((f"occ:{intake.get('occupation_code')}", "school:", "program:"))]
        print(case["id"], [(o["name"], o["years_in_school"], o["debt"], o["expected_salary"]) for o in chosen])
    (EVALS / "report_cases.jsonl").write_text("\n".join(lines) + "\n")
    print(f"wrote {len(lines)} cases")


if __name__ == "__main__":
    main()
