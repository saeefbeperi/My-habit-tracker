import logging

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from database import get_or_create_user
from config import BOT_NAME

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user = update.effective_user
        await get_or_create_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
        )

        welcome_text = (
            f"👋 Welcome to HabitFlow 🌊, {user.first_name}!\n\n"
            "I'm your personal daily habit tracker. Here's what I do:\n"
            "📅 Help you plan tomorrow's tasks every night\n"
            "☀️ Send you a morning reminder with your task list\n"
            "✅ Let you mark tasks complete throughout the day\n"
            "📊 Track your streaks and progress\n"
            "🤖 Give you AI-powered motivation each evening\n\n"
            "Let's build better habits together! 💪"
        )

        await update.message.reply_text(welcome_text)
        await show_main_menu(update, context)

    except Exception as e:
        logger.error(f"Error in start_command: {e}", exc_info=True)
        await update.message.reply_text(
            "Something went wrong while starting up. Please try again."
        )


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user = update.effective_user
        await get_or_create_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
        )
        await show_main_menu(update, context)

    except Exception as e:
        logger.error(f"Error in menu_command: {e}", exc_info=True)
        await update.message.reply_text(
            "Something went wrong while loading the menu. Please try again."
        )


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📅 Today's Tasks", callback_data="menu_today"),
                InlineKeyboardButton("✏️ Plan Tomorrow", callback_data="menu_plan"),
            ],
            [
                InlineKeyboardButton("📊 My Stats", callback_data="menu_stats"),
                InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings"),
            ],
        ]
    )

    text = "🏠 Main Menu — What would you like to do?"

    if update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=keyboard)
    else:
        await update.message.reply_text(text, reply_markup=keyboard)


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        query = update.callback_query
        await query.answer()

        data = query.data

        if data == "menu_today":
            from handlers.task_handler import show_today_tasks
            await show_today_tasks(update, context)

        elif data == "menu_plan":
            from handlers.task_handler import start_planning
            await start_planning(update, context)

        elif data == "menu_stats":
            from handlers.stats_handler import show_stats
            await show_stats(update, context)

        elif data == "menu_settings":
            from handlers.settings_handler import show_settings
            await show_settings(update, context)

        elif data == "menu_home":
            await show_main_menu(update, context)

        else:
            logger.warning(f"Unhandled menu callback data: {data}")

    except Exception as e:
        logger.error(f"Error in menu_callback: {e}", exc_info=True)
        try:
            await update.callback_query.message.reply_text(
                "Something went wrong. Please try again."
            )
        except Exception:
            pass


def get_start_handlers() -> list:
    return [
        CommandHandler("start", start_command),
        CommandHandler("menu", menu_command),
        CallbackQueryHandler(menu_callback, pattern="^menu_"),
    ]
