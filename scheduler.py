import asyncio
from datetime import datetime

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden

import database
import ai_module
from config import DEFAULT_REMINDER_TIME, DEFAULT_SUMMARY_TIME, DEFAULT_TIMEZONE


# ─────────────────────────────────────────────
# Module-level scheduler instance
# ─────────────────────────────────────────────

_scheduler: AsyncIOScheduler | None = None


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _parse_time(time_str: str) -> tuple[int, int]:
    """Parse 'HH:MM' string into (hour, minute) integers."""
    try:
        parts = time_str.strip().split(":")
        return int(parts[0]), int(parts[1])
    except Exception:
        default_parts = DEFAULT_REMINDER_TIME.split(":")
        return int(default_parts[0]), int(default_parts[1])


def _get_pytz(timezone_str: str):
    try:
        return pytz.timezone(timezone_str)
    except Exception:
        return pytz.timezone(DEFAULT_TIMEZONE)


def _today_in_tz(tz) -> str:
    return datetime.now(tz).strftime("%Y-%m-%d")


def _format_date_display(date_str: str) -> str:
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%B %d, %Y")
    except Exception:
        return date_str


def _build_task_list(tasks: list[dict]) -> str:
    lines: list[str] = []
    for t in tasks:
        slot = t.get("time_slot", "Anytime")
        name = t.get("task_name", "")
        status = t.get("status", "pending")
        icon = "✅" if status == "completed" else "⬜"
        lines.append(f"  {icon} [{slot}] {name}")
    return "\n".join(lines)


def _add_jobs_for_user(app, user: dict) -> None:
    global _scheduler
    if _scheduler is None:
        return

    user_id: int = user["user_id"]
    reminder_time: str = user.get("reminder_time") or DEFAULT_REMINDER_TIME
    summary_time: str = user.get("summary_time") or DEFAULT_SUMMARY_TIME
    timezone_str: str = user.get("timezone") or DEFAULT_TIMEZONE
    tz = _get_pytz(timezone_str)

    r_hour, r_minute = _parse_time(reminder_time)
    s_hour, s_minute = _parse_time(summary_time)

    _scheduler.add_job(
        send_morning_reminder,
        trigger=CronTrigger(hour=r_hour, minute=r_minute, timezone=tz),
        args=[app, user_id],
        id=f"morning_{user_id}",
        replace_existing=True,
        misfire_grace_time=300,
    )

    _scheduler.add_job(
        send_evening_summary,
        trigger=CronTrigger(hour=s_hour, minute=s_minute, timezone=tz),
        args=[app, user_id],
        id=f"evening_{user_id}",
        replace_existing=True,
        misfire_grace_time=300,
    )


# ─────────────────────────────────────────────
# FEATURE 1 — setup_scheduler
# ─────────────────────────────────────────────

def setup_scheduler(app) -> None:
    global _scheduler

    _scheduler = AsyncIOScheduler()

    users: list[dict] = asyncio.get_event_loop().run_until_complete(
        database.get_all_users()
    )

    for user in users:
        _add_jobs_for_user(app, user)

    _scheduler.start()
    print(f"[SCHED] Scheduler started with {len(users)} user jobs")


# ─────────────────────────────────────────────
# FEATURE 2 — reschedule_user
# ─────────────────────────────────────────────

async def reschedule_user(
    app,
    user_id: int,
    reminder_time: str,
    summary_time: str,
    timezone: str,
) -> None:
    global _scheduler
    if _scheduler is None:
        print(f"[SCHED ERROR] reschedule_user({user_id}): scheduler not initialized")
        return

    for job_id in (f"morning_{user_id}", f"evening_{user_id}"):
        try:
            _scheduler.remove_job(job_id)
        except Exception:
            pass  # Job may not exist yet — that's fine

    fake_user = {
        "user_id": user_id,
        "reminder_time": reminder_time,
        "summary_time": summary_time,
        "timezone": timezone,
    }
    _add_jobs_for_user(app, fake_user)

    print(
        f"[SCHED] Rescheduled user {user_id}: "
        f"morning={reminder_time}, evening={summary_time}"
    )


# ─────────────────────────────────────────────
# FEATURE 3 — Morning Reminder Job
# ─────────────────────────────────────────────

async def send_morning_reminder(app, user_id: int) -> None:
    try:
        user = await database.get_user(user_id)
        if user is None:
            print(f"[SCHED ERROR] send_morning_reminder: user {user_id} not found")
            return

        timezone_str: str = user.get("timezone") or DEFAULT_TIMEZONE
        tz = _get_pytz(timezone_str)
        date_str = _today_in_tz(tz)
        first_name: str = user.get("first_name", "Friend")

        tasks = await database.get_tasks_for_date(user_id, date_str)

        if not tasks:
            text = (
                f"☀️ Good Morning {first_name}! You have no tasks planned today.\n"
                f"Tap /menu to add some quick tasks! 💪"
            )
            await app.bot.send_message(chat_id=user_id, text=text)
            print(f"[SCHED] Morning reminder (no tasks) sent to user {user_id}")
            return

        task_lines = _build_task_list(tasks)
        total = len(tasks)
        text = (
            f"☀️ Good Morning, {first_name}! Ready to make today count?\n\n"
            f"📋 Your tasks for today ({total} planned):\n"
            f"{task_lines}\n\n"
            f"Let's crush it, one task at a time! 💪"
        )

        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("📋 View & Complete Tasks", callback_data="view_tasks")]]
        )

        await app.bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=keyboard,
        )
        print(f"[SCHED] Morning reminder sent to user {user_id} ({total} tasks)")

    except Forbidden:
        print(f"[SCHED] Morning reminder skipped — user {user_id} blocked the bot")
    except Exception as e:
        print(f"[SCHED ERROR] send_morning_reminder user {user_id}: {e}")


# ─────────────────────────────────────────────
# FEATURE 4 — Evening Summary Job
# ─────────────────────────────────────────────

async def send_evening_summary(app, user_id: int) -> None:
    try:
        user = await database.get_user(user_id)
        if user is None:
            print(f"[SCHED ERROR] send_evening_summary: user {user_id} not found")
            return

        timezone_str: str = user.get("timezone") or DEFAULT_TIMEZONE
        tz = _get_pytz(timezone_str)
        date_str = _today_in_tz(tz)
        first_name: str = user.get("first_name", "Friend")

        tasks = await database.get_tasks_for_date(user_id, date_str)

        total = len(tasks)
        completed = sum(1 for t in tasks if t.get("status") == "completed")
        completion_rate = completed / total if total > 0 else 0.0
        percent = int(round(completion_rate * 100))

        await database.save_daily_summary(user_id, date_str, total, completed)

        streak_data = await database.update_streak(user_id, date_str, completion_rate)
        current_streak: int = streak_data.get("current_streak", 0)
        longest_streak: int = streak_data.get("longest_streak", 0)

        motivation = await ai_module.get_motivation(current_streak, completion_rate, first_name)

        display_date = _format_date_display(date_str)

        text = (
            f"🌙 Evening Summary — {display_date}\n\n"
            f"✅ Completed: {completed}/{total} tasks ({percent}%)\n"
            f"🔥 Streak: {current_streak} days | 🏆 Best: {longest_streak} days\n\n"
            f"{motivation}\n\n"
            f"Plan tomorrow? Tap /menu 📅"
        )

        await app.bot.send_message(chat_id=user_id, text=text)
        print(
            f"[SCHED] Evening summary sent to user {user_id} "
            f"({completed}/{total} tasks, streak={current_streak})"
        )

    except Forbidden:
        print(f"[SCHED] Evening summary skipped — user {user_id} blocked the bot")
    except Exception as e:
        print(f"[SCHED ERROR] send_evening_summary user {user_id}: {e}")
