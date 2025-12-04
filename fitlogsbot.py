import logging
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram import F
from aiogram.types import Message

import os
from aiohttp import web
import asyncio

TOKEN = os.getenv("TOKEN")

logging.basicConfig(level=logging.INFO)

from aiogram.client.default import DefaultBotProperties

bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()

@dp.message(F.text)
async def handle_message(message: Message):
    await message.answer("Бот работает! Ты написал: " + message.text)


async def start_webserver():
    async def handle(request):
        return web.Response(text="Bot is running")

    app = web.Application()
    app.add_routes([web.get("/", handle)])

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Web server started on port {port}")


async def main():
    asyncio.create_task(start_webserver())  # <-- добавили
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
