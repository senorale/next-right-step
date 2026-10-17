"""
Report checks for the evals. The number checks (every figure in the text comes
from the code-built data, every stated difference is the real gap between the
rows it names) live in api/report_checks.py, which the report step also runs in
production; this adds the per-case expectations: the figures a case requires,
and which rows the report shows and how. Words aren't checked: matching wording
is too weak a test (revisit later).
"""

import html
import re

from report_checks import _breakdown_rows, _numbers, _same, _text, number_problems, prose


def run_checks(response: str, report_html: str, expect: dict | None = None) -> dict[str, dict]:
    """Each check -> {"pass": bool, "hits": [offending text]}."""
    texts = prose(response, report_html)
    results = {"report_rendered": [] if report_html else ["no report HTML"], **number_problems(response, report_html)}
    if expect and expect.get("required_figures"):
        found = _numbers(" ".join(texts))
        results["required_figures"] = [
            f"missing {n:,}" for n in expect["required_figures"] if not any(_same(v, n) for v in found)
        ]
    if expect and expect.get("headline_figures"):
        # The headline is also the chat reply (response), the first thing the user reads.
        found = _numbers(response)
        results["headline_figures"] = [
            f"headline missing {n:,}" for n in expect["headline_figures"] if not any(_same(v, n) for v in found)
        ]
    return {name: {"pass": not h, "hits": h} for name, h in results.items()}


def _value(row: dict, key: str):
    return row.get(key) if key in row else (row.get("metrics") or {}).get(key)


def choice_checks(report_html: str, rows: list[dict], expect: dict | None) -> dict[str, dict]:
    """Which rows the report shows and how: rows the user named appear, rows they
    didn't ask for don't, the order follows their ranking, and metric tables
    show only the metrics they chose."""
    from report import METRIC_FORMATS

    expect = expect or {}
    by_name = {r["name"]: r for r in rows}
    shown = [by_name[html.unescape(n)] for n in _breakdown_rows(report_html) if html.unescape(n) in by_name]
    shown_ids = [r["option_id"] for r in shown]
    results: dict[str, list[str]] = {}
    if "required_options" in expect:
        results["required_options"] = [f"missing {i}" for i in expect["required_options"] if i not in shown_ids]
    if "forbidden_options" in expect:
        results["forbidden_options"] = [f"shows {i}" for i in expect["forbidden_options"] if i in shown_ids]
    if "min_options" in expect:
        prefix, least = expect["min_options"]
        count = sum(i.startswith(prefix) for i in shown_ids)
        results["min_options"] = [] if count >= least else [f"{count} {prefix} rows, expected at least {least}"]
    if "ranked_by" in expect:
        # [key, direction] or [key, direction, option_id prefix of the ranked rows].
        key, direction, *prefix = expect["ranked_by"]
        # Baselines (high school, bachelor's) are references, not ranked options.
        values = [(r["name"], _value(r, key)) for r in shown
                  if not r["option_id"].startswith("baseline:") and r["option_id"].startswith(tuple(prefix) or "")
                  and _value(r, key) is not None]
        ordered = sorted(values, key=lambda v: v[1], reverse=direction == "desc")
        results["ranked_by"] = [] if values == ordered else [f"order {[n for n, _ in values]}, expected {[n for n, _ in ordered]}"]
    if "no_payoff" in expect:
        # path4 compares careers on salary, school, and debt; a payoff would restate path1.
        results["no_payoff"] = [f"report mentions {w}" for w in ("payoff", "pays off", "Financial breakdown")
                                if w.lower() in report_html.lower()]
    if "required_text" in expect:
        # Code-built text every report on this path carries (path5's data caveats).
        text = html.unescape(report_html)
        results["required_text"] = [f"missing {t!r}" for t in expect["required_text"] if t not in text]
    if "forbidden_words" in expect:
        # Words the model's text must not use (path5: "starting salary" for pay 1 year out).
        written = " ".join(prose("", report_html)).lower()
        results["forbidden_words"] = [f"says {w!r}" for w in expect["forbidden_words"] if w.lower() in written]
    if "allowed_metrics" in expect:
        allowed = {METRIC_FORMATS[k][0] for k in expect["allowed_metrics"]} | {"Option"}
        body = report_html.split("<h2>Financial breakdown</h2>", 1)[0]
        headers = [_text(h) for t in re.findall(r"<thead>(.*?)</thead>", body, flags=re.S) for h in re.findall(r"<th>(.*?)</th>", t)]
        results["allowed_metrics"] = [f"table shows {h}" for h in headers if h not in allowed]
    return {name: {"pass": not h, "hits": h} for name, h in results.items()}
