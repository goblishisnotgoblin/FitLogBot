# google_sheets.py
import logging

import gspread
from google.oauth2.service_account import Credentials


# -----------------------------
# Карта "Имя атлета" -> "Spreadsheet ID"
# -----------------------------
ATHLETE_SHEETS = {
    # Имя ДОЛЖНО совпадать с тем, что ты пишешь первым в сообщении боту
    "Роман Г.": "1YKpW75xuGky8o7jj-uZ2gQVk2mKHyh_YD4b9z188fHs",
    "Олег": "1Qsa1tkW7W3aRfqZsACwiRnQdB-lnAD643OK7ABXwG14",
    # Добавишь сюда других при необходимости
}


# -----------------------------
# Настройки доступа
# -----------------------------
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
CREDS_FILE = "/etc/secrets/google-credentials.json"   # путь к ключам сервисного аккаунта


def get_client():
    """
    Возвращает авторизованный gspread-клиент.
    """
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


def open_athlete_sheet(athlete_name: str):
    """
    Открывает файл Google Sheets для указанного спортсмена по ID.
    """
    logging.info(f"Открываю таблицу для спортсмена: {athlete_name!r}")
    gc = get_client()

    spreadsheet_id = ATHLETE_SHEETS.get(athlete_name)
    if not spreadsheet_id:
        raise RuntimeError(
            f"Для спортсмена '{athlete_name}' не найден ID таблицы.\n"
            f"Добавь его в словарь ATHLETE_SHEETS в google_sheets.py."
        )

    try:
        sh = gc.open_by_key(spreadsheet_id)
        return sh.sheet1
    except Exception as e:
        logging.exception("Не удалось открыть таблицу по ID")
        raise RuntimeError(
            f"Не удалось открыть таблицу для '{athlete_name}'. "
            f"Проверь, что ID верный и файл расшарен на сервисный аккаунт."
        ) from e


# -----------------------------
# Утилиты для списка атлетов / упражнений
# -----------------------------
def get_athletes() -> list[str]:
    """
    Возвращает список имён атлетов (ключи ATHLETE_SHEETS).
    """
    return list(ATHLETE_SHEETS.keys())


def get_exercises(athlete_name: str) -> list[str]:
    """
    Возвращает список упражнений из столбца A (непустые строки).
    """
    ws = open_athlete_sheet(athlete_name)
    col_a = ws.col_values(1)
    return [v.strip() for v in col_a if v.strip()]


# -----------------------------
# Поиск упражнения и свободного столбца
# -----------------------------
def find_exercise_row(ws, exercise_name: str) -> int:
    """
    Ищем строку, где в колонке A находится название упражнения.
    Возвращаем номер строки (1-based).
    """
    col_a = ws.col_values(1)
    exercise_name_lower = exercise_name.strip().lower()

    for idx, value in enumerate(col_a, start=1):
        if value.strip().lower() == exercise_name_lower:
            logging.info(f"Нашёл упражнение {exercise_name!r} в строке {idx}")
            return idx

    raise ValueError(f"Упражнение '{exercise_name}' не найдено в столбце A")


def get_next_free_column(ws, row: int) -> int:
    """
    Ищем первый свободный столбец в заданной строке.
    Логика: считаем количество НЕпустых ячеек в строке -> следующий столбец.
    """
    row_values = ws.row_values(row)
    col = len(row_values) + 1
    logging.info(f"Следующий свободный столбец в строке {row}: {col}")
    return col


# -----------------------------
# Базовая запись в одну ячейку
# -----------------------------
def add_workout_cell(
    athlete_name: str,
    exercise_name: str,
    lines: list[str],
):
    """
    Пишет список строк в одну ячейку упражнения:
    lines[0] = дата
    остальные = подходы (вес x повторы и т.п.).
    """
    ws = open_athlete_sheet(athlete_name)

    # 1. Строка с названием упражнения (например, "Тяга вертикального блока")
    exercise_row = find_exercise_row(ws, exercise_name)

    # 2. Следующий свободный столбец (B, C, D, ...)
    col = get_next_free_column(ws, exercise_row)

    # 3. Собираем многострочный текст
    cell_value = "\n".join(lines)

    # 4. Записываем всё в одну ячейку (например, D1)
    ws.update_cell(exercise_row, col, cell_value)

    logging.info(
        f"Записал тренировку (одна ячейка): {athlete_name}, {exercise_name}, "
        f"строк={len(lines)} в колонку {col}"
    )


# -----------------------------
# Старый простой формат с ';'
# -----------------------------
def add_workout(
    athlete_name: str,
    date_str: str,
    exercise_name: str,
    weight_str: str,
    sets: int,
    reps: int,
):
    """
    Поддерживает старый формат:
    Имя; дата; упражнение; вес; подходы; повторения

    Пример содержимого ячейки:
        4.12
        8x10
        8x10
        8x10
        8x10
    """
    weight_str = weight_str.strip()
    if weight_str in ("", "0", "-"):
        set_line = f"x{reps}"
    else:
        set_line = f"{weight_str}x{reps}"

    lines = [date_str] + [set_line for _ in range(sets)]
    add_workout_cell(athlete_name, exercise_name, lines)
