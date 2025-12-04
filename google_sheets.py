# google_sheets.py
import gspread
from google.oauth2.service_account import Credentials


SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
CREDS_FILE = "google-credentials.json"   # имя файла с ключами


def get_client():
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


def open_athlete_sheet(athlete_name: str):
    """
    Открывает файл Google Sheets по названию.
    Имя спортсмена == название файла, например 'Роман Г.'.
    """
    gc = get_client()
    # открываем по title
    return gc.open(athlete_name).sheet1  # берем первый лист

# google_sheets.py (продолжение)

from typing import Tuple


def find_exercise_row(ws, exercise_name: str) -> int:
    """
    Ищем строку, где в колонке A находится название упражнения.
    Возвращаем номер строки (1-based).
    """
    # читаем всю колонку A
    col_a = ws.col_values(1)
    exercise_name_lower = exercise_name.strip().lower()

    for idx, value in enumerate(col_a, start=1):
        if value.strip().lower() == exercise_name_lower:
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
        # если в колонке A что-то есть — началось следующее упражнение
        if row <= len(col_a) and col_a[row - 1].strip():
            end_row = row - 1
            break

    return exercise_row, end_row


def get_next_free_column(ws, row: int) -> int:
    """
    Ищем первый свободный столбец в заданной строке.
    """
    row_values = ws.row_values(row)
    # длина списка = количество заполненных ячеек слева направо
    return len(row_values) + 1


def add_workout(
    athlete_name: str,
    date_str: str,
    exercise_name: str,
    weight_str: str,
    sets: int,
    reps: int,
):
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
        # заменяем запятую на точку только для внутренних расчётов при желании,
        # в таблицу можно писать как есть
        cell_value = f"{weight_str}x{reps}"

    # заполняем подходы
    updates = []
    for i in range(sets):
        row = exercise_row + 1 + i
        updates.append(
            gspread.Cell(row=row, col=col, value=cell_value)
        )

    ws.update_cells(updates)
