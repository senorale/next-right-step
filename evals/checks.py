"""
Deterministic checks on what the user sees: the chat reply and the rendered
report HTML. They don't depend on how the report is built, so the same checks
benchmark any change to prompts or report code.
"""

import html
import re

# Prose = text the LLM wrote: chat reply, headline, bullets, "What this means
# for you", limitations. Tables, charts, the notice and the footer are code.
PROSE_PATTERNS = [
    r'<p class="headline">(.*?)</p>',
    r'<p class="means">(.*?)</p>',
    r"<li>(.*?)</li>",
]

DOLLAR = re.compile(r"\$\s?(?!0\b)\d[\d,]*")  # $0 needs no statistic label
# "your" marks figures the user gave, which aren't national statistics.
STAT_WORD = re.compile(r"\b(median|average|mean|your)\b", re.I)
# "You earn / you're making / you'd be paid", "your salary of $X", "your current role pays".
USER_AS_EARNER = re.compile(
    r"\b(you|you're|you are|you'd|you'll|you've)\s+(\w+\s+){0,3}?(earn|earns|earning|earned|make|makes|making|paid)\b"
    r"|\byour\s+(current\s+)?(salary|pay|income|wage|wages|earnings)\b[^.]{0,40}\$"
    r"|\byour\s+(current\s+)?(role|job|position)\s+pays\b",
    re.I,
)
STARTING_PAY = re.compile(r"\b(entry[- ]level|entry|starting|initial) (pay|salary|salaries|wage|wages|earnings)\b", re.I)
NEGATED_STARTING_PAY = re.compile(r"\bnot\b[^.]{0,20}\b(entry|starting|initial)", re.I)
BANNED = re.compile(r"\b(majors?|break(s|ing)?[- ]even)\b", re.I)
# Salaries, debt, and costs in the data are medians.
AVERAGE_SALARY = re.compile(
    r"\b(average|avg|mean)\b[^.]{0,40}\b(salary|salaries|earn\w*|wage|wages|pay|debt|cost|costs|price)\b"
    r"|\b(salary|salaries|earn\w*|wage|wages|pay|debt|cost|costs|price)\b[^.]{0,40}\b(average|averages|avg)\b",
    re.I,
)
PAYOFF_GUESS = re.compile(r"\b(pay(s|ing)?[- ]?off|recoup\w*)\b[^.]*?(\d|\bfew\b|\bseveral\b)", re.I)


def _text(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def _sentences(texts: list[str]) -> list[str]:
    out = []
    for t in texts:
        out += [s for s in re.split(r"(?<=[.!?])\s+", t) if s]
    return out


def prose(response: str, report_html: str) -> list[str]:
    body = re.sub(r"<svg.*?</svg>", "", report_html, flags=re.S)
    texts = [response]
    for pattern in PROSE_PATTERNS:
        texts += [_text(m) for m in re.findall(pattern, body, flags=re.S)]
    return [t for t in texts if t]


def _dollars(text: str) -> list[float]:
    return [float(m.replace(",", "")) for m in re.findall(r"\$\s?(\d[\d,]*)", text)]


def _report_figures(report_html: str) -> list[float]:
    """Dollar figures code rendered in tables and charts."""
    cells = re.findall(r"<td>(.*?)</td>", report_html, flags=re.S)
    cells += [li for ul in re.findall(r'<ul class="note">(.*?)</ul>', report_html, flags=re.S) for li in re.findall(r"<li>(.*?)</li>", ul)]
    values = re.findall(r'class="val">(.*?)<', report_html)
    return [v for t in cells + values for v in _dollars(html.unescape(t))]


def _matches(value: float, figures: list[float], tolerance: float = 0.02) -> bool:
    """True when value is one of the figures, or the gap between two, within tolerance."""
    candidates = figures + [abs(a - b) for i, a in enumerate(figures) for b in figures[i + 1:]]
    return any(abs(value - c) <= tolerance * max(c, 1) for c in candidates)


def run_checks(response: str, report_html: str, expect: dict | None = None) -> dict[str, dict]:
    """Each check -> {"pass": bool, "hits": [offending text]}."""
    sentences = _sentences(prose(response, report_html))
    captions = [_text(c) for c in re.findall(r"<figcaption>(.*?)</figcaption>", report_html, flags=re.S)]
    visible = response + _text(report_html)
    figures = _report_figures(report_html)

    def hits(pred) -> list[str]:
        return [s for s in sentences if pred(s)]

    results = {
        "report_rendered": [] if report_html else ["no report HTML"],
        "notice_at_top": [] if re.search(r"<main>\s*<p class=\"notice\">", report_html) else ["notice missing"],
        "no_user_as_earner": hits(lambda s: USER_AS_EARNER.search(s)),
        # The BLS reporting cap is a threshold, not a statistic.
        "dollar_figures_labeled": hits(lambda s: DOLLAR.search(s) and not STAT_WORD.search(s) and "cap" not in s.lower()),
        "charts_have_source": [c for c in captions if "Source:" not in c],
        "no_starting_pay": hits(lambda s: STARTING_PAY.search(s) and not NEGATED_STARTING_PAY.search(s)),
        "no_banned_words": hits(lambda s: BANNED.search(s)),
        "no_payoff_guesses": hits(lambda s: PAYOFF_GUESS.search(s)),
        "no_average_salary": hits(lambda s: AVERAGE_SALARY.search(s)),
        "prose_figures_in_report": hits(lambda s: any(not _matches(v, figures) for v in _dollars(s))),
        "no_template_leaks": [m for m in re.findall(r"\{\{[^}]*\}\}|\*\*", visible)],
    }
    if expect:
        # Per-case expectations from cases.jsonl, matched against the LLM's text.
        text = " ".join(prose(response, report_html))
        results["case_expectations"] = (
            [f"missing: {p}" for p in expect.get("must_mention", []) if not re.search(p, text, re.I)]
            + [f"should not mention: {p}" for p in expect.get("must_not_mention", []) if re.search(p, text, re.I)]
        )
    return {name: {"pass": not h, "hits": h} for name, h in results.items()}
