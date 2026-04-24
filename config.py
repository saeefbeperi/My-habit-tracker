import os
from enum import IntEnum


# ─────────────────────────────────────────────
# Environment Variables
# ─────────────────────────────────────────────

BOT_TOKEN: str = os.environ.get("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise ValueError(
        "Missing required environment variable: BOT_TOKEN\n"
        "Please set BOT_TOKEN in your Render.com environment variables "
        "(Dashboard → Your Service → Environment → Add Environment Variable)."
    )

GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    raise ValueError(
        "Missing required environment variable: GEMINI_API_KEY\n"
        "Please set GEMINI_API_KEY in your Render.com environment variables."
    )

_admin_id_raw: str = os.environ.get("ADMIN_ID", "")
if not _admin_id_raw:
    raise ValueError(
        "Missing required environment variable: ADMIN_ID\n"
        "Please set ADMIN_ID (your Telegram user ID) in your Render.com environment variables."
    )
try:
    ADMIN_ID: int = int(_admin_id_raw)
except ValueError:
    raise ValueError(
        f"Environment variable ADMIN_ID must be an integer (your Telegram user ID), got: {_admin_id_raw!r}"
    )

RENDER_EXTERNAL_URL: str = os.environ.get("RENDER_EXTERNAL_URL", "")
if not RENDER_EXTERNAL_URL:
    raise ValueError(
        "Missing required environment variable: RENDER_EXTERNAL_URL\n"
        "Please set RENDER_EXTERNAL_URL to your Render.com service URL "
        "(e.g. https://habitflow-bot.onrender.com)."
    )

_port_raw: str = os.environ.get("PORT", "8000")
try:
    PORT: int = int(_port_raw)
except ValueError:
    raise ValueError(
        f"Environment variable PORT must be an integer, got: {_port_raw!r}"
    )


# ─────────────────────────────────────────────
# Database Constants
# ─────────────────────────────────────────────

DB_PATH: str = "habitflow.db"
MAX_TASKS_PER_DAY: int = 10
STREAK_THRESHOLD: float = 0.70  # 70% daily completion required to extend streak


# ─────────────────────────────────────────────
# Conversation States
# ─────────────────────────────────────────────

class ConversationState(IntEnum):
    ADDING_TASK = 1
    SETTING_REMINDER_TIME = 2
    SETTING_SUMMARY_TIME = 3
    SETTING_TIMEZONE = 4
    ADMIN_BROADCAST = 5


# ─────────────────────────────────────────────
# Bot Personality Constants
# ─────────────────────────────────────────────

BOT_NAME: str = "HabitFlow 🌊"
DEFAULT_REMINDER_TIME: str = "08:00"
DEFAULT_SUMMARY_TIME: str = "21:00"
DEFAULT_TIMEZONE: str = "Asia/Dhaka"


# ─────────────────────────────────────────────
# Common Timezone List
# ─────────────────────────────────────────────

COMMON_TIMEZONES: dict[str, str] = {
    "BD": "Asia/Dhaka",
    "IN": "Asia/Kolkata",
    "UK": "Europe/London",
    "US_ET": "America/New_York",
    "US_PT": "America/Los_Angeles",
    "UAE": "Asia/Dubai",
    "SG": "Asia/Singapore",
}
