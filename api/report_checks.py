"""
Number checks on the text the report model wrote: every dollar figure must come
from the code-built data (or be the difference between two such figures), and
every stated difference ("$X more than Y") must be the real gap between the rows
it names. The report step runs them on every report (agent.write_report) and
the evals score with them (evals/checks.py).

The checks read the rendered HTML, so they see exactly what the user sees:
the tables and charts code drew, and the prose the model wrote.
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


def _names(text: str, name: str) -> bool:
    """Whether text names the row, by whole words: "mathematic" (Mathematics)
    isn't named by "Mathematical Science Occupations"."""
    return any(re.search(rf"\b{re.escape(a)}s?\b", text) for a in _aliases(name))


def _national_gaps(report_html: str) -> list[float]:
    """path5's national spread table (lowest, median, highest school per
    measure): each median, and how far the lowest and highest sit from it."""
    if "<h2>How much the school matters</h2>" not in report_html:
        return []
    table = report_html.split("<h2>How much the school matters</h2>", 1)[1].split("</table>", 1)[0]
    out = []
    for row in re.findall(r"<tr>(.*?)</tr>", table, flags=re.S):
        cells = [_numbers(_text(c).replace("$", "")) for c in re.findall(r"<td>(.*?)</td>", row, flags=re.S)]
        if len(cells) >= 4 and all(cells[1:4]):
            low, median, high = cells[1][0], cells[2][0], cells[3][0]
            out.append((median, median - low, high - median))
    return out


def _wrong_gaps(sentence: str, rows: dict[str, dict], national: list | None = None) -> list[str]:
    """For "$X more ... than <row>": X must be the gap between the row named after
    "than" and another row the sentence names before it. "than the national
    median" may also mean path5's national spread: a row's gap from a national
    median, or the lowest or highest school's."""
    problems = []
    for match in GAP_PHRASE.finditer(sentence):
        amount, after = match.group(1), match.group(3)
        # The compared row ends at the clause: "than the national median, and Duquesne ..."
        # (row names can hold commas and "and": "Computer and Information Sciences, General").
        after = re.split(r";|,\s*(?:and|but)\b", after)[0]
        value = float(amount.replace(",", ""))
        before = sentence[: match.start(3)].lower()
        compared = [n for n in rows if _names(after.lower(), n)]
        subjects = [n for n in rows if _names(before, n) and n not in compared]
        if "national median" in after.lower() and national:
            gaps = [abs(v - median) for s in subjects for v in rows[s].values() for median, _, _ in national]
            gaps += [g for _, below, above in national for g in (below, above)]
            if any(_same(value, g) for g in gaps):
                continue
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


def report_facts(report_html: str) -> dict:
    """What the checks compare the prose with: the dollar figures code rendered
    (and every difference between two), the row tables' values, and path5's
    national spread."""
    figures = _report_figures(report_html)
    rows = _breakdown_rows(report_html)
    for name, values in _metric_rows(report_html).items():
        rows.setdefault(name, {}).update(values)
    return {
        "figures": figures + [abs(a - b) for i, a in enumerate(figures) for b in figures[i + 1:]],
        "rows": rows,
        "national": _national_gaps(report_html),
    }


def unsupported_figures(sentence: str, facts: dict) -> bool:
    """A dollar figure in the sentence that is neither a rendered figure nor a gap between two."""
    return any(not any(_same(v, f) for f in facts["figures"]) for v in _dollars(sentence))


def wrong_gaps(sentence: str, facts: dict) -> list[str]:
    return _wrong_gaps(sentence, facts["rows"], facts["national"])


def number_problems(response: str, report_html: str) -> dict[str, list[str]]:
    """figures_from_data: sentences with an unsupported figure; gaps_match_rows:
    stated differences that aren't the real gap."""
    facts = report_facts(report_html)
    sentences = _sentences(prose(response, report_html))
    return {
        "figures_from_data": [s for s in sentences if unsupported_figures(s, facts)],
        "gaps_match_rows": [p for s in sentences for p in wrong_gaps(s, facts)],
    }


def sentence_ok(sentence: str, facts: dict) -> bool:
    return not unsupported_figures(sentence, facts) and not wrong_gaps(sentence, facts)


def split_sentences(text: str) -> list[str]:
    return _sentences([text])
