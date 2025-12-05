# google_sheets.py
import logging

import gspread
from google.oauth2.service_account import Credentials


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
# Открытие таблицы / списка упражнений
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
    _, _, ws = open_athlete_sheet(athlete_name)
    col_a = ws.col_values(1)
    return [v.strip() for v in col_a if v.strip()]


# -----------------------------
# Поиск строки упражнения
# -----------------------------
def find_exercise_row(ws, exercise_name: str) -> int:
    col_a = ws.col_values(1)
    for idx, value in enumerate(col_a, start=1):
        if value.strip().lower() == exercise_name.strip().lower():
            return idx
    raise ValueError(f"Упражнение '{exercise_name}' не найдено")


# -----------------------------
# Поиск свободного столбца
# -----------------------------
def get_next_free_column(ws, row: int) -> int:
    values = ws.row_values(row)
    return len(values) + 1


# -----------------------------
# Форматирование: жирный курсив только первой строки
# -----------------------------
def batch_update_cell_with_rich_text(sh, sheet_id, row, col, text: str):
    """
    Один batchUpdate:
    — Заменяем текст ячейки
    — Применяем textFormatRuns, делая первую строку жирной и курсивной
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
                                            "format": {"bold": False, "italic": False},
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
# Запись тренировки в ячейку
# -----------------------------
def add_workout_cell(athlete_name: str, exercise_name: str, lines: list[str]):
    """
    Пример lines:
    ["5.12", "8x10", "8x10", "8x10"]
    """
    gc, sh, ws = open_athlete_sheet(athlete_name)
    sheet_id = ws.id

    # где писать
    exercise_row = find_exercise_row(ws, exercise_name)
    col = get_next_free_column(ws, exercise_row)

    # текст ячейки
    cell_text = "\n".join(lines)

    # делаем одной операцией текст + формат
    batch_update_cell_with_rich_text(
        sh=sh,
        sheet_id=sheet_id,
        row=exercise_row,
        col=col,
        text=cell_text
    )

    logging.info(f"Записал тренировку для {athlete_name}: {exercise_name}")


# -----------------------------
# Старый формат с ";"
# -----------------------------
def add_workout(athlete_name, date_str, exercise_name, weight_str, sets, reps):
    weight_str = weight_str.strip()
    if weight_str in ("", "0", "-"):
        one = f"x{reps}"
    else:
        one = f"{weight_str}x{reps}"

    lines = [date_str] + [one] * sets
    add_workout_cell(athlete_name, exercise_name, lines)
