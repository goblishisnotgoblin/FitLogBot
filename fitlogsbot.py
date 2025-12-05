# fitlogsbot.py — version v1.09
import logging
import asyncio
import os

from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters import Command

from google_sheets import (
    VERSION as GS_VERSION,
    add_workout,
    add_workout_cell,
    get_athletes,
    get_exercises,
    get_oldest_exercises,
)


VERSION = "v1.09"  # <--- версия этого файла


# -----------------------------
# Настройки логов и токена
# -----------------------------
logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("TOKEN")

# Разрешённые пользователи (username без @)
ALLOWED_USERNAMES = {"gblsh", "staytorqued"}


def is_allowed_user(message_or_callback) -> bool:
    from_user = message_or_callback.from_user
    username = from_user.username
    if not username:
        return False
    return username.lower() in ALLOWED_USERNAMES


# -----------------------------
# Состояние пользователей
# -----------------------------
# user_id -> {...}
USER_STATE: dict[int, dict] = {}


def reset_user_state(user_id: int):
    USER_STATE[user_id] = {
        "athlete": None,
        "mode": None,
        "exercise": None,
        "awaiting_volume": False,
    }


# -----------------------------
# Инициализация бота
# -----------------------------
bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()
router = Router()
dp.include_router(router)


# -----------------------------
# Парсер старого формата с ';'
# -----------------------------
def parse_workout_message(text: str):
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
# Парсер объёма: "5.12 2x5x10 3x8x10"
# -----------------------------
def parse_volume_string(volume_str: str) -> list[str]:
    parts = volume_str.strip().split()
    if len(parts) < 2:
        raise ValueError("Неверный формат объёма. Пример: 5.12 2x5x10 3x8x10")

    date_str = parts[0]
    groups = parts[1:]

    lines = [date_str]

    for g in groups:
        g_clean = g.replace("х", "x").lower()
        try:
            sets_str, weight_str, reps_str = g_clean.split("x")
            sets = int(sets_str)
            weight = weight_str
            reps = int(reps_str)
        except Exception:
            raise ValueError(f"Неверный формат группы '{g}'. Ожидаю что-то вроде 2x5x10")

        for _ in range(sets):
            lines.append(f"{weight}x{reps}")

    return lines


# -----------------------------
# Клавиатуры
# -----------------------------
def main_menu_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Атлеты", callback_data="main|people")]
        ]
    )


def athletes_keyboard():
    athletes = get_athletes()
    buttons = [
        [InlineKeyboardButton(text=name, callback_data=f"athlete|{name}")]
        for name in athletes
    ]
    buttons.append(
        [InlineKeyboardButton(text="⏪ Выход в главное меню", callback_data="main|menu")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def athlete_actions_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Добавить тренировку", callback_data="action|add"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📊 Аналитика", callback_data="action|analysis"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⏪ Выход в главное меню", callback_data="main|menu"
                )
            ],
        ]
    )


def analysis_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🧓 Старые упражнения", callback_data="analysis|old"
                )
            ],
            [InlineKeyboardButton(text="⏮ Назад", callback_data="back|athlete")],
            [InlineKeyboardButton(text="⏪ Выход", callback_data="main|menu")],
        ]
    )


def old_count_keyboard():
    rows = []
    for row in (1, 4, 7):
        rows.append(
            [
                InlineKeyboardButton(text=str(row), callback_data=f"oldn|{row}"),
                InlineKeyboardButton(text=str(row + 1), callback_data=f"oldn|{row+1}"),
                InlineKeyboardButton(text=str(row + 2), callback_data=f"oldn|{row+2}"),
            ]
        )
    rows.append([InlineKeyboardButton(text="⏮ Назад", callback_data="back|athlete")])
    rows.append(
        [InlineKeyboardButton(text="⏪ Выход в главное меню", callback_data="main|menu")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def exercises_keyboard(athlete_name: str):
    exercises = get_exercises(athlete_name)
    buttons = []
    for idx, ex in enumerate(exercises):
        buttons.append(
            [InlineKeyboardButton(text=ex, callback_data=f"exercise|{idx}")]
        )
    buttons.append([InlineKeyboardButton(text="⏮ Назад", callback_data="back|athlete")])
    buttons.append(
        [InlineKeyboardButton(text="⏪ Выход в главное меню", callback_data="main|menu")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# -----------------------------
# /version
# -----------------------------
@router.message(Command("version"))
async def cmd_version(message: Message):
    if not is_allowed_user(message):
        await message.answer("Этот бот только для @gblsh и @staytorqued 🙂")
        return

    await message.answer(
        f"Текущие версии:\n"
        f"<b>fitlogsbot.py:</b> {VERSION}\n"
        f"<b>google_sheets.py:</b> {GS_VERSION}"
    )


# -----------------------------
# /start и /people
# -----------------------------
@router.message(Command("start"))
async def cmd_start(message: Message):
    if not is_allowed_user(message):
        await message.answer("Этот бот только для @gblsh и @staytorqued 🙂")
        return

    reset_user_state(message.from_user.id)
    await message.answer(
        "Привет! Я бот для логов тренировок.\n\n
