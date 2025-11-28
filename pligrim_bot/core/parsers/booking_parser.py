# pligrim_bot/core/booking_parser.py

import re
from typing import Optional, Dict, List


# --- Вспомогательные регулярки ---

# Удаляем WhatsApp-шапку вида:
# [6:22 PM, 11/27/2025] +7 708 013 2211:
WHATSAPP_PREFIX = re.compile(
    r"^\[\d{1,2}:\d{2}\s*[AP]M,\s*\d{1,2}/\d{1,2}/\d{4}\]\s+.+?:\s*",
    flags=re.MULTILINE
)


def clean_text(text: str) -> str:
    """Нормализуем текст, убираем WhatsApp-шапку и лишние пробелы."""
    text = WHATSAPP_PREFIX.sub("", text or "")
    text = text.replace("\u202a", "").replace("\u202c", "")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def split_cards(text: str) -> List[str]:
    """Разрезает большой текст на несколько карточек по «ФИО:»."""
    t = clean_text(text)
    parts = re.split(r"(?=ФИО\s*:)", t)
    return [p.strip() for p in parts if "ФИО" in p]


def find(pattern: str, text: str) -> Optional[str]:
    m = re.search(pattern, text, flags=re.IGNORECASE)
    if not m:
        return None
    return m.group(m.lastindex or 1).strip()


def normalize_amount(raw: Optional[str]) -> Optional[str]:
    """Извлекает число из вида '1600$', '192 $/520.7 = 100 000 тг' → '1600' / '192.0'."""
    if not raw:
        return None
    m = re.search(r"([\d\s]+[.,]?\d*)\s*\$", raw)
    if not m:
        return None
    return m.group(1).replace(" ", "").replace(",", ".")


def normalize_room(text: Optional[str]) -> str:
    if not text:
        return ""
    t = text.upper()
    if "SNGL" in t or "SGL" in t:
        return "SNGL"
    if "DBL" in t:
        return "DBL"
    if "TRPL" in t:
        return "TRPL"
    if "QDR" in t or "QUAD" in t:
        return "QDR"
    return t


def normalize_meal(text: Optional[str]) -> str:
    if not text:
        return ""
    t = text.upper()
    if "HB" in t:
        return "HB"
    if "BB" in t:
        return "BB"
    if "FB" in t:
        return "FB"
    if "AI" in t:
        return "AI"
    return t


# --- ПАРСИНГ ОДНОЙ КАРТОЧКИ ---


def parse_single_card(text: str) -> Optional[Dict[str, str]]:
    """
    Разбирает ОДНУ карточку WhatsApp.
    Возвращает dict с унифицированными полями или None, если даже ФИО нет.
    """
    t = clean_text(text)

    fio = find(r"ФИО\s*:\s*(.+)", t)
    if not fio:
        return None

    departure_date = find(r"Дата(?: вылета)?\s*:\s*(.+)", t)
    package_name = find(r"Пакет название\s*:\s*(.+)", t)

    amount = find(r"Сумма\s*:\s*(.+)", t)
    paid_amount = find(r"[CС]умма оплаты\s*:\s*(.+)", t)

    placement = find(r"Размещение\s*:\s*(.+)", t)
    meal = find(r"Питание\s*:\s*(.+)", t)

    rate = find(r"Курс\s*\$?\s*:\s*(.+)", t)
    visa = find(r"Виза\s*:\s*(.+)", t)

    region = find(r"Регион\s*:\s*(.+)", t)
    departure_city = find(r"Вылет\s*:\s*(.+)", t)

    # Авиа / Авиа запрос
    avia = find(r"Авиа(?: запрос)?\s*:\s*(.*)", t)
    train = find(r"Поезд\s*:\s*(.*)", t)

    phone = find(r"(Контактные номера|Телефон|Номер)\s*:\s*(.+)", t)
    manager = find(r"Менеджер\s*:\s*(.+)", t)
    source = find(r"Источник\s*:\s*(.+)", t)

    contract = find(r"Договор\s*:\s*(.*)", t)
    contract_date = find(r"Дата договора\s*:\s*(.*)", t)

    comments = find(r"(Комментарии|Комментарий|Коммент)\s*:\s*([\s\S]*)", t)

    # ФИО → фамилия / имя
    parts = fio.split()
    last_name = parts[0] if parts else ""
    first_name = " ".join(parts[1:]) if len(parts) > 1 else ""

    return {
        "full_name": fio,
        "last_name": last_name,
        "first_name": first_name,

        "departure_date": departure_date or "",
        "package_name": package_name or "",

        "amount": amount or "",
        "amount_clean": normalize_amount(amount) or "",
        "paid_amount": paid_amount or "",
        "paid_amount_clean": normalize_amount(paid_amount) or "",

        "placement": placement or "",
        "placement_code": normalize_room(placement),

        "meal": meal or "",
        "meal_code": normalize_meal(meal),

        "rate": rate or "",
        "visa": visa or "",
        "region": region or "",
        "departure_city": departure_city or "",

        "avia": avia or "",
        "train": train or "",

        "phone": phone or "",
        "manager": manager or "",
        "source": source or "",

        "contract": contract or "",
        "contract_date": contract_date or "",

        "comments": (comments or "").strip(),
        "raw": text,
    }


def parse_booking_cards(text: str) -> List[Dict[str, str]]:
    """
    Разбирает ОДНО или НЕСКОЛЬКО бронирований в одном тексте.
    Возвращает список карточек.
    """
    cards = split_cards(text)
    result: List[Dict[str, str]] = []

    for card in cards:
        parsed = parse_single_card(card)
        if parsed:
            result.append(parsed)

    return result


import re
from typing import Dict

def parse_booking_card(text: str) -> Dict[str, str] | None:
    """
    Парсит карточку из WhatsApp в нормальный dict.
    Работает построчно, чтобы Авиа/Виза/Менеджер не смешивались.
    """

    if not text or not text.strip():
        return None

    t = text.strip()

    # Разбиваем на строки один раз
    lines = [line.strip() for line in t.splitlines() if line.strip()]

    def find_line(prefixes):
        """
        Ищет строку вида 'Префикс: значение' по указанным префиксам (список вариантов).
        Возвращает только ТЕКСТ после двоеточия.
        """
        if isinstance(prefixes, str):
            prefixes_list = [prefixes]
        else:
            prefixes_list = prefixes

        # Собираем регэксп типа: ^(ФИО|FIO)\s*[:\-–]\s*(.*)$
        pattern = r'^(?:' + "|".join(re.escape(p) for p in prefixes_list) + r')\s*[:\-–]\s*(.*)$'

        for line in lines:
            m = re.match(pattern, line, flags=re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return ""

    # --- ФИО ---
    full_name = find_line(["ФИО", "FIO", "Full name"])
    full_name = re.sub(r"\s+", " ", full_name).strip()

    last_name = ""
    first_name = ""
    if full_name:
        parts = full_name.split()
        if len(parts) >= 2:
            last_name = parts[0]
            first_name = " ".join(parts[1:])
        else:
            last_name = full_name

    # --- Пакет, суммы и т.д. ---
    package_name = find_line(["Пакет название", "Пакет", "Package"])
    amount_raw = find_line(["Сумма"])
    paid_raw = find_line(["Cумма оплаты", "Сумма оплаты", "Оплата"])
    placement = find_line(["Размещение"])
    meal = find_line(["Питание"])
    course = find_line(["Курс$", "Курс $", "Курс"])
    visa = find_line(["Виза", "Visa"])
    region = find_line(["Регион"])
    departure_city = find_line(["Вылет"])
    manager = find_line(["Менеджер", "Manager"])
    phone = find_line(["Телефон", "Номер", "Контактные номера"])
    train = find_line(["Поезд", "Train"])
    avia = find_line(["Авиа", "Авиа запрос", "Avia"])

    # --- Комментарий: всё после строки 'Комментарии:' ---
    comments = ""
    for idx, line in enumerate(lines):
        if re.match(r"^Комментарии\s*[:\-–]?\s*$", line, flags=re.IGNORECASE):
            tail = lines[idx + 1:]
            comments = "\n".join(tail).strip()
            break

    # --- Чистая сумма (цифры из '1950$' и т.п.) ---
    def extract_amount(num_text: str) -> str:
        if not num_text:
            return ""
        m = re.search(r"(\d+[.,]?\d*)", num_text)
        return m.group(1).replace(",", ".") if m else ""

    amount_clean = extract_amount(amount_raw)
    paid_amount_clean = extract_amount(paid_raw)

    booking = {
        "raw": text,

        "full_name": full_name,
        "last_name": last_name,
        "first_name": first_name,

        "package_name": package_name,

        "amount": amount_raw,
        "amount_clean": amount_clean,

        "paid_raw": paid_raw,
        "paid_amount": paid_amount_clean,

        "placement": placement,
        "meal": meal,
        "course": course,
        "visa": visa,
        "region": region,
        "departure_city": departure_city,
        "manager": manager,
        "phone": phone,
        "train": train,
        "comments": comments,
        "avia": avia,
    }

    return booking



# --- ПОДГОТОВКА ДАННЫХ ДЛЯ ЛИСТА ПАЛОМНИКОВ ---


def build_sheet_row_payload(booking: Dict[str, str], *, index: int | None = None) -> Dict[str, str]:
    avia = (booking.get("avia") or "").strip()
    visa = (booking.get("visa") or "").strip()
    price = booking.get("amount_clean") or booking.get("amount") or ""
    gender = (booking.get("gender") or "").strip().upper()  # "M" / "F"

    payload = {
        "№": str(index) if index is not None else "",
        "Avia": avia,
        "Visa": visa,
        "Type of room": booking.get("placement_code") or booking.get("placement") or "",
        "Meal a day": booking.get("meal_code") or booking.get("meal") or "",
        "Last Name": booking.get("last_name") or "",
        "First Name": booking.get("first_name") or "",
        "Gender": gender,               # <- вот тут
        "Date of Birth": "",
        "Document Number": "",
        "Document Issue date": "",
        "Document  Expiration": "",
        "Comment": booking.get("comments") or "",
        "Price": price,
        "Manager": booking.get("manager") or "",
        "Train": booking.get("train") or "",
    }

    return payload




