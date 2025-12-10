# google_sheets.py — version v1.14
import logging
from datetime import datetime, date

import gspread
from google.oauth2.service_account import Credentials


VERSION = "v1.14"  # версия этого файла


# -----------------------------
# Карта "Имя атлета" -> Spreadsheet ID
# -----------------------------
ATHLETE_SHEETS = {
    "Роман Г.": "1YKpW75xuGky8o7jj-uZ2gQVk2mKHyh_YD4b9z188fHs",
    "Олег": "1Qsa1tkW7W3aRfqZsACwiRnQdB-lnAD643OK7ABXwG14",
}


# -----------------------------
# Авторизация
# -----------------------------
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

CREDS_FILE = "/etc/secrets/google-credentials.json"


def get_client():
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


# -----------------------------
# Открытие таблицы / списков
# -----------------------------
def open_athlete_sheet(athlete_name: str):
    gc = get_client()
    spreadsheet_id = ATHLETE_SHEETS.get(athlete_name)
    if not spreadsheet_id:
        raise RuntimeError(f"Нет ID таблицы для '{athlete_name}'")

    sh = gc.open_by_key(spreadsheet_id)
    ws = sh.sheet1
    return gc, sh, ws


def get_athletes():
    return list(ATHLETE_SHEETS.keys())


def get_exercises(athlete_name: str):
    """
    Просто все значения из столбца A (без фильтрации по '-').
    Фильтрацией занимаемся уже на уровне бота.
    """
    _, _, ws = open_athlete_sheet(athlete_name)
    col_a = ws.col_values(1)
    return [v.strip() for v in col_a if v.strip()]


# -----------------------------
# Вспомогательные функции
# -----------------------------
def find_exercise_row(ws, exercise_name: str) -> int:
    col_a = ws.col_values(1)
    for idx, value in enumerate(col_a, start=1):
        if value.strip().lower() == exercise_name.strip().lower():
            return idx
    raise ValueError(f"Упражнение '{exercise_name}' не найдено")


def get_next_free_column(ws, row: int) -> int:
    values = ws.row_values(row)
    return len(values) + 1


def batch_update_cell_with_rich_text(sh, sheet_id, row, col, text: str):
    """
    Записать текст и сделать первую строку (дату) жирной курсивной.
    """
    first_line_len = text.find("\n")
    if first_line_len == -1:
        first_line_len = len(text)

    body = {
        "requests": [
            {
                "updateCells": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": row - 1,
                        "endRowIndex": row,
                        "startColumnIndex": col - 1,
                        "endColumnIndex": col,
                    },
                    "rows": [
                        {
                            "values": [
                                {
                                    "userEnteredValue": {"stringValue": text},
                                    "textFormatRuns": [
                                        {
                                            "startIndex": 0,
                                            "format": {"bold": True, "italic": True},
                                        },
                                        {
                                            "startIndex": first_line_len,
                                            "format": {
                                                "bold": False,
                                                "italic": False,
                                            },
                                        },
                                    ],
                                }
                            ]
                        }
                    ],
                    "fields": "userEnteredValue,textFormatRuns",
                }
            }
        ]
    }

    sh.batch_update(body)


# -----------------------------
# Запись тренировки в существующее упражнение
# -----------------------------
def add_workout_cell(athlete_name: str, exercise_name: str, lines: list[str]):
    """
    Пример lines:
    ["5.12", "8x10", "8x10", "8x10"]
    """
    _, sh, ws = open_athlete_sheet(athlete_name)
    sheet_id = ws.id

    exercise_row = find_exercise_row(ws, exercise_name)
    col = get_next_free_column(ws, exercise_row)

    cell_text = "\n".join(lines)

    batch_update_cell_with_rich_text(
        sh=sh,
        sheet_id=sheet_id,
        row=exercise_row,
        col=col,
        text=cell_text,
    )

    logging.info(
        f"Записал тренировку для {athlete_name}: {exercise_name} в колонку {col}"
    )


def add_workout(athlete_name, date_str, exercise_name, weight_str, sets, reps):
    """
    Старый формат с ';'
    """
    weight_str = weight_str.strip()
    if weight_str in ("", "0", "-"):
        one = f"x{reps}"
    else:
        one = f"{weight_str}x{reps}"

    lines = [date_str] + [one] * sets
    add_workout_cell(athlete_name, exercise_name, lines)


# -----------------------------
# Добавление нового упражнения + первая тренировка
# -----------------------------
def add_exercise_with_workout(
    athlete_name: str,
    exercise_name: str,
    lines: list[str],
):
    """
    Добавляет новое упражнение в конец таблицы и записывает тренировку
    в первую свободную ячейку строки (обычно колонка B).
    """
    gc, sh, ws = open_athlete_sheet(athlete_name)
    sheet_id = ws.id

    # Проверка на дубликат (без учёта префикса '-')
    col_a = ws.col_values(1)
    ex_lower = exercise_name.strip().lower()
    for val in col_a:
        name = val.strip().lstrip("-").strip().lower()
        if name == ex_lower:
            raise ValueError(f"Упражнение '{exercise_name}' уже есть в списке")

    all_values = ws.get_all_values()
    new_row = len(all_values) + 1 if all_values else 1

    # Имя упражнения в столбец A
    ws.update_cell(new_row, 1, exercise_name)

    # Тренировка в колонку B
    cell_text = "\n".join(lines)
    batch_update_cell_with_rich_text(
        sh=sh,
        sheet_id=sheet_id,
        row=new_row,
        col=2,
        text=cell_text,
    )

    logging.info(
        f"Добавил новое упражнение '{exercise_name}' для {athlete_name} "
        f"в строку {new_row} и записал тренировку"
    )


# -----------------------------
# Сделать упражнение неактуальным
# -----------------------------
def make_exercise_inactive(athlete_name: str, exercise_name: str):
    """
    Переносит строку упражнения в конец таблицы, сохраняя полностью
    форматирование строки (moveDimension/copy), затем:
    - добавляет '-' перед названием в A
    - красит строку в серый.
    """
    gc, sh, ws = open_athlete_sheet(athlete_name)
    sheet_id = ws.id

    all_values = ws.get_all_values()
    if not all_values:
        raise ValueError("Таблица пустая")

    # Находим строку упражнения по точному совпадению
    row_idx = None
    for idx, row in enumerate(all_values, start=1):
        if row and row[0].strip() == exercise_name.strip():
            row_idx = idx
            break

    if row_idx is None:
        raise ValueError(f"Упражнение '{exercise_name}' не найдено в столбце A")

    row_count = len(all_values)
    col_count = ws.col_count

    # 1) Копируем строку в самый низ (включая форматирование)
    body = {
        "requests": [
            {
                "copyPaste": {
                    "source": {
                        "sheetId": sheet_id,
                        "startRowIndex": row_idx - 1,
                        "endRowIndex": row_idx,
                        "startColumnIndex": 0,
                        "endColumnIndex": col_count,
                    },
                    "destination": {
                        "sheetId": sheet_id,
                        "startRowIndex": row_count,
                        "endRowIndex": row_count + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": col_count,
                    },
                    "pasteType": "PASTE_NORMAL",
                }
            },
            {
                "deleteDimension": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": row_idx - 1,
                        "endIndex": row_idx,
                    }
                }
            },
        ]
    }
    sh.batch_update(body)

    # После копирования+удаления новая строка оказывается на позиции row_count (0-based),
    # т.е. в нумерации Google Sheets 1-based это row_count.
    new_row = row_count

    # 2) Обновляем название с префиксом '-'
    new_name = exercise_name.strip()
    if not new_name.startswith("-"):
        new_name = "-" + new_name
    ws.update_cell(new_row, 1, new_name)

    # 3) Красим строку в серый цвет
    gray_body = {
        "requests": [
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": new_row - 1,
                        "endRowIndex": new_row,
                        "startColumnIndex": 0,
                        "endColumnIndex": col_count,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {
                                "red": 0.9,
                                "green": 0.9,
                                "blue": 0.9,
                            }
                        }
                    },
                    "fields": "userEnteredFormat.backgroundColor",
                }
            }
        ]
    }
    sh.batch_update(gray_body)

    logging.info(
        f"Упражнение '{exercise_name}' для {athlete_name} "
        f"помечено как неактуальное (строка {new_row})"
    )


# -----------------------------
# Парсинг даты без года
# -----------------------------
def parse_date_without_year(date_str: str):
    """
    Принимает строку вида '5.12' или '05.12', возвращает date с годом.
    """
    s = date_str.strip().replace(" ", "").replace("/", ".")
    if not s:
        return None

    try:
        dt = datetime.strptime(s, "%d.%m")
    except ValueError:
        return None

    today = date.today()
    dt = dt.replace(year=today.year)
    d = dt.date()
    if d > today:
        d = d.replace(year=today.year - 1)

    return d


# -----------------------------
# Получение самых старых упражнений
# -----------------------------
def get_oldest_exercises(athlete_name: str, limit: int):
    """
    Возвращает список из limit элементов вида:
        (exercise_name, lines)

    Упражнения, у которых название в столбце A начинается с '-', игнорируются.
    """
    _, sh, ws = open_athlete_sheet(athlete_name)

    all_values = ws.get_all_values()
    row_count = len(all_values)
    if row_count == 0:
        return []

    items = []

    for idx in range(row_count):
        row = all_values[idx]
        exercise_name = (row[0].strip() if row else "")
        if not exercise_name:
            continue

        # Игнорируем неактуальные упражнения
        if exercise_name.startswith("-"):
            continue

        # последняя непустая ячейка в строке (кроме A)
        last_text = ""
        for val in reversed(row[1:]):
            if val.strip():
                last_text = val
                break

        if not last_text:
            continue

        lines = [ln.strip() for ln in last_text.split("\n") if ln.strip()]
        if not lines:
            continue

        d = parse_date_without_year(lines[0])
        if not d:
            continue

        items.append(
            {
                "exercise": exercise_name,
                "date": d,
                "lines": lines,
            }
        )

    items.sort(key=lambda x: x["date"])

    result = []
    for it in items[:limit]:
        result.append((it["exercise"], it["lines"]))

    return result
