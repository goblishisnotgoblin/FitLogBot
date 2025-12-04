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

# fitlogsbot.py (или где у тебя dp / router)

from aiogram import Router, F
from aiogram.types import Message

from google_sheets import add_workout

router = Router()


def parse_workout_message(text: str):
    """
    Парсим строку вида:
    'Роман Г.; 4.12; подтягивания; 2,5; 4; 10'
    """
    parts = [p.strip() for p in text.split(";")]
    if len(parts) != 6:
        raise ValueError(
            "Неверный формат. Используй: "
            "Имя; дата; упражнение; вес; кол-во подходов; кол-во повторений"
        )

    athlete_name, date_str, exercise_name, weight_str, sets_str, reps_str = parts

    # поддержим запятую как разделитель десятичной части, а в таблицу пишем как есть
    sets = int(sets_str.replace(",", "."))
    reps = int(reps_str.replace(",", "."))

    return athlete_name, date_str, exercise_name, weight_str, sets, reps


@router.message(F.text.contains(";"))
async def handle_workout(message: Message):
    try:
        athlete_name, date_str, exercise_name, weight_str, sets, reps = \
            parse_workout_message(message.text)

        add_workout(
            athlete_name=athlete_name,
            date_str=date_str,
            exercise_name=exercise_name,
            weight_str=weight_str,
            sets=sets,
            reps=reps,
        )

        await message.answer(
            f"Записал: {athlete_name}, {date_str}, {exercise_name}, "
            f"{weight_str} × {sets} по {reps}"
        )

    except Exception as e:
        # В бою лучше логировать e и показывать юзеру более простой текст
        await message.answer(f"Не получилось записать тренировку: {e}")
