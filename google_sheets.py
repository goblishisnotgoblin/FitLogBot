# google_sheets.py
import logging
from typing import Tuple

import gspread
from google.oauth2.service_account import Credentials


# -----------------------------
# Карта "Имя атлета" -> "Spreadsheet ID"
# -----------------------------
ATHLETE_SHEETS = {
    # имя ДОЛЖНО совпадать с тем, что пишешь первым в сообщении боту
    "Роман Г.": "1YKpW75xuGky8o7jj-uZ2gQVk2mKHyh_YD4b9z188fHs",
    # сюда можно добавить других людей:
    # "Иван": "1AbCdEfGh123...",
}


# -----------------------------
# Настройки доступа
# -----------------------------
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",  # можно оставить, вдруг пригодится
]
CREDS_FILE = "/etc/secrets/google-credentials.json"   # имя файла с ключами


def get_client():
    """
    Возвращает авторизованный gspread-клиент.
    """
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


def open_athlete_sheet(athlete_name: str):
    """
    Открывает файл Google Sheets по ИМЕНИ АТЛЕТА через ID таблицы.

    Было:
        gc.open(athlete_name).sheet1   # искали по названию файла

    Стало:
        берём ID из ATHLETE_SHEETS и открываем через open_by_key()
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
# Работа с упражнениями
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


def find_exercise_block(ws, exercise_row: int) -> Tuple[int, int]:
    """
    Находит границы блока упражнения.
    Начало блока = exercise_row
    Конец блока = строка перед следующей непустой ячейкой в колонке A
    или последняя строка листа.
    """
    col_a = ws.col_values(1)
    last_row = len(col_a) if col_a else ws.row_count

    end_row = last_row
    for row in range(exercise_row + 1, last_row + 1):
        if row <= len(col_a) and col_a[row - 1].strip():
            end_row = row - 1
            break

    logging.info(
        f"Блок упражнения: с {exercise_row} по {end_row} строку "
        f"(доступно строк под подходы: {end_row - exercise_row})"
    )
    return exercise_row, end_row


def get_next_free_column(ws, row: int) -> int:
    """
    Ищем первый свободный столбец в заданной строке.
    """
    row_values = ws.row_values(row)
    col = len(row_values) + 1
    logging.info(f"Следующий свободный столбец в строке {row}: {col}")
    return col


def add_workout(
    athlete_name: str,
    date_str: str,
    exercise_name: str,
    weight_str: str,
    sets: int,
    reps: int,
):
    """
    Добавляет тренировку в таблицу:
    - ищет нужное упражнение
    - находит новый столбец справа
    - пишет дату в заголовок
    - пишет подходы ниже
    """
    ws = open_athlete_sheet(athlete_name)

    # строка с названием упражнения
    exercise_row = find_exercise_row(ws, exercise_name)

    # границы блока упражнения
    block_start, block_end = find_exercise_block(ws, exercise_row)
    available_rows_for_sets = block_end - block_start

    if sets > available_rows_for_sets:
        raise ValueError(
            f"Для упражнения '{exercise_name}' в таблице предусмотрено "
            f"только {available_rows_for_sets} строк под подходы, "
            f"а ты хочешь записать {sets}."
        )

    # новый столбец справа
    col = get_next_free_column(ws, exercise_row)

    # заголовок с датой
    ws.update_cell(exercise_row, col, date_str)

    # подготовка значения типа "2,5x10" или "x10", если веса нет
    weight_str = weight_str.strip()
    if weight_str in ("", "0", "-"):
        cell_value = f"x{reps}"
    else:
        cell_value = f"{weight_str}x{reps}"

    # заполняем подходы
    from gspread import Cell  # можно и сверху импортнуть, если хочешь

    updates = []
    for i in range(sets):
        row = exercise_row + 1 + i
        updates.append(Cell(row=row, col=col, value=cell_value))

    ws.update_cells(updates)
    logging.info(
        f"Записал тренировку: {athlete_name}, {date_str}, {exercise_name}, "
        f"{weight_str} × {sets} по {reps} в столбец {col}"
    )
