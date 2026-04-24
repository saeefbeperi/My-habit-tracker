import logging
import re

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from database import get_user, update_user_settings
from config import ConversationState, COMMON_TIMEZONES
import scheduler as scheduler_module

logger = logging.getLogger(__name__)

SETTING_REMINDER_TIME = ConversationState.SETTING_REMINDER_TIME
SETTING_SUMMARY_TIME = ConversationState.SETTING_SUMMARY_TIME
SETTING_TIMEZONE = ConversationState.SETTING_TIMEZONE

TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _cancel_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Cancel", callback_data="settings_cancel")]]
    )


def _home_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🏠 Home", callback_data="menu_home")]]
    )


def _build_settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "⏰ Change Morning Time", callback_data="set_reminder"
                ),
                InlineKeyboardButton(
                    "🌙 Change Evening Time", callback_data="set_summary"
                ),
            ],
            [
                InlineKeyboardButton(
                    "🌍 Change Timezone", callback_data="set_timezone"
                ),
            ],
            [
                InlineKeyboardButton("🏠 Home", callback_data="menu_home"),
            ],
        ]
    )


def _build_timezone_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for code, tz_value in COMMON_TIMEZONES.items():
        row.append(
            InlineKeyboardButton(
                f"{code} ({tz_value})", callback_data=f"tz_{code}"
            )
        )
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append(
        [InlineKeyboardButton("❌ Cancel", callback_data="settings_cancel")]
    )
    return InlineKeyboardMarkup(buttons)


async def _get_user_safe(user_id: int) -> dict:
    try:
        user_record = await get_user(user_id)
        return user_record or {}
    except Exception as e:
        logger.error(f"DB error in get_user({user_id}): {e}", exc_info=True)
        return {}


async def _do_reschedule(app, user_id: int, user_record: dict) -> None:
    try:
        reminder_time = user_record.get("reminder_time", "08:00") or "08:00"
        summary_time = user_record.get("summary_time", "21:00") or "21:00"
        timezone = user_record.get("timezone", "UTC") or "UTC"
        await scheduler_module.reschedule_user(
            app, user_id, reminder_time, summary_time, timezone
        )
    except Exception as e:
        logger.error(f"Error rescheduling user {user_id}: {e}", exc_info=True)


async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if update.callback_query:
            await update.callback_query.answer()

        user = update.effective_user
        user_record = await _get_user_safe(user.id)

        reminder_time = user_record.get("reminder_time", "08:00") or "08:00"
        summary_time = user_record.get("summary_time", "21:00") or "21:00"
        timezone = user_record.get("timezone", "UTC") or "UTC"

        text = (
            "⚙️ *Settings*\n\n"
            f"⏰ Morning Reminder: *{reminder_time}* ({timezone})\n"
            f"🌙 Evening Summary: *{summary_time}* ({timezone})\n"
            f"🌍 Timezone: *{timezone}*"
        )

        keyboard = _build_settings_keyboard()

        if update.callback_query:
            await update.callback_query.message.reply_text(
                text, reply_markup=keyboard, parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                text, reply_markup=keyboard, parse_mode="Markdown"
            )

    except Exception as e:
        logger.error(f"Error in show_settings: {e}", exc_info=True)
        try:
            msg = "Something went wrong loading settings. Please try again."
            if update.callback_query:
                await update.callback_query.message.reply_text(msg)
            else:
                await update.message.reply_text(msg)
        except Exception:
            pass


async def set_reminder_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    try:
        await update.callback_query.answer()
        text = (
            "⏰ Send me your preferred morning reminder time.\n\n"
            "Format: HH:MM (24-hour) — e.g., 08:00, 07:30"
        )
        await update.callback_query.message.reply_text(
            text, reply_markup=_cancel_button()
        )
        return SETTING_REMINDER_TIME
    except Exception as e:
        logger.error(f"Error in set_reminder_callback: {e}", exc_info=True)
        return ConversationHandler.END


async def receive_reminder_time(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    try:
        text = update.message.text.strip()

        if not TIME_PATTERN.match(text):
            await update.message.reply_text(
                "❌ Invalid format. Please use HH:MM (24-hour), e.g., 08:00 or 21:30",
                reply_markup=_cancel_button(),
            )
            return SETTING_REMINDER_TIME

        user = update.effective_user

        try:
            await update_user_settings(user.id, "reminder_time", text)
        except Exception as e:
            logger.error(
                f"DB error updating reminder_time for {user.id}: {e}", exc_info=True
            )
            await update.message.reply_text(
                "❌ Failed to save. Please try again.", reply_markup=_cancel_button()
            )
            return SETTING_REMINDER_TIME

        user_record = await _get_user_safe(user.id)
        user_record["reminder_time"] = text
        await _do_reschedule(context.application, user.id, user_record)

        await update.message.reply_text(
            f"✅ Morning reminder set to *{text}*!",
            parse_mode="Markdown",
            reply_markup=_home_button(),
        )
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error in receive_reminder_time: {e}", exc_info=True)
        try:
            await update.message.reply_text(
                "Something went wrong. Please try again.", reply_markup=_cancel_button()
            )
        except Exception:
            pass
        return SETTING_REMINDER_TIME


async def set_summary_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    try:
        await update.callback_query.answer()
        text = (
            "🌙 Send me your preferred evening summary time.\n\n"
            "Format: HH:MM (24-hour) — e.g., 21:00, 20:30"
        )
        await update.callback_query.message.reply_text(
            text, reply_markup=_cancel_button()
        )
        return SETTING_SUMMARY_TIME
    except Exception as e:
        logger.error(f"Error in set_summary_callback: {e}", exc_info=True)
        return ConversationHandler.END


async def receive_summary_time(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    try:
        text = update.message.text.strip()

        if not TIME_PATTERN.match(text):
            await update.message.reply_text(
                "❌ Invalid format. Please use HH:MM (24-hour), e.g., 21:00 or 20:30",
                reply_markup=_cancel_button(),
            )
            return SETTING_SUMMARY_TIME

        user = update.effective_user

        try:
            await update_user_settings(user.id, "summary_time", text)
        except Exception as e:
            logger.error(
                f"DB error updating summary_time for {user.id}: {e}", exc_info=True
            )
            await update.message.reply_text(
                "❌ Failed to save. Please try again.", reply_markup=_cancel_button()
            )
            return SETTING_SUMMARY_TIME

        user_record = await _get_user_safe(user.id)
        user_record["summary_time"] = text
        await _do_reschedule(context.application, user.id, user_record)

        await update.message.reply_text(
            f"✅ Evening summary set to *{text}*!",
            parse_mode="Markdown",
            reply_markup=_home_button(),
        )
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error in receive_summary_time: {e}", exc_info=True)
        try:
            await update.message.reply_text(
                "Something went wrong. Please try again.", reply_markup=_cancel_button()
            )
        except Exception:
            pass
        return SETTING_SUMMARY_TIME


async def set_timezone_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    try:
        await update.callback_query.answer()
        text = "🌍 Select your timezone:"
        await update.callback_query.message.reply_text(
            text, reply_markup=_build_timezone_keyboard()
        )
        return SETTING_TIMEZONE
    except Exception as e:
        logger.error(f"Error in set_timezone_callback: {e}", exc_info=True)
        return ConversationHandler.END


async def receive_timezone(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    try:
        await update.callback_query.answer()
        data = update.callback_query.data

        if not data.startswith("tz_"):
            return SETTING_TIMEZONE

        code = data[3:]
        tz_value = COMMON_TIMEZONES.get(code)

        if not tz_value:
            await update.callback_query.message.reply_text(
                "❌ Unknown timezone. Please select from the list.",
                reply_markup=_build_timezone_keyboard(),
            )
            return SETTING_TIMEZONE

        user = update.effective_user

        try:
            await update_user_settings(user.id, "timezone", tz_value)
        except Exception as e:
            logger.error(
                f"DB error updating timezone for {user.id}: {e}", exc_info=True
            )
            await update.callback_query.message.reply_text(
                "❌ Failed to save timezone. Please try again.",
                reply_markup=_build_timezone_keyboard(),
            )
            return SETTING_TIMEZONE

        user_record = await _get_user_safe(user.id)
        user_record["timezone"] = tz_value
        await _do_reschedule(context.application, user.id, user_record)

        await update.callback_query.message.reply_text(
            f"✅ Timezone updated to *{tz_value}*!",
            parse_mode="Markdown",
            reply_markup=_home_button(),
        )
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error in receive_timezone: {e}", exc_info=True)
        try:
            await update.callback_query.message.reply_text(
                "Something went wrong. Please try again.",
                reply_markup=_build_timezone_keyboard(),
            )
        except Exception:
            pass
        return SETTING_TIMEZONE


async def settings_cancel(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    try:
        await update.callback_query.answer()
        await show_settings(update, context)
    except Exception as e:
        logger.error(f"Error in settings_cancel: {e}", exc_info=True)
    return ConversationHandler.END


async def cancel_via_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    try:
        from handlers.start_handler import show_main_menu
        await show_main_menu(update, context)
    except Exception as e:
        logger.error(f"Error in cancel_via_command: {e}", exc_info=True)
    return ConversationHandler.END


def get_settings_handlers() -> list:
    conversation_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(show_settings, pattern="^menu_settings$"),
        ],
        states={
            SETTING_REMINDER_TIME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, receive_reminder_time
                ),
                CallbackQueryHandler(settings_cancel, pattern="^settings_cancel$"),
            ],
            SETTING_SUMMARY_TIME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, receive_summary_time
                ),
                CallbackQueryHandler(settings_cancel, pattern="^settings_cancel$"),
            ],
            SETTING_TIMEZONE: [
                CallbackQueryHandler(receive_timezone, pattern="^tz_"),
                CallbackQueryHandler(settings_cancel, pattern="^settings_cancel$"),
            ],
        },
        fallbacks=[
            CommandHandler("menu", cancel_via_command),
            CallbackQueryHandler(settings_cancel, pattern="^settings_cancel$"),
        ],
        per_message=False,
    )

    loose_handlers = [
        CallbackQueryHandler(set_reminder_callback, pattern="^set_reminder$"),
        CallbackQueryHandler(set_summary_callback, pattern="^set_summary$"),
        CallbackQueryHandler(set_timezone_callback, pattern="^set_timezone$"),
    ]

    return [conversation_handler] + loose_handlers
