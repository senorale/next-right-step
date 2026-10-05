"""
Numbers a path1 user typed in free text ("tuition is $12,000 a year, I have an
offer for $95,000"), pulled into structured fields by a small model call.

The model only copies numbers into the schema; code then keeps a value only if
it appears in the user's text and falls inside sane bounds, so an invented or
mistyped number can't reach the report.
"""

import json
import logging
import re

logger = logging.getLogger(__name__)

FIELDS = {
    # field: (description for the model, min, max)
    "undergrad_tuition_per_year": ("Yearly tuition or cost for undergraduate (bachelor's) school", 0, 150_000),
    "graduate_tuition_per_year": ("Yearly tuition or cost for graduate or professional school (law, medical, master's)", 0, 150_000),
    "total_education_cost": ("Total cost for all of school, only if the user gave a total instead of a yearly amount", 0, 1_000_000),
    "expected_salary": ("Yearly salary the user expects or was offered in the occupation", 10_000, 1_000_000),
}

SCHEMA = {
    "type": "object",
    "properties": {
        **{name: {"anyOf": [{"type": "number"}, {"type": "null"}], "description": desc} for name, (desc, _, _) in FIELDS.items()},
        "unparsed": {"type": "string", "description": "Anything with a number that fits none of the fields, else empty"},
    },
    "required": [*FIELDS, "unparsed"],
    "additionalProperties": False,
}

PROMPT = (
    "Copy the numbers the user gave into the JSON fields. Use a number only if the user wrote it; "
    "never calculate, convert, or estimate. Yearly amounts go in the per-year fields. Leave a field null "
    "when the user didn't give it."
)

_NUMBER = re.compile(r"\$?\s*(\d[\d,]*(?:\.\d+)?)\s*(k|thousand)?\b", re.I)


def _numbers_in(text: str) -> set[float]:
    values = set()
    for digits, suffix in _NUMBER.findall(text):
        value = float(digits.replace(",", ""))
        values.add(value * 1000 if suffix else value)
    return values


def validate(extracted: dict, text: str) -> dict:
    """Keep values that appear in the user's text and fall within bounds."""
    seen = _numbers_in(text)
    kept = {}
    for name, (_, low, high) in FIELDS.items():
        value = extracted.get(name)
        if value is None:
            continue
        if not any(abs(value - s) <= 0.005 * max(s, 1) for s in seen):
            logger.warning("Dropping %s=%s: not in the user's text", name, value)
        elif not low <= value <= high:
            logger.warning("Dropping %s=%s: outside %s-%s", name, value, low, high)
        else:
            kept[name] = value
    return kept


async def extract_user_numbers(client, model: str, text: str) -> dict | None:
    """Structured user numbers; {} when there are none, None when the model call fails."""
    if not text.strip():
        return {}
    try:
        response = await client.chat.completions.create(
            model=model,
            max_tokens=512,
            messages=[{"role": "system", "content": PROMPT}, {"role": "user", "content": text}],
            response_format={"type": "json_schema", "json_schema": {"name": "user_numbers", "schema": SCHEMA}},
        )
        extracted = json.loads(response.choices[0].message.content or "{}")
    except Exception:
        logger.exception("Extracting user numbers failed")
        return None
    numbers = validate(extracted, text)
    logger.info("User numbers: %s (unparsed: %r)", numbers, extracted.get("unparsed"))
    return numbers
