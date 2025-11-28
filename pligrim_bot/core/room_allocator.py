# pligrim_bot/core/room_allocator.py

from typing import Dict, List, Tuple, Optional
import re

from pligrim_bot.core.parsers.package_parser import package_bounds

# какие типы комнат к какому размеру относятся


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


# Каноничные типы комнат и их синонимы
ROOM_CANON = {
    "quadro": ["quadro", "qvdr", "quad"],
    "triple": ["triple", "trpl"],
    "double": ["double", "dbl"],   # <= ВАЖНО: DBL и Double теперь одно и то же
    "single": ["single", "sngl"],
}

ROOM_SIZE = {
    "quadro": 4,
    "triple": 3,
    "double": 2,
    "single": 1,
}

def normalize_room_type(cell: str) -> Optional[str]:
    """
    Приводим значение типа комнаты к одному каноничному виду:
    - 'DBL', 'Double' → 'double'
    - 'TRPL', 'Triple' → 'triple'
    - 'QDR', 'Quadro', 'QVDR' → 'quadro'
    - 'SNGL', 'Single' → 'single'
    """
    t = _norm(cell)
    if not t:
        return None

    for canon, variants in ROOM_CANON.items():
        for v in variants:
            if v in t:
                return canon
    return None



def find_header_and_cols(data: List[List[str]], start: int, end: int) -> Tuple[int, Dict[str, int]]:
    """
    Ищем строку с заголовком и индексы нужных колонок:
    Type of room / Last Name / First Name / Gender / Price / Comment / Manager / Train
    """
    header_row = -1
    cols: Dict[str, int] = {}

    # ищем заголовок недалеко от начала пакета
    for r in range(start, min(end, start + 15)):
        row = data[r]
        joined = " ".join(_norm(x) for x in row)
        if "type of room" in joined and "last name" in joined:
            header_row = r
            break

    if header_row == -1:
        raise RuntimeError("Не нашли строку заголовка (Type of room / Last Name)")

    header = [_norm(x) for x in data[header_row]]

    def find_col(name_variants: List[str]) -> Optional[int]:
        for i, cell in enumerate(header):
            for v in name_variants:
                if v in cell:
                    return i
        return None

    cols["№"] = find_col(["№", "no"])
    cols["Visa"] = find_col(["visa"])
    cols["Avia"] = find_col(["avia"])
    cols["Type of room"] = find_col(["type of room"])
    cols["Meal a day"] = find_col(["meal a day"])
    cols["Last Name"] = find_col(["last name"])
    cols["First Name"] = find_col(["first name"])
    cols["Gender"] = find_col(["gender"])
    cols["Date of Birth"] = find_col(["date of birth"])
    cols["Document Number"] = find_col(["document number"])
    cols["Document Expiration"] = find_col(["document expiration"])
    cols["Price"] = find_col(["price"])
    cols["Comment"] = find_col(["comment"])
    cols["Manager"] = find_col(["manager"])
    cols["Train"] = find_col(["train"])

    return header_row, cols


def find_free_slot_auto(ws, pkg_row: int, payload: Dict[str, str]) -> Optional[Tuple[int, Dict[str, int]]]:
    """
    НАЙТИ СВОБОДНОЕ МЕСТО ДЛЯ ПАЛОМНИКА ВНУТРИ ПАКЕТА (произвольное размещение)
    Возвращает:
        (row_index, cols_dict) — row_index это индекс строки (0-based) в get_all_values()
    Если места нет → None
    """
    data = ws.get_all_values()
    r0, r1, all_pk = package_bounds(ws, pkg_row)

    room_type = (payload.get("Type of room") or "").strip()
    gender = (payload.get("Gender") or "").strip().upper()   # "M" / "F"

    if not room_type:
        return None

    header_row, cols = find_header_and_cols(data, r0, r1)
    type_col = cols["Type of room"]
    last_col = cols["Last Name"]
    gender_col = cols["Gender"]

    if type_col is None or last_col is None or gender_col is None:
        raise RuntimeError("Не нашли нужные колонки (Type of room / Last Name / Gender)")

    want_norm = normalize_room_type(room_type)
    if not want_norm:
        return None

    r = header_row + 1

    while r < r1:
        row = data[r]
        cell_type = row[type_col] if type_col < len(row) else ""
        rt_norm = normalize_room_type(cell_type)

        if not rt_norm:
            r += 1
            continue

        room_size = ROOM_SIZE[rt_norm]

        # если тип комнаты не наш, пропускаем весь блок этой комнаты
        if rt_norm != want_norm:
            r += room_size
            continue

        room_rows = list(range(r, min(r + room_size, r1)))

        # смотрим, кто уже живёт в комнате
        existing_genders = set()
        for rr in room_rows:
            row_rr = data[rr]
            ln = row_rr[last_col] if last_col < len(row_rr) else ""
            gd = row_rr[gender_col] if gender_col < len(row_rr) else ""
            if ln.strip():
                if gd.strip():
                    existing_genders.add(gd.strip().upper())

        # если в комнате уже стоит пол, а наш другой – не берём эту комнату
        if existing_genders:
            if gender and existing_genders != {gender}:
                r += room_size
                continue

        # ищем свободное место (пустой Last Name)
        for rr in room_rows:
            row_rr = data[rr]
            ln = row_rr[last_col] if last_col < len(row_rr) else ""
            if not str(ln).strip():
                return rr, cols

        r += room_size

    return None


def build_row_values_from_payload(
        payload: Dict[str, str],
        cols: Dict[str, int],
        base_row: Optional[List[str]] = None,
) -> List[str]:
    """
    Собирает список значений для одной строки по payload и маппингу колонок.

    ВАЖНО:
    - если передан base_row, мы берём её за основу и ЗАТЕМ
      перезаписываем только нужные поля.
    - колонку "Type of room" НЕ трогаем
    - колонку "Visa" ТОЖЕ НЕ трогаем (ориентируемся, но не меняем).
    """
    if base_row is None:
        base_row = []

    max_idx = max(i for i in cols.values() if i is not None)

    # Берём существующую строку и расширяем её до нужной длины
    row = list(base_row)
    if len(row) < max_idx + 1:
        row += [""] * (max_idx + 1 - len(row))

    mapping = {
        "№": "№",
        "Visa": "Visa",
        "Avia": "Avia",
        "Type of room": "Type of room",
        "Meal a day": "Meal a day",
        "Last Name": "Last Name",
        "First Name": "First Name",
        "Gender": "Gender",
        "Date of Birth": "Date of Birth",
        "Document Number": "Document Number",
        "Document Expiration": "Document  Expiration",
        "Price": "Price",
        "Comment": "Comment",
        "Manager": "Manager",
        "Train": "Train",
    }

    for col_name, key in mapping.items():
        idx = cols.get(col_name)
        if idx is None:
            continue

        # 🔒 НЕ трогаем Type of room — остаётся из таблицы
        if col_name == "Type of room":
            continue

        # 🔒 НЕ трогаем Visa — как в таблице
        if col_name == "Visa":
            continue

        # Перезаписываем остальные поля
        row[idx] = payload.get(key, row[idx] or "")

    return row

