import logging
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram import F
from aiogram.types import Message

import os
TOKEN = os.getenv("BOT_TOKEN")

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

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
