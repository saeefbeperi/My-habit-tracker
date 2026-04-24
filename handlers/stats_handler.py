import logging
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CallbackQueryHandler

from database import get_stats, get_user

logger = logging.getLogger(__name__)


def _emoji_bar(rate: float, width: int = 10) -> str:
    rate = max(0.0, min(1.0, rate))
    filled = round(rate * width)
    empty = width - filled
    return "█" * filled + "░" * empty


def _format_last_7_days(daily_data: list) -> str:
    if not daily_data:
        return "No data yet 🌱"

    lines = []
    for entry in daily_data:
        try:
            date_str = entry.get("date", "")
            if date_str:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                date_short = date_obj.strftime("%b %d")
            else:
                date_short = "???"

            completed = entry.get("completed", 0)
            total = entry.get("total", 0)

            if total > 0:
                rate = completed / total
            else:
                rate = 0.0

            pct = int(rate * 100)
            bar = _emoji_bar(rate)
            lines.append(f"{date_short}  {bar}  {pct}%")

        except Exception as e:
            logger.warning(f"Error formatting daily entry {entry}: {e}")
            continue

    return "\n".join(lines) if lines else "No data yet 🌱"


async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if update.callback_query:
            await update.callback_query.answer()

        user = update.effective_user

        try:
            stats = await get_stats(user.id)
        except Exception as e:
            logger.error(f"DB error in show_stats get_stats: {e}", exc_info=True)
            stats = {}

        try:
            user_record = await get_user(user.id)
        except Exception as e:
            logger.error(f"DB error in show_stats get_user: {e}", exc_info=True)
            user_record = None

        first_name = user.first_name or "friend"
        if user_record:
            first_name = user_record.get("first_name", first_name) or first_name

        current_streak = stats.get("current_streak", 0)
        best_streak = stats.get("best_streak", 0)
        total_days = stats.get("total_days_tracked", 0)
        tasks_completed = stats.get("tasks_completed", 0)
        tasks_total = stats.get("tasks_total", 0)

        if tasks_total > 0:
            avg_rate = tasks_completed / tasks_total
            avg_pct = int(avg_rate * 100)
        else:
            avg_pct = 0

        daily_data = stats.get("last_7_days", [])

        if not daily_data:
            today = datetime.utcnow().date()
            daily_data = []
            for i in range(6, -1, -1):
                day = today - timedelta(days=i)
                daily_data.append({
                    "date": day.strftime("%Y-%m-%d"),
                    "completed": 0,
                    "total": 0,
                })

        last_7_str = _format_last_7_days(daily_data)

        message = (
            "📊 *Your HabitFlow Stats*\n\n"
            f"🔥 Current Streak: *{current_streak}* days\n"
            f"🏆 Best Streak: *{best_streak}* days\n"
            f"📅 Total Days Tracked: *{total_days}*\n"
            f"✅ Tasks Completed: *{tasks_completed}* / *{tasks_total}* total\n"
            f"📈 Avg Completion Rate: *{avg_pct}%*\n\n"
            "📊 *Last 7 Days:*\n"
            f"{last_7_str}\n\n"
            f"Keep it up, {first_name}! 💪"
        )

        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🏠 Home", callback_data="menu_home")]]
        )

        if update.callback_query:
            await update.callback_query.message.reply_text(
                message,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                message,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )

    except Exception as e:
        logger.error(f"Error in show_stats: {e}", exc_info=True)
        try:
            error_msg = "Something went wrong loading your stats. Please try again."
            if update.callback_query:
                await update.callback_query.message.reply_text(error_msg)
            else:
                await update.message.reply_text(error_msg)
        except Exception:
            pass


def get_stats_handlers() -> list:
    return [
        CallbackQueryHandler(show_stats, pattern="^menu_stats$"),
    ]
