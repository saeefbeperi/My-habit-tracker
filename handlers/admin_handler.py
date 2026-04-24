import logging

from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
from telegram.error import Forbidden, TelegramError

from database import get_all_users
from config import ADMIN_ID, ConversationState

logger = logging.getLogger(__name__)

ADMIN_BROADCAST = ConversationState.ADMIN_BROADCAST


def _is_admin(update: Update) -> bool:
    return update.effective_user.id == ADMIN_ID


async def _deny(update: Update) -> None:
    try:
        await update.message.reply_text("⛔ Not authorized.")
    except Exception:
        pass


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if not _is_admin(update):
            await _deny(update)
            return

        try:
            users = await get_all_users()
            total = len(users)
        except Exception as e:
            logger.error(f"DB error in admin_panel get_all_users: {e}", exc_info=True)
            total = 0

        text = (
            "🔧 *Admin Panel — HabitFlow*\n\n"
            f"👥 Total Users: *{total}*\n"
            "📊 Send a broadcast: /broadcast\n"
            "🏠 Type /menu for user view"
        )

        await update.message.reply_text(text, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error in admin_panel: {e}", exc_info=True)
        try:
            await update.message.reply_text(
                "Something went wrong loading the admin panel."
            )
        except Exception:
            pass


async def broadcast_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    try:
        if not _is_admin(update):
            await _deny(update)
            return ConversationHandler.END

        try:
            users = await get_all_users()
            total = len(users)
        except Exception as e:
            logger.error(
                f"DB error in broadcast_start get_all_users: {e}", exc_info=True
            )
            total = 0

        await update.message.reply_text(
            f"📢 Type your broadcast message. It will be sent to ALL *{total}* users.\n\n"
            "Send /cancel to abort.",
            parse_mode="Markdown",
        )
        return ADMIN_BROADCAST

    except Exception as e:
        logger.error(f"Error in broadcast_start: {e}", exc_info=True)
        try:
            await update.message.reply_text("Something went wrong. Please try again.")
        except Exception:
            pass
        return ConversationHandler.END


async def broadcast_send(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    try:
        if not _is_admin(update):
            await _deny(update)
            return ConversationHandler.END

        message_text = update.message.text.strip()

        if not message_text:
            await update.message.reply_text(
                "Message cannot be empty. Please type your broadcast message."
            )
            return ADMIN_BROADCAST

        try:
            users = await get_all_users()
        except Exception as e:
            logger.error(
                f"DB error in broadcast_send get_all_users: {e}", exc_info=True
            )
            await update.message.reply_text(
                "❌ Failed to fetch users. Broadcast aborted."
            )
            return ConversationHandler.END

        total = len(users)
        success_count = 0
        skip_count = 0

        await update.message.reply_text(
            f"📤 Sending broadcast to {total} users, please wait..."
        )

        for user_record in users:
            user_id = user_record.get("user_id") or user_record.get("id")
            if not user_id:
                logger.warning(f"Skipping user record with no user_id: {user_record}")
                skip_count += 1
                continue

            try:
                await context.application.bot.send_message(
                    chat_id=user_id,
                    text=message_text,
                )
                success_count += 1
                logger.info(f"Broadcast sent to user {user_id}")

            except Forbidden:
                logger.info(
                    f"Broadcast skipped for user {user_id}: bot was blocked by user"
                )
                skip_count += 1

            except TelegramError as e:
                logger.warning(
                    f"Broadcast failed for user {user_id}: {e}"
                )
                skip_count += 1

            except Exception as e:
                logger.error(
                    f"Unexpected error broadcasting to user {user_id}: {e}",
                    exc_info=True,
                )
                skip_count += 1

        report = (
            f"✅ Broadcast sent to *{success_count}/{total}* users.\n"
            f"⏭️ Skipped / failed: *{skip_count}*"
        )
        await update.message.reply_text(report, parse_mode="Markdown")
        logger.info(
            f"Broadcast complete: {success_count} sent, {skip_count} skipped out of {total} total."
        )

        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error in broadcast_send: {e}", exc_info=True)
        try:
            await update.message.reply_text(
                "Something went wrong during broadcast. Please try again."
            )
        except Exception:
            pass
        return ConversationHandler.END


async def broadcast_cancel(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    try:
        if not _is_admin(update):
            await _deny(update)
            return ConversationHandler.END

        await update.message.reply_text("❌ Broadcast cancelled.")
        logger.info(f"Broadcast cancelled by admin {update.effective_user.id}")

    except Exception as e:
        logger.error(f"Error in broadcast_cancel: {e}", exc_info=True)

    return ConversationHandler.END


def get_admin_handlers() -> list:
    broadcast_conversation = ConversationHandler(
        entry_points=[
            CommandHandler("broadcast", broadcast_start),
        ],
        states={
            ADMIN_BROADCAST: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, broadcast_send
                ),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", broadcast_cancel),
            CommandHandler("menu", broadcast_cancel),
        ],
        per_message=False,
    )

    return [
        CommandHandler("admin", admin_panel),
        broadcast_conversation,
    ]
