import logging
import re
from datetime import datetime, timedelta

import pytz
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from database import get_or_create_user, add_task, get_tasks_for_date, complete_task, get_streak
from config import MAX_TASKS_PER_DAY

try:
    from config import ConversationState
    ADDING_TASK = ConversationState.ADDING_TASK
except Exception:
    ADDING_TASK = 1

logger = logging.getLogger(__name__)

TIME_SLOT_EMOJIS = {
    "Morning": "🌅",
    "Afternoon": "☀️",
    "Evening": "🌆",
    "Anytime": "⭐",
}

TIME_SLOT_PREFIXES = ["Morning:", "Afternoon:", "Evening:", "Anytime:"]


def _get_user_timezone(user_record: dict) -> pytz.BaseTzInfo:
    tz_str = user_record.get("timezone", "UTC") if user_record else "UTC"
    try:
        return pytz.timezone(tz_str)
    except Exception:
        return pytz.UTC


def _get_tomorrow_str(tz: pytz.BaseTzInfo) -> str:
    now = datetime.now(tz)
    tomorrow = now + timedelta(days=1)
    return tomorrow.strftime("%Y-%m-%d")


def _get_today_str(tz: pytz.BaseTzInfo) -> str:
    return datetime.now(tz).strftime("%Y-%m-%d")


def _build_task_keyboard(tasks: list) -> InlineKeyboardMarkup:
    buttons = []
    for task in tasks:
        task_id = task.get("id") or task.get("task_id")
        task_name = task.get("task_name", "Task")
        is_done = task.get("completed", False) or task.get("is_completed", False)
        if is_done:
            label = f"✅ {task_name}"
            cb = f"done_{task_id}"
        else:
            label = f"⬜ {task_name}"
            cb = f"complete_{task_id}"
        buttons.append([InlineKeyboardButton(label, callback_data=cb)])
    return InlineKeyboardMarkup(buttons)


def _build_today_message(tasks: list, streak_data: dict) -> str:
    total = len(tasks)
    done = sum(
        1 for t in tasks if t.get("completed", False) or t.get("is_completed", False)
    )
    pct = int((done / total) * 100) if total > 0 else 0
    streak = streak_data.get("current_streak", 0) if streak_data else 0

    lines = ["📋 *Today's Tasks*\n"]
    for task in tasks:
        is_done = task.get("completed", False) or task.get("is_completed", False)
        task_name = task.get("task_name", "Task")
        slot = task.get("time_slot", "Anytime")
        emoji = TIME_SLOT_EMOJIS.get(slot, "⭐")
        status = "✅" if is_done else "⬜"
        lines.append(f"{status} {emoji} {task_name}")

    lines.append(f"\nProgress: {done}/{total} ({pct}%) | 🔥 Streak: {streak} days")
    return "\n".join(lines)


async def start_planning(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        user = update.effective_user
        try:
            user_record = await get_or_create_user(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
            )
        except Exception as e:
            logger.error(f"DB error in start_planning get_or_create_user: {e}", exc_info=True)
            user_record = {}

        tz = _get_user_timezone(user_record)
        tomorrow_str = _get_tomorrow_str(tz)

        try:
            existing_tasks = await get_tasks_for_date(user.id, tomorrow_str)
        except Exception as e:
            logger.error(f"DB error in start_planning get_tasks_for_date: {e}", exc_info=True)
            existing_tasks = []

        if len(existing_tasks) >= MAX_TASKS_PER_DAY:
            msg = "You've already planned 10 tasks for tomorrow! ✅"
            if update.callback_query:
                await update.callback_query.answer()
                await update.callback_query.message.reply_text(msg)
            else:
                await update.message.reply_text(msg)
            return ConversationHandler.END

        context.user_data["planning_date"] = tomorrow_str
        context.user_data["tasks_added"] = len(existing_tasks)

        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("✅ Done Planning", callback_data="plan_done")]]
        )

        tomorrow_display = datetime.strptime(tomorrow_str, "%Y-%m-%d").strftime("%B %d, %Y")
        text = (
            f"✏️ Planning tasks for tomorrow ({tomorrow_display})!\n\n"
            "Send me your first task (e.g., 'Morning run 🏃')\n\n"
            "Or type a time prefix before your task:\n"
            "[Morning] [Afternoon] [Evening] [Anytime]\n\n"
            "Tap [✅ Done Planning] when finished."
        )

        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(text, reply_markup=keyboard)
        else:
            await update.message.reply_text(text, reply_markup=keyboard)

        return ADDING_TASK

    except Exception as e:
        logger.error(f"Error in start_planning: {e}", exc_info=True)
        try:
            if update.callback_query:
                await update.callback_query.answer()
                await update.callback_query.message.reply_text(
                    "Something went wrong. Please try again."
                )
            else:
                await update.message.reply_text("Something went wrong. Please try again.")
        except Exception:
            pass
        return ConversationHandler.END


async def receive_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        text = update.message.text.strip()

        if not text:
            await update.message.reply_text(
                "Please send a task name. What do you want to accomplish tomorrow?"
            )
            return ADDING_TASK

        time_slot = "Anytime"
        task_name = text

        for prefix in TIME_SLOT_PREFIXES:
            if text.startswith(prefix):
                time_slot = prefix.rstrip(":")
                task_name = text[len(prefix):].strip()
                break

        if not task_name:
            await update.message.reply_text(
                "Task name can't be empty. Please send a task after the time prefix."
            )
            return ADDING_TASK

        user = update.effective_user
        planning_date = context.user_data.get("planning_date")

        if not planning_date:
            try:
                user_record = await get_or_create_user(
                    user_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                )
            except Exception:
                user_record = {}
            tz = _get_user_timezone(user_record)
            planning_date = _get_tomorrow_str(tz)
            context.user_data["planning_date"] = planning_date

        try:
            await add_task(user.id, task_name, planning_date, time_slot)
        except Exception as e:
            logger.error(f"DB error in receive_task add_task: {e}", exc_info=True)
            await update.message.reply_text(
                "Failed to save your task. Please try again."
            )
            return ADDING_TASK

        context.user_data["tasks_added"] = context.user_data.get("tasks_added", 0) + 1
        count = context.user_data["tasks_added"]

        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("✅ Done Planning", callback_data="plan_done")]]
        )

        if count >= MAX_TASKS_PER_DAY:
            await update.message.reply_text(
                f"✅ Task {count} added: {task_name}\n\n"
                f"You've reached the maximum of {MAX_TASKS_PER_DAY} tasks for tomorrow!"
            )
            return await _finish_planning(update, context, planning_date, user.id)

        await update.message.reply_text(
            f"✅ Task {count} added: {task_name}\n\n"
            "Keep adding tasks or tap [✅ Done Planning]",
            reply_markup=keyboard,
        )

        return ADDING_TASK

    except Exception as e:
        logger.error(f"Error in receive_task: {e}", exc_info=True)
        try:
            await update.message.reply_text("Something went wrong. Please try again.")
        except Exception:
            pass
        return ADDING_TASK


async def _finish_planning(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    planning_date: str,
    user_id: int,
) -> int:
    try:
        try:
            tasks = await get_tasks_for_date(user_id, planning_date)
        except Exception as e:
            logger.error(f"DB error in _finish_planning: {e}", exc_info=True)
            tasks = []

        n = len(tasks)
        lines = [f"✅ Great! You've planned {n} task{'s' if n != 1 else ''} for tomorrow!\n"]

        for task in tasks:
            slot = task.get("time_slot", "Anytime")
            emoji = TIME_SLOT_EMOJIS.get(slot, "⭐")
            task_name = task.get("task_name", "Task")
            lines.append(f"{emoji} {task_name}")

        lines.append("\nSweet dreams! I'll remind you in the morning ☀️")
        summary = "\n".join(lines)

        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🏠 Home", callback_data="menu_home")]]
        )

        if update.callback_query:
            await update.callback_query.message.reply_text(summary, reply_markup=keyboard)
        else:
            await update.message.reply_text(summary, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error in _finish_planning: {e}", exc_info=True)

    context.user_data.pop("planning_date", None)
    context.user_data.pop("tasks_added", None)

    return ConversationHandler.END


async def plan_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        await update.callback_query.answer()
        user = update.effective_user
        planning_date = context.user_data.get("planning_date")

        if not planning_date:
            try:
                user_record = await get_or_create_user(
                    user_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                )
            except Exception:
                user_record = {}
            tz = _get_user_timezone(user_record)
            planning_date = _get_tomorrow_str(tz)

        return await _finish_planning(update, context, planning_date, user.id)

    except Exception as e:
        logger.error(f"Error in plan_done: {e}", exc_info=True)
        try:
            await update.callback_query.message.reply_text(
                "Something went wrong. Please try again."
            )
        except Exception:
            pass
        return ConversationHandler.END


async def show_today_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user = update.effective_user

        try:
            user_record = await get_or_create_user(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
            )
        except Exception as e:
            logger.error(f"DB error in show_today_tasks get_or_create_user: {e}", exc_info=True)
            user_record = {}

        tz = _get_user_timezone(user_record)
        today_str = _get_today_str(tz)

        try:
            tasks = await get_tasks_for_date(user.id, today_str)
        except Exception as e:
            logger.error(f"DB error in show_today_tasks get_tasks_for_date: {e}", exc_info=True)
            tasks = []

        try:
            streak_data = await get_streak(user.id)
        except Exception as e:
            logger.error(f"DB error in show_today_tasks get_streak: {e}", exc_info=True)
            streak_data = {}

        if not tasks:
            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("✏️ Plan Tomorrow", callback_data="menu_plan"),
                        InlineKeyboardButton("🏠 Home", callback_data="menu_home"),
                    ]
                ]
            )
            no_task_msg = (
                "📋 No tasks planned for today!\n\nTap below to plan quickly 👇"
            )
            if update.callback_query:
                await update.callback_query.message.reply_text(
                    no_task_msg, reply_markup=keyboard
                )
            else:
                await update.message.reply_text(no_task_msg, reply_markup=keyboard)
            return

        message_text = _build_today_message(tasks, streak_data)
        keyboard = _build_task_keyboard(tasks)

        if update.callback_query:
            await update.callback_query.message.reply_text(
                message_text,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                message_text,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )

    except Exception as e:
        logger.error(f"Error in show_today_tasks: {e}", exc_info=True)
        try:
            if update.callback_query:
                await update.callback_query.message.reply_text(
                    "Something went wrong loading your tasks. Please try again."
                )
            else:
                await update.message.reply_text(
                    "Something went wrong loading your tasks. Please try again."
                )
        except Exception:
            pass


async def show_today_tasks_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await update.callback_query.answer()
        await show_today_tasks(update, context)
    except Exception as e:
        logger.error(f"Error in show_today_tasks_callback: {e}", exc_info=True)


async def handle_task_complete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        query = update.callback_query
        await query.answer()

        data = query.data
        match = re.match(r"^complete_(\d+)$", data)
        if not match:
            return

        task_id = int(match.group(1))
        user = update.effective_user

        try:
            success = await complete_task(task_id, user.id)
        except Exception as e:
            logger.error(f"DB error in handle_task_complete complete_task: {e}", exc_info=True)
            await query.answer("Failed to complete task. Please try again.")
            return

        if not success:
            await query.answer("Already done! ✅")
            return

        await query.answer("✅ Done! Great job!")

        try:
            user_record = await get_or_create_user(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
            )
        except Exception:
            user_record = {}

        tz = _get_user_timezone(user_record)
        today_str = _get_today_str(tz)

        try:
            tasks = await get_tasks_for_date(user.id, today_str)
        except Exception as e:
            logger.error(f"DB error in handle_task_complete get_tasks_for_date: {e}", exc_info=True)
            tasks = []

        try:
            streak_data = await get_streak(user.id)
        except Exception as e:
            logger.error(f"DB error in handle_task_complete get_streak: {e}", exc_info=True)
            streak_data = {}

        message_text = _build_today_message(tasks, streak_data)
        keyboard = _build_task_keyboard(tasks)

        try:
            await query.edit_message_text(
                message_text,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.warning(f"Could not edit message in handle_task_complete: {e}")

        all_done = all(
            t.get("completed", False) or t.get("is_completed", False) for t in tasks
        )
        if all_done and tasks:
            try:
                await query.message.reply_text(
                    "🎉 PERFECT DAY! You completed ALL your tasks!\n\n"
                    "You're absolutely crushing it today! "
                    "Keep this streak alive tomorrow! 🔥"
                )
            except Exception as e:
                logger.error(f"Error sending perfect day message: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"Error in handle_task_complete: {e}", exc_info=True)
        try:
            await update.callback_query.answer("Something went wrong. Please try again.")
        except Exception:
            pass


async def cancel_planning(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data.pop("planning_date", None)
        context.user_data.pop("tasks_added", None)

        from handlers.start_handler import show_main_menu
        await show_main_menu(update, context)
    except Exception as e:
        logger.error(f"Error in cancel_planning: {e}", exc_info=True)

    return ConversationHandler.END


def get_task_handlers() -> list:
    conversation_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_planning, pattern="^menu_plan$"),
        ],
        states={
            ADDING_TASK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_task),
                CallbackQueryHandler(plan_done, pattern="^plan_done$"),
            ],
        },
        fallbacks=[
            CommandHandler("menu", cancel_planning),
        ],
        per_message=False,
    )

    return [
        conversation_handler,
        CallbackQueryHandler(handle_task_complete, pattern=r"^complete_\d+$"),
        CallbackQueryHandler(show_today_tasks_callback, pattern="^menu_today$"),
    ]
