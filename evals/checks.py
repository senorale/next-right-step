"""
Number checks on the report the model wrote: every figure in its text must come
from the code-built data, every stated difference must be the real gap between
the rows it names, and the figures a case requires must appear. Words aren't
checked: matching wording is too weak a test (revisit later).
"""

import html
import re

# Prose = text the LLM wrote: chat reply, headline, bullets, "What this means
# for you", limitations. Tables, charts, the notice, and the code-built notes
# are code.
PROSE_PATTERNS = [
    r'<p class="headline">(.*?)</p>',
    r'<p class="means">(.*?)</p>',
    r"<li>(.*?)</li>",
]
GAP_PHRASE = re.compile(r"\$\s?(\d[\d,]*)\s+(more|less|higher|lower)\b[^.$]*?\bthan\b([^.$]*)", re.I)


def _text(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def _sentences(texts: list[str]) -> list[str]:
    out = []
    for t in texts:
        out += [s for s in re.split(r"(?<=[.!?])\s+", t) if s]
    return out


def prose(response: str, report_html: str) -> list[str]:
    """Text the report model wrote; charts and the code-built notes are left out."""
    body = re.sub(r'<svg.*?</svg>|<ul class="note">.*?</ul>', "", report_html, flags=re.S)
    texts = [response]
    for pattern in PROSE_PATTERNS:
        texts += [_text(m) for m in re.findall(pattern, body, flags=re.S)]
    return [t for t in texts if t]


def _dollars(text: str) -> list[float]:
    return [float(m.replace(",", "")) for m in re.findall(r"\$\s?(\d[\d,]*)", text)]


def _report_figures(report_html: str) -> list[float]:
    """Dollar figures code rendered: table cells, chart values, cost notes."""
    cells = re.findall(r"<td>(.*?)</td>", report_html, flags=re.S)
    cells += [li for ul in re.findall(r'<ul class="note">(.*?)</ul>', report_html, flags=re.S) for li in re.findall(r"<li>(.*?)</li>", ul)]
    values = re.findall(r'class="val">(.*?)<', report_html)
    return [v for t in cells + values for v in _dollars(html.unescape(t))]


def _same(value: float, exact: float) -> bool:
    """The exact figure, or (for amounts of $1,000 or more) the figure rounded to
    the nearest hundred or thousand."""
    if abs(exact) < 1000:
        return value == exact
    return any(value == round(exact, -digits) for digits in (0, 2, 3))


# Code-built row tables: heading -> (cell count, debt column, salary column).
# The financial breakdown on most paths; path4's side-by-side table, which has no
# payoff; path5's ranked schools (salary: pay 4 years after graduating).
ROW_TABLES = {"Financial breakdown": (7, 2, 6), "Side by side": (5, 3, 4), "Schools ranked": (8, 6, 4)}


def _breakdown_rows(report_html: str) -> dict[str, dict]:
    """Rows of the code-built row table: name -> median salary and debt."""
    rows = {}
    for heading, (width, debt, salary) in ROW_TABLES.items():
        if f"<h2>{heading}</h2>" not in report_html:
            continue
        section = report_html.split(f"<h2>{heading}</h2>", 1)[1].split("</section>", 1)[0]
        for row in re.findall(r"<tr>(.*?)</tr>", section, flags=re.S):
            cells = [_text(c) for c in re.findall(r"<td>(.*?)</td>", row, flags=re.S)]
            if len(cells) >= width:
                money = [_dollars(c) for c in cells]
                rows[cells[0]] = {"debt": money[debt][0] if money[debt] else 0.0,
                                  "salary": money[salary][0] if money[salary] else 0.0}
    return rows


def _metric_rows(report_html: str) -> dict[str, dict]:
    """Rows of the metric tables above the financial breakdown: name -> {column: value}.
    path5's national spread table names measures, not options, so it's left out."""
    body = report_html.split("<h2>Financial breakdown</h2>", 1)[0].split("<h2>How much the school matters</h2>", 1)[0]
    rows: dict[str, dict] = {}
    for table in re.findall(r"<table>(.*?)</table>", body, flags=re.S):
        heads = [_text(h) for h in re.findall(r"<th>(.*?)</th>", table)]
        for row in re.findall(r"<tr>(.*?)</tr>", table, flags=re.S):
            cells = [_text(c) for c in re.findall(r"<td>(.*?)</td>", row, flags=re.S)]
            for head, cell in zip(heads[1:], cells[1:]):
                nums = _numbers(cell.replace("$", ""))
                if cells and nums:
                    rows.setdefault(cells[0], {})[head] = nums[0]
    return rows


GENERIC_LAST_WORDS = {"university", "college", "institute", "school", "campus", "technology", "sciences"}


def _aliases(name: str) -> list[str]:
    """Words a sentence uses for a row, e.g. "Lawyers" -> "lawyer"."""
    base = re.sub(r"\(.*?\)", "", name).lower()
    if "high school" in base:
        return ["high school", "diploma"]
    if "bachelor" in base:
        return ["bachelor"]
    words = re.findall(r"[a-z]+", base)
    if words[-1] in GENERIC_LAST_WORDS:
        # "Harvard University": the last word names every school.
        return [base.strip()]
    return [words[-1].rstrip("s")]


def _wrong_gaps(sentence: str, rows: dict[str, dict]) -> list[str]:
    """For "$X more ... than <row>": X must be the gap between the row named after
    "than" and another row the sentence names before it."""
    problems = []
    for match in GAP_PHRASE.finditer(sentence):
        amount, after = match.group(1), match.group(3)
        value = float(amount.replace(",", ""))
        before = sentence[: match.start(3)].lower()
        compared = [n for n in rows if any(a in after.lower() for a in _aliases(n))]
        subjects = [n for n in rows if any(a in before for a in _aliases(n)) and n not in compared]
        if not compared or not subjects:
            continue
        gaps = [
            abs(rows[s][metric] - rows[c][metric])
            for c in compared for s in subjects for metric in rows[s] if metric in rows[c]
        ]
        if not any(_same(value, g) for g in gaps):
            problems.append(f"${amount} isn't the gap between {subjects} and {compared}: {sentence[:120]}")
    return problems


def _numbers(text: str) -> list[float]:
    return [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)]


def run_checks(response: str, report_html: str, expect: dict | None = None) -> dict[str, dict]:
    """Each check -> {"pass": bool, "hits": [offending text]}."""
    texts = prose(response, report_html)
    sentences = _sentences(texts)
    figures = _report_figures(report_html)
    rows = _breakdown_rows(report_html)
    for name, values in _metric_rows(report_html).items():
        rows.setdefault(name, {}).update(values)
    gaps = [abs(a - b) for i, a in enumerate(figures) for b in figures[i + 1:]]

    results = {
        "report_rendered": [] if report_html else ["no report HTML"],
        # Every dollar figure in the text is a code-built figure or a gap between two.
        "figures_from_data": [
            s for s in sentences
            if any(not any(_same(v, f) for f in figures + gaps) for v in _dollars(s))
        ],
        "gaps_match_rows": [p for s in sentences for p in _wrong_gaps(s, rows)],
    }
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
