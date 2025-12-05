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
        "Привет! Я бот для логов тренировок.\n\n"
        "Можешь:\n"
        "• писать тренировки вручную в формате:\n"
        "  <code>Имя; дата; упражнение; вес; подходы; повторения</code>\n"
        "• или пользоваться меню через /people",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("people"))
async def cmd_people(message: Message):
    if not is_allowed_user(message):
        await message.answer("Этот бот только для @gblsh и @staytorqued 🙂")
        return

    reset_user_state(message.from_user.id)
    await message.answer("Выбери атлета:", reply_markup=athletes_keyboard())


# -----------------------------
# Callback: главное меню
# -----------------------------
@router.callback_query(F.data.startswith("main|"))
async def cb_main(callback: CallbackQuery):
    if not is_allowed_user(callback):
        await callback.answer("Нет доступа", show_alert=True)
        return

    user_id = callback.from_user.id
    reset_user_state(user_id)

    kind = callback.data.split("|", 1)[1]
    if kind == "people":
        await callback.message.edit_text(
            "Выбери атлета:", reply_markup=athletes_keyboard()
        )
    else:
        await callback.message.edit_text(
            "Главное меню. Используй /people или кнопки ниже.",
            reply_markup=main_menu_keyboard(),
        )
    await callback.answer()


# -----------------------------
# Callback: выбор атлета
# -----------------------------
@router.callback_query(F.data.startswith("athlete|"))
async def cb_athlete(callback: CallbackQuery):
    if not is_allowed_user(callback):
        await callback.answer("Нет доступа", show_alert=True)
        return

    user_id = callback.from_user.id
    _, athlete_name = callback.data.split("|", 1)
    reset_user_state(user_id)
    USER_STATE[user_id]["athlete"] = athlete_name

    await callback.message.edit_text(
        f"Выбран атлет: <b>{athlete_name}</b>\nВыбери действие:",
        reply_markup=athlete_actions_keyboard(),
    )
    await callback.answer()


# -----------------------------
# Callback: действия для атлета
# -----------------------------
@router.callback_query(F.data.startswith("action|"))
async def cb_action(callback: CallbackQuery):
    if not is_allowed_user(callback):
        await callback.answer("Нет доступа", show_alert=True)
        return

    user_id = callback.from_user.id
    state = USER_STATE.get(user_id)
    if not state or not state.get("athlete"):
        await callback.answer("Сначала выбери атлета через /people", show_alert=True)
        return

    _, action_name = callback.data.split("|", 1)
    if action_name == "add":
        USER_STATE[user_id]["mode"] = "add"
        await callback.message.edit_text(
            f"Атлет: <b>{state['athlete']}</b>\nВыбери упражнение:",
            reply_markup=exercises_keyboard(state["athlete"]),
        )
    elif action_name == "analysis":
        USER_STATE[user_id]["mode"] = "analysis"
        await callback.message.edit_text(
            f"Атлет: <b>{state['athlete']}</b>\nВыбери вид аналитики:",
            reply_markup=analysis_keyboard(),
        )

    await callback.answer()


# -----------------------------
# Callback: назад к действиям атлета
# -----------------------------
@router.callback_query(F.data == "back|athlete")
async def cb_back_athlete(callback: CallbackQuery):
    if not is_allowed_user(callback):
        await callback.answer("Нет доступа", show_alert=True)
        return

    user_id = callback.from_user.id
    state = USER_STATE.get(user_id)
    if not state or not state.get("athlete"):
        reset_user_state(user_id)
        await callback.message.edit_text(
            "Выбери атлета:", reply_markup=athletes_keyboard()
        )
    else:
        USER_STATE[user_id]["exercise"] = None
        USER_STATE[user_id]["awaiting_volume"] = False
        await callback.message.edit_text(
            f"Выбран атлет: <b>{state['athlete']}</b>\nВыбери действие:",
            reply_markup=athlete_actions_keyboard(),
        )
    await callback.answer()


# -----------------------------
# Callback: выбор упражнения
# -----------------------------
@router.callback_query(F.data.startswith("exercise|"))
async def cb_exercise(callback: CallbackQuery):
    if not is_allowed_user(callback):
        await callback.answer("Нет доступа", show_alert=True)
        return

    user_id = callback.from_user.id
    state = USER_STATE.get(user_id)
    if not state or not state.get("athlete"):
        await callback.answer("Сначала выбери атлета через /people", show_alert=True)
        return

    _, idx_str = callback.data.split("|", 1)
    try:
        idx = int(idx_str)
    except ValueError:
        await callback.answer("Неверный формат callback данных", show_alert=True)
        return

    exercises = get_exercises(state["athlete"])
    try:
        exercise_name = exercises[idx]
    except IndexError:
        await callback.answer("Не удалось найти упражнение", show_alert=True)
        return

    USER_STATE[user_id]["exercise"] = exercise_name
    USER_STATE[user_id]["awaiting_volume"] = True

    await callback.message.edit_text(
        f"Атлет: <b>{state['athlete']}</b>\n"
        f"Упражнение: <b>{exercise_name}</b>\n\n"
        f"Теперь напиши объём в формате:\n"
        f"<code>дата кол-во_подходовxвесxповторы ...</code>\n"
        f"Пример:\n"
        f"<code>5.12 2x5x10 3x8x10</code>\n\n"
        f"Кнопки:\n"
        f"⏮ Назад — к выбору упражнения\n"
        f"⏪ Выход — в главное меню",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⏮ Назад", callback_data="back|athlete")],
                [
                    InlineKeyboardButton(
                        text="⏪ Выход в главное меню", callback_data="main|menu"
                    )
                ],
            ]
        ),
    )
    await callback.answer()


# -----------------------------
# Callback: аналитика
# -----------------------------
@router.callback_query(F.data.startswith("analysis|"))
async def cb_analysis(callback: CallbackQuery):
    if not is_allowed_user(callback):
        await callback.answer("Нет доступа", show_alert=True)
        return

    user_id = callback.from_user.id
    state = USER_STATE.get(user_id)
    if not state or not state.get("athlete"):
        await callback.answer("Сначала выбери атлета через /people", show_alert=True)
        return

    _, kind = callback.data.split("|", 1)

    if kind == "old":
        await callback.message.edit_text(
            f"Атлет: <b>{state['athlete']}</b>\n\n"
            f"Сколько старых упражнений показать?",
            reply_markup=old_count_keyboard(),
        )

    await callback.answer()


# -----------------------------
# Callback: выбор количества старых упражнений (1–9)
# -----------------------------
@router.callback_query(F.data.startswith("oldn|"))
async def cb_oldn(callback: CallbackQuery):
    if not is_allowed_user(callback):
        await callback.answer("Нет доступа", show_alert=True)
        return

    user_id = callback.from_user.id
    state = USER_STATE.get(user_id)
    if not state or not state.get("athlete"):
        await callback.answer("Сначала выбери атлета через /people", show_alert=True)
        return

    _, n_str = callback.data.split("|", 1)
    try:
        n = int(n_str)
    except ValueError:
        await callback.answer("Неверное число", show_alert=True)
        return

    if not (1 <= n <= 9):
        await callback.answer("Нужно число от 1 до 9", show_alert=True)
        return

    try:
        items = get_oldest_exercises(state["athlete"], n)
    except Exception as e:
        await callback.message.answer(f"Ошибка при получении аналитики: {e}")
        await callback.answer()
        return

    if not items:
        await callback.message.answer("Не нашёл старых упражнений для этого атлета.")
        await callback.answer()
        return

    lines = [f"Вот {len(items)} упражнен(ия/ий), которые выполнялись давно:\n"]
    for ex_name, ex_lines in items:
        lines.append(ex_name)
        lines.extend(ex_lines)
        lines.append("")  # пустая строка между упражнениями

    reply = "\n".join(lines).rstrip()

    await callback.message.answer(reply)
    await callback.answer()


# -----------------------------
# Обработка сообщений с ';' (старый формат)
# -----------------------------
@router.message(F.text.contains(";"))
async def handle_semicolon_workout(message: Message):
    if not is_allowed_user(message):
        await message.answer("Этот бот только для @gblsh и @staytorqued 🙂")
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
            f"Записал тренировку (старый формат):\n"
            f"<b>{athlete_name}</b>\n"
            f"{date_str} — {exercise_name}\n"
            f"{weight_str} × {sets} × {reps}"
        )

    except Exception as e:
        await message.answer(f"Ошибка: {e}")


# -----------------------------
# Обработка остальных сообщений
# -----------------------------
@router.message()
async def handle_any_message(message: Message):
    if not is_allowed_user(message):
        await message.answer("Этот бот только для @gblsh и @staytorqued 🙂")
        return

    user_id = message.from_user.id
    state = USER_STATE.get(user_id)

    # Ожидаем объём тренировки (новый формат)
    if (
        state
        and state.get("awaiting_volume")
        and state.get("athlete")
        and state.get("exercise")
    ):
        try:
            lines = parse_volume_string(message.text)
            add_workout_cell(
                athlete_name=state["athlete"],
                exercise_name=state["exercise"],
                lines=lines,
            )

            await message.answer(
                "Записал тренировку (через меню):\n"
                f"Атлет: <b>{state['athlete']}</b>\n"
                f"Упражнение: <b>{state['exercise']}</b>\n\n"
                f"<code>{chr(10).join(lines)}</code>"
            )

            USER_STATE[user_id]["awaiting_volume"] = False

        except Exception as e:
            await message.answer(f"Ошибка при разборе объёма: {e}")
        return

    # Фолбэк
    await message.answer(
        "Бот работает.\n\n"
        "Можешь:\n"
        "• Записать тренировку так:\n"
        "<code>Имя; дата; упражнение; вес; подходы; повторения</code>\n"
        "• Или вызвать меню: /people"
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
    logging.info(
        f"Web server started on port {port}. "
        f"Bot version {VERSION}, Sheets version {GS_VERSION}"
    )


# -----------------------------
# ENTRYPOINT
# -----------------------------
async def main():
    asyncio.create_task(start_webserver())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
