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

# Разрешённые пользователи (username без @)
ALLOWED_USERNAMES = {"gblsh", "staytorqued"}


def is_allowed_user(message: Message) -> bool:
    """
    Проверяет, может ли пользователь пользоваться ботом.
    Основано на username.
    """
    username = message.from_user.username
    if not username:
        return False
    return username.lower() in ALLOWED_USERNAMES


# -----------------------------
# Инициализация Бота + DP + Router
# -----------------------------
bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()
router = Router()
dp.include_router(router)


# -----------------------------
# Парсер строки от пользователя
# -----------------------------
def parse_workout_message(text: str):
    """
    Формат:
    'Имя; дата; упражнение; вес; подходы; повторения'

    Пример:
    'Роман Г.; 4.12; Тяга вертикального блока; 8; 4; 10'
    """
    parts = [p.strip() for p in text.split(";")]
    if len(parts) != 6:
        raise ValueError(
            "Неверный формат. Используй:\n"
            "Имя; дата; упражнение; вес; подходы; повторения\n\n"
            "Например:\n"
            "Роман Г.; 4.12; Тяга вертикального блока; 8; 4; 10"
        )

    athlete_name, date_str, exercise_name, weight_str, sets_str, reps_str = parts

    try:
        sets = int(sets_str.replace(",", "."))
        reps = int(reps_str.replace(",", "."))
    except ValueError:
        raise ValueError("Подходы и повторения должны быть целыми числами.")

    return athlete_name, date_str, exercise_name, weight_str, sets, reps


# -----------------------------
# Хэндлер обработки тренировок
# -----------------------------
@router.message(F.text.contains(";"))
async def handle_workout(message: Message):
    # проверка доступа
    if not is_allowed_user(message):
        await message.answer("Нет прав на бота")
        return

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
            f"Записал тренировку:\n"
            f"<b>{athlete_name}</b>\n"
            f"{date_str} — {exercise_name}\n"
            f"{weight_str} × {sets} × {reps}"
        )

    except Exception as e:
        await message.answer(f"Ошибка: {e}")


# -----------------------------
# Ответ на любое другое сообщение
# -----------------------------
@router.message()
async def fallback(message: Message):
    # проверка доступа
    if not is_allowed_user(message):
        await message.answer("Нет прав на бота")
        return

    await message.answer(
        "Бот работает! Отправь тренировку в формате:\n"
        "<b>Имя; дата; упражнение; вес; подходы; повторения</b>\n\n"
        "Например:\n"
        "Роман Г.; 4.12; Тяга вертикального блока; 8; 4; 10"
    )


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
