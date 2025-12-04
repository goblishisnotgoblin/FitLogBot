import logging
import asyncio
import os

from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message

from google_sheets import add_workout


# -----------------------------
# Настройки логов и токена
# -----------------------------
logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("TOKEN")


# -----------------------------
# Инициализация Бота + DP + Router
# -----------------------------
bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()
router = Router()
dp.include_router(router)  # <-- ВАЖНО!


# -----------------------------
# Парсер строки от пользователя
# -----------------------------
def parse_workout_message(text: str):
    """
    Пример:
    'Роман Г.; 4.12; подтягивания; 2,5; 4; 10'
    """
    parts = [p.strip() for p in text.split(";")]
    if len(parts) != 6:
        raise ValueError(
            "Неверный формат. Используй: "
            "Имя; дата; упражнение; вес; подходы; повторения"
        )

    athlete_name, date_str, exercise_name, weight_str, sets_str, reps_str = parts

    sets = int(sets_str.replace(",", "."))
    reps = int(reps_str.replace(",", "."))

    return athlete_name, date_str, exercise_name, weight_str, sets, reps


# -----------------------------
# Хэндлер обработки тренировок
# -----------------------------
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
        await message.answer(f"Ошибка: {e}")


# -----------------------------
# Отвечает на всё остальное
# -----------------------------
@router.message()
async def fallback(message: Message):
    await message.answer("Бот работает! Напиши тренировку в формате:\n"
                         "Имя; дата; упражнение; вес; подходы; повторения")


# -----------------------------
# Web-сервер для Render
# -----------------------------
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


# -----------------------------
# ENTRYPOINT
# -----------------------------
async def main():
    asyncio.create_task(start_webserver())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
