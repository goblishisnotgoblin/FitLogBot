# google_sheets.py
import logging
from datetime import datetime, date

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
    _, _, ws = open_athlete_sheet(athlete_name)
    col_a = ws.col_values(1)
    return [v.strip() for v in col_a if v.strip()]


# -----------------------------
# Поиск строки упражнения / свободного столбца
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


# -----------------------------
# Форматирование: жирный курсив только даты (первая строка)
# -----------------------------
def batch_update_cell_with_rich_text(sh, sheet_id, row, col, text: str):
    """
    Один batchUpdate:
    — Записываем текст в ячейку
    — Делаем первую строку жирной курсивной
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
# Запись тренировки в одну ячейку
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


# -----------------------------
# Старый формат с ';'
# -----------------------------
def add_workout(athlete_name, date_str, exercise_name, weight_str, sets, reps):
    weight_str = weight_str.strip()
    if weight_str in ("", "0", "-"):
        one = f"x{reps}"
    else:
        one = f"{weight_str}x{reps}"

    lines = [date_str] + [one] * sets
    add_workout_cell(athlete_name, exercise_name, lines)


# -----------------------------
# Вспомогательное: парсинг даты без года
# -----------------------------
def parse_date_without_year(date_str: str) -> date | None:
    """
    Принимает строку вида '5.12' или '05.12', возвращает дату с годом.
    Логика:
    - год = текущий
    - если результат в будущем относительно сегодня -> год = текущий - 1
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
        # считем, что это дата прошлого года
        d = d.replace(year=today.year - 1)

    return d


# -----------------------------
# Получение самых старых упражнений
# -----------------------------
def get_oldest_exercises(athlete_name: str, limit: int):
    """
    Возвращает список из limit элементов вида:
        (exercise_name, lines)

    Где:
        exercise_name — название упражнения из столбца A
        lines — список строк из последней ячейки по этому упражнению
    """
    gc, sh, ws = open_athlete_sheet(athlete_name)
    spreadsheet_id = sh.id
    sheet_title = ws.title

    # Вытаскиваем все значения (матрица)
    all_values = ws.get_all_values()
    row_count = len(all_values)

    if row_count == 0:
        return []

    # Получаем цвета фона для колонки A, чтобы пропустить серые / цветные упражнения
    # includeGridData=true + диапазон A1:A{row_count}
    resp = gc.request(
        "get",
        f"spreadsheets/{spreadsheet_id}",
        params={
            "includeGridData": "true",
            "ranges": f"{sheet_title}!A1:A{row_count}",
            "fields": "sheets(data(rowData(values(userEnteredFormat.backgroundColor,userEnteredValue))))",
        },
    )

    row_formats = []
    try:
        row_data = resp["sheets"][0]["data"][0].get("rowData", [])
        for r in row_data:
            vals = r.get("values", [])
            if vals:
                fmt = vals[0].get("userEnteredFormat", {})
                bg = fmt.get("backgroundColor", {})
            else:
                bg = {}
            row_formats.append(bg)
    except Exception:
        logging.exception("Не удалось прочитать форматирование колонки A")
        row_formats = [{} for _ in range(row_count)]

    def is_colored(bg: dict) -> bool:
        """Считаем ячейку 'закрашенной', если цвет заметно отличается от белого."""
        if not bg:
            return False
        r = bg.get("red", 1)
        g = bg.get("green", 1)
        b = bg.get("blue", 1)
        # если хоть один канал < 0.95 — считаем, что ячейка цветная (например, серая)
        return (r < 0.95) or (g < 0.95) or (b < 0.95)

    items = []

    for idx in range(row_count):
        row = all_values[idx]
        exercise_name = (row[0].strip() if row else "")
        if not exercise_name:
            continue

        # пропускаем закрашенные упражнения
        bg = row_formats[idx] if idx < len(row_formats) else {}
        if is_colored(bg):
            continue

        # ищем последнюю непустую ячейку в строке (кроме A)
        last_text = ""
        for val in reversed(row[1:]):  # B..end
            if val.strip():
                last_text = val
                break

        if not last_text:
            continue  # по этому упражнению нет тренировок

        lines = [ln.strip() for ln in last_text.split("\n") if ln.strip()]
        if not lines:
            continue

        date_str = lines[0]
        d = parse_date_without_year(date_str)
        if not d:
            continue

        items.append(
            {
                "exercise": exercise_name,
                "date": d,
                "lines": lines,
            }
        )

    # Сортируем по дате по возрастанию (самые старые первыми)
    items.sort(key=lambda x: x["date"])

    # Берём только limit штук
    result = []
    for it in items[:limit]:
        result.append((it["exercise"], it["lines"]))

    return result
