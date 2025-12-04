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
