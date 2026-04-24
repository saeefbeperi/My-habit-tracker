import asyncio
import os

import google.generativeai as genai

from config import GEMINI_API_KEY


# ─────────────────────────────────────────────
# Module-level Gemini configuration
# ─────────────────────────────────────────────

genai.configure(api_key=GEMINI_API_KEY)

_MODEL_NAME = "gemini-1.5-flash"


# ─────────────────────────────────────────────
# FEATURE 2 — Fallback Messages
# ─────────────────────────────────────────────

FALLBACK_MESSAGES: dict[str, str] = {
    "zero":   "Every day is a new start, {name}! Tomorrow, small steps lead to big wins. 🌱",
    "low":    "Progress is progress, {name}! You showed up and that matters. Keep going! 💪",
    "medium": "Great effort today, {name}! You're building something real. Keep the momentum! 🔥",
    "full":   "PERFECT DAY, {name}! You crushed every single task! You're unstoppable! 🏆",
    "streak": "🔥 {streak} days strong, {name}! This is what champions look like!",
}


def _get_fallback(
    first_name: str,
    completion_rate: float,
    streak: int,
) -> str:
    if streak >= 7:
        return FALLBACK_MESSAGES["streak"].format(name=first_name, streak=streak)
    if completion_rate == 0.0:
        return FALLBACK_MESSAGES["zero"].format(name=first_name)
    if completion_rate < 0.5:
        return FALLBACK_MESSAGES["low"].format(name=first_name)
    if completion_rate < 1.0:
        return FALLBACK_MESSAGES["medium"].format(name=first_name)
    return FALLBACK_MESSAGES["full"].format(name=first_name)


def _build_prompt(first_name: str, completion_rate: float, streak: int) -> str:
    percent = int(round(completion_rate * 100))

    context_hints: list[str] = []

    if completion_rate == 0.0:
        context_hints.append("Be gentle and never shame them — zero tasks were completed.")
    elif completion_rate < 0.5:
        context_hints.append("Acknowledge their partial progress warmly.")
    elif completion_rate < 1.0:
        context_hints.append("Celebrate the solid progress and encourage them for tomorrow.")
    else:
        context_hints.append("Give a big celebration — they had a perfect day!")

    if streak >= 30:
        context_hints.append(f"They have a legendary {streak}-day streak — mention this epic milestone!")
    elif streak >= 7:
        context_hints.append(f"They have a {streak}-day streak — mention this impressive milestone!")

    context_block = " ".join(context_hints)

    prompt = (
        f"Generate a warm, personal 2-sentence motivational message for a habit tracker "
        f"app user named {first_name}. They completed {percent}% of their tasks today and have "
        f"a {streak}-day streak. Tone: encouraging, never shaming. End with an emoji. "
        f"{context_block} Keep the message under 100 words."
    )
    return prompt


def _call_gemini(prompt: str) -> str:
    model = genai.GenerativeModel(_MODEL_NAME)
    response = model.generate_content(prompt)
    return response.text.strip()


# ─────────────────────────────────────────────
# FEATURE 1 — get_motivation
# ─────────────────────────────────────────────

async def get_motivation(
    streak: int,
    completion_rate: float,
    first_name: str,
) -> str:
    print(f"[AI] Generating motivation for {first_name}...")

    prompt = _build_prompt(first_name, completion_rate, streak)

    try:
        message = await asyncio.to_thread(_call_gemini, prompt)
        return message
    except Exception as e:
        print(f"[AI] Fallback used due to error: {e}")
        return _get_fallback(first_name, completion_rate, streak)
