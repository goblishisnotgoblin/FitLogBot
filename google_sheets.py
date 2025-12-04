# google_sheets.py
import logging

import gspread
from google.oauth2.service_account import Credentials


# -----------------------------
# Карта "Имя атлета" -> "Spreadsheet ID"
# -----------------------------
ATHLETE_SHEETS = {
    # имя ДОЛЖНО совпадать с тем, что пишешь первым в сообщении боту
    "Роман Г.": "1YKpW75xuGky8o7jj-uZ2gQVk2mKHyh_YD4b9z188fHs",
    # сюда добавишь остальных при необходимости
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
# Запись тренировки
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
    Добавляет тренировку в таблицу.

    Логика:
    1. Находим строку упражнения в столбце A.
    2. В этой строке берём следующий свободный столбец.
    3. В ОДНУ ячейку (exercise_row, col) записываем многострочный текст:
       дата + sets строк "вес x повторения".

    Пример содержимого ячейки:
        4.12
        8x10
        8x10
        8x10
        8x10
    """
    ws = open_athlete_sheet(athlete_name)

    # 1. Строка с названием упражнения (например, "Тяга вертикального блока")
    exercise_row = find_exercise_row(ws, exercise_name)

    # 2. Следующий свободный столбец (B, C, D, ...)
    col = get_next_free_column(ws, exercise_row)

    # 3. Собираем текст для одной ячейки
    weight_str = weight_str.strip()
    if weight_str in ("", "0", "-"):
        set_line = f"x{reps}"
    else:
        # если хочешь кириллическую "х" и пробелы — поменяй на f"{weight_str} х {reps}"
        set_line = f"{weight_str}x{reps}"

    lines = [date_str] + [set_line for _ in range(sets)]
    cell_value = "\n".join(lines)  # многострочный текст внутри одной ячейки

    # 4. Записываем всё в одну ячейку (например, D1)
    ws.update_cell(exercise_row, col, cell_value)

    logging.info(
        f"Записал тренировку (одна ячейка): {athlete_name}, {date_str}, "
        f"{exercise_name}, {weight_str} × {sets} по {reps} в колонку {col}"
    )
