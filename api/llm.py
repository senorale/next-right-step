"""
Shared model client, Gemini through its OpenAI-compatible endpoint.

Which key is used depends on where the app runs:
- production: the paid GEMINI_API_KEY. Production means APP_ENV=production
  (set on the Railway service) inside an actual Railway deployment
  (RAILWAY_DEPLOYMENT_ID). `railway run` on a laptop gets the project's
  variables but no deployment id, so it stays development.
- anywhere else (local development): the free-tier GEMINI_FREE_TIER_API_KEY,
  so local testing never spends paid credits. Free-tier prompts may be used by
  Google, so local testing uses made-up input only.

Production has no free key set, so it can never fall back to the free tier:
if detection failed there, model calls would fail loudly instead.

Development always uses the free key and Google's endpoint; nothing overrides
that. In production, LLM_BASE_URL / LLM_API_KEY can point at another
OpenAI-compatible provider. LLM_MODEL picks the model in both.
"""

import logging
import os

import openai
from dotenv import load_dotenv

load_dotenv(dotenv_path="../.env")
logger = logging.getLogger(__name__)

IS_PRODUCTION = os.environ.get("APP_ENV") == "production" and bool(os.environ.get("RAILWAY_DEPLOYMENT_ID"))
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

if IS_PRODUCTION:
    KEY_VAR = "LLM_API_KEY" if os.environ.get("LLM_API_KEY") else "GEMINI_API_KEY"
    BASE_URL = os.environ.get("LLM_BASE_URL", GEMINI_URL)
else:
    KEY_VAR, BASE_URL = "GEMINI_FREE_TIER_API_KEY", GEMINI_URL

client = openai.AsyncOpenAI(
    base_url=BASE_URL,
    # Placeholder keeps the server starting without a key; model calls then fail with an auth error.
    api_key=os.environ.get(KEY_VAR) or "unset",
)
MODEL = os.environ.get("LLM_MODEL", "gemini-3.5-flash-lite")
REPORT_MODEL = os.environ.get("LLM_REPORT_MODEL", MODEL)

logger.warning("Model client: %s, key from %s", "production" if IS_PRODUCTION else "development", KEY_VAR)
