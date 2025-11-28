# pligrim_bot/core/booking_builder.py
# Берём распарсенный booking и сохраняем его в Google Sheets.

from __future__ import annotations

from typing import Dict, List
from datetime import datetime

from pligrim_bot.config.settings import get_worksheet


# Порядок колонок в тестовой таблице
BOOKING_COLUMNS: List[str] = [
    "Timestamp",
    "Full name",
    "Last name",
    "First name",
    "Departure date",
    "Package name",
    "Amount (raw)",
    "Amount (clean)",
    "Paid amount (raw)",
    "Paid amount (clean)",
    "Placement",
    "Placement code",
    "Meal",
    "Meal code",
    "Rate",
    "Visa",
    "Region",
    "Departure city",
    "Manager",
    "Phone",
    "Source",
    "Contract",
    "Contract date",
    "Comments",
]


def build_booking_row(booking: Dict[str, str]) -> List[str]:
    """Собираем одну строку для записи в таблицу."""
    ts = datetime.now().strftime("%d.%m.%Y %H:%M")

    return [
        ts,
        booking.get("full_name", ""),
        booking.get("last_name", ""),
        booking.get("first_name", ""),
        booking.get("departure_date", ""),
        booking.get("package_name", ""),
        booking.get("amount", ""),
        booking.get("amount_clean", ""),
        booking.get("paid_amount", ""),
        booking.get("paid_amount_clean", ""),
        booking.get("placement", ""),
        booking.get("placement_code", ""),
        booking.get("meal", ""),
        booking.get("meal_code", ""),
        booking.get("rate", ""),
        booking.get("visa", ""),
        booking.get("region", ""),
        booking.get("departure_city", ""),
        booking.get("manager", ""),
        booking.get("phone", ""),
        booking.get("source", ""),
        booking.get("contract", ""),
        booking.get("contract_date", ""),
        (booking.get("comments") or "").strip(),
    ]


def ensure_header(ws) -> None:
    """Если лист пустой – ставим заголовки колонок."""
    first_row = ws.row_values(1)
    if not first_row:
        ws.insert_row(BOOKING_COLUMNS, 1)


def save_booking_to_sheet(month_key: str, ws_title: str, booking: Dict[str, str]) -> None:
    """
    Пишем бронь в ЛИСТ.
    Сейчас — просто в конец листа.
    Позже можно будет усложнить и класть её сразу в блок нужного пакета.
    """
    ws = get_worksheet(month_key, ws_title)
    if ws is None:
        raise RuntimeError(f"Не найден лист для month_key={month_key}, ws_title={ws_title}")

    ensure_header(ws)
    row = build_booking_row(booking)

    # пишем в конец таблицы
    ws.append_row(row, value_input_option="USER_ENTERED")
