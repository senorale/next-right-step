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

EVALS = Path(__file__).resolve().parent

PATH1 = {"path_type": "path1", "data_source": "medians"}
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
]


def main() -> None:
    lines = []
    for case in CASES:
        intake = case["intake"]
        data_blocks = agent.path1_data_blocks(intake)
        content, fixed = agent.build_report_input(intake, data_blocks, "", case.get("user_numbers"))
        if not fixed:
            raise SystemExit(f"{case['id']}: no path1 options built")
        lines.append(json.dumps({"id": case["id"], "report_input": content, "expect": case["expect"]}, default=str))
        chosen = fixed[4:]
        print(case["id"], [(o["name"], o["years_in_school"], o["debt"], o["expected_salary"]) for o in chosen])
    (EVALS / "report_cases.jsonl").write_text("\n".join(lines) + "\n")
    print(f"wrote {len(lines)} cases")


if __name__ == "__main__":
    main()
