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


def _breakdown_rows(report_html: str) -> dict[str, dict]:
    """Rows of the code-built financial breakdown: name -> median salary and debt."""
    section = report_html.split("<h2>Financial breakdown</h2>", 1)[-1]
    rows = {}
    for row in re.findall(r"<tr>(.*?)</tr>", section, flags=re.S):
        cells = [_text(c) for c in re.findall(r"<td>(.*?)</td>", row, flags=re.S)]
        if len(cells) >= 7:
            money = [_dollars(c) for c in cells]
            rows[cells[0]] = {"debt": money[2][0] if money[2] else 0.0, "salary": money[6][0] if money[6] else 0.0}
    return rows


def _aliases(name: str) -> list[str]:
    """Words a sentence uses for a row, e.g. "Lawyers" -> "lawyer"."""
    base = re.sub(r"\(.*?\)", "", name).lower()
    if "high school" in base:
        return ["high school", "diploma"]
    if "bachelor" in base:
        return ["bachelor"]
    last = re.findall(r"[a-z]+", base)[-1]
    return [last.rstrip("s")]


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
            for c in compared for s in subjects for metric in ("salary", "debt")
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
