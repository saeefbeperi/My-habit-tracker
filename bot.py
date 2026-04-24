import asyncio
import logging
import os

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route
from telegram import Update
from telegram.ext import Application

from database import init_db
from scheduler import setup_scheduler
from config import BOT_TOKEN, RENDER_EXTERNAL_URL, PORT
from handlers import (
    get_start_handlers,
    get_task_handlers,
    get_stats_handlers,
    get_settings_handlers,
    get_admin_handlers,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def health_check(request: Request) -> PlainTextResponse:
    return PlainTextResponse("✅ HabitFlow Bot is alive! 🌊")


async def telegram_webhook(request: Request) -> Response:
    bot_app = request.app.state.bot_app
    data = await request.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)
    return Response(status_code=200)


async def main() -> None:
    bot_app = Application.builder().token(BOT_TOKEN).build()

    for handler in get_start_handlers():
        bot_app.add_handler(handler)
    for handler in get_task_handlers():
        bot_app.add_handler(handler)
    for handler in get_stats_handlers():
        bot_app.add_handler(handler)
    for handler in get_settings_handlers():
        bot_app.add_handler(handler)
    for handler in get_admin_handlers():
        bot_app.add_handler(handler)

    await init_db()
    await bot_app.initialize()
    await bot_app.start()

    webhook_path = f"/webhook/{BOT_TOKEN}"
    await bot_app.bot.set_webhook(f"{RENDER_EXTERNAL_URL}{webhook_path}")
    setup_scheduler(bot_app)
    logger.info(f"✅ Webhook set: {RENDER_EXTERNAL_URL}{webhook_path}")

    starlette_app = Starlette(
        routes=[
            Route("/", health_check),
            Route("/health", health_check),
            Route(f"/webhook/{BOT_TOKEN}", telegram_webhook, methods=["POST"]),
        ]
    )
    starlette_app.state.bot_app = bot_app

    uvicorn_config = uvicorn.Config(starlette_app, host="0.0.0.0", port=PORT)
    server = uvicorn.Server(uvicorn_config)
    await server.serve()

    await bot_app.stop()
    await bot_app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
