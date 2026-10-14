"""
Email alerts, through Resend, for failures a user would otherwise never
report: a data source that is down or returns nothing the report needs.

Off unless both RESEND_API_KEY and ALERT_EMAIL_TO are set, so evals and local
runs stay quiet by default. Every alert is logged either way.
"""

import json
import logging
import os
import threading

import requests

from llm import IS_PRODUCTION

logger = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"
ALERT_FROM = "Next Right Step Alerts <onboarding@resend.dev>"
# Same rule llm.py uses to pick the paid key.
ENVIRONMENT = "production" if IS_PRODUCTION else "development"


def send_alert(subject: str, details: dict) -> None:
    """Log the alert and email it in the background. Never raises: a failed
    send must not break the request that hit the failure."""
    body = json.dumps({"environment": ENVIRONMENT, **details}, indent=2, default=str)
    logger.error("ALERT [%s] %s\n%s", ENVIRONMENT, subject, body)
    key, to = os.environ.get("RESEND_API_KEY"), os.environ.get("ALERT_EMAIL_TO")
    if not key or not to:
        return
    threading.Thread(target=_send, args=(key, to, subject, body), daemon=True).start()


def _send(key: str, to: str, subject: str, body: str) -> None:
    try:
        resp = requests.post(
            RESEND_URL,
            headers={"Authorization": f"Bearer {key}"},
            json={"from": ALERT_FROM, "to": [to], "subject": f"[Next Right Step][{ENVIRONMENT}] {subject}", "text": body},
            timeout=10,
        )
        if resp.status_code >= 300:
            logger.error("Resend returned %d for alert %r: %s", resp.status_code, subject, resp.text[:300])
    except requests.RequestException:
        logger.exception("Alert email failed: %r", subject)
