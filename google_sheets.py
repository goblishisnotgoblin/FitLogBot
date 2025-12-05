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


# -----------------------------
# Работа с таблицами / списками
# -----------------------------
def open_athlete_sheet(athlete_name: str):
    """
    Открывает Spreadsheet и первый лист (sheet1) для указанного спортсмена.
    Возвращает (gc, spreadsheet, worksheet).
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
        ws = sh.sheet1
        return gc, sh, ws
    except Exception as e:
        logging.exception("Не удалось открыть таблицу по ID")
        raise RuntimeError(
            f"Не удалось открыть таблицу для '{athlete_name}'. "
            f"Проверь, что ID верный и файл расшарен на сервисный аккаунт."
        ) from e


def get_athletes() -> list[str]:
    """
    Возвращает список имён атлетов (ключи ATHLETE_SHEETS).
    """
    return list(ATHLETE_SHEETS.keys())


def get_exercises(athlete_name: str) -> list[str]:
    """
    Возвращает список упражнений из столбца A (непустые строки).
    """
    _, _, ws = open_athlete_sheet(athlete_name)
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
# Форматирование первой строки (даты) жирным курсивом
# -----------------------------
def format_first_line_bold_italic(
    gc,
    spreadsheet_id: str,
    sheet_id: int,
    row: int,
    col: int,
    text: str,
):
    """
    Делает первую строку в ячейке жирным курсивом.
    text — полный текст ячейки.
    """
    first_line_length = text.find("\n")
    if first_line_length == -1:
        first_line_length = len(text)

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
                                            "format": {
                                                "bold": True,
                                                "italic": True,
                                            },
                                        },
                                        {
                                            "startIndex": first_line_length,
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

    # gspread.Client.request использует относительные пути к API
    gc.request(
        "post",
        f"spreadsheets/{spreadsheet_id}:batchUpdate",
        json=body,
    )


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
    lines[0] = дата (потом форматируется жирным курсивом)
    остальные = подходы (вес x повторы и т.п.).
    """
    gc, sh, ws = open_athlete_sheet(athlete_name)
    spreadsheet_id = sh.id
    sheet_id = ws.id

    # 1. Находим строку упражнения и свободный столбец
    exercise_row = find_exercise_row(ws, exercise_name)
    col = get_next_free_column(ws, exercise_row)

    # 2. Собираем текст в ячейку
    cell_value = "\n".join(lines)

    # 3. Записываем текст
    ws.update_cell(exercise_row, col, cell_value)

    # 4. Форматируем первую строку (дату) как жирный курсив
    try:
        format_first_line_bold_italic(
            gc=gc,
            spreadsheet_id=spreadsheet_id,
            sheet_id=sheet_id,
            row=exercise_row,
            col=col,
            text=cell_value,
        )
    except Exception:
        # Если форматирование не удалось, не ломаем работу бота
        logging.exception("Не удалось применить форматирование к ячейке")

    logging.info(
        f"Записал тренировку (форматированно): {athlete_name}, {exercise_name}, "
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
