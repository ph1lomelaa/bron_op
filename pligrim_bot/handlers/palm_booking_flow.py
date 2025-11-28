# pligrim_bot/handlers/palm_booking_flow.py
# Логика: /start → месяц → лист → пакет → ждём карточку → показываем разбор.

import logging
from typing import List, Dict

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from pligrim_bot.config.settings import get_worksheet
from pligrim_bot.core.room_allocator import find_free_slot_auto, build_row_values_from_payload

from pligrim_bot.config.settings import PALM_SHEETS
from pligrim_bot.core.google_sheets import get_palm_sheet_names
from pligrim_bot.core.parsers.booking_parser import (
    parse_booking_card,
    build_sheet_row_payload,
)
from pligrim_bot.core.utils.text_utils import safe_cb_text


logger = logging.getLogger(__name__)

router = Router()


# ========= FSM: один стейт — ждём карточку ========
class BookingStates(StatesGroup):
    choosing_gender = State()          # <- новый
    waiting_for_card_text = State()
    review = State()
    editing_field = State()
    waiting_new_value = State()

# ======= КЛАВИАТУРЫ =========

def start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Начать бронирование", callback_data="start_flow")]
        ]
    )


def get_palm_month_buttons() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=month_key, callback_data=f"palm_month:{month_key}")]
        for month_key in PALM_SHEETS.keys()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_palm_sheet_buttons(month_key: str, show_all: bool = False) -> InlineKeyboardMarkup:
    try:
        names: List[str] = get_palm_sheet_names(month_key, include_past=False)

        if not names:
            names = ["— нет актуальных листов —"]

        if not show_all and len(names) > 8:
            display = names[:8]
            has_more = True
        else:
            display = names
            has_more = False

        rows: List[List[InlineKeyboardButton]] = []
        for n in display:
            txt = n[:30] + "..." if len(n) > 30 else n
            cb = f"palm_sheet:{safe_cb_text(month_key)}:{safe_cb_text(n)}"
            rows.append([InlineKeyboardButton(text=txt, callback_data=cb)])

        if has_more:
            rows.append([InlineKeyboardButton(text="📋 Показать все", callback_data=f"palm_show_all:{month_key}")])

        rows.append([InlineKeyboardButton(text="🔙 Назад к месяцам", callback_data="palm_back_to_months")])

        return InlineKeyboardMarkup(inline_keyboard=rows)

    except Exception as e:
        logger.exception(f"Ошибка в get_palm_sheet_buttons: {e}")
        return InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="palm_back_to_months")]]
        )

def gender_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👨 M", callback_data="gender:M"),
                InlineKeyboardButton(text="👩 F", callback_data="gender:F"),
            ]
        ]
    )


def build_palm_packages_kb(month_key: str, ws_title: str, packages: List[Dict]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=p["title"],
            callback_data=f"palm_pkg:{month_key}:{ws_title}:{p['row']}"
        )]
        for p in packages
    ]
    rows.append([InlineKeyboardButton(text="🔙 Назад к листам", callback_data=f"palm_back_to_sheets:{month_key}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ========= Заглушка: позже подружим с package_parser =========
from pligrim_bot.core.parsers.package_parser import find_palm_packages
from pligrim_bot.config.settings import get_worksheet

async def load_packages_for_sheet(month_key: str, ws_title: str) -> list[dict]:
    """
    Реальный поиск пакетов на листе паломников.
    Использует find_palm_packages() из package_parser.py.
    Возвращает список:
        [{"title": "...", "row": int}, ...]
    """
    try:
        # 1. Берём рабочий лист
        ws = get_worksheet(month_key, ws_title)
        if ws is None:
            print("❌ Не найден worksheet:", month_key, ws_title)
            return []

        # 2. Ищем пакеты
        packages_raw = find_palm_packages(ws)

        # 3. Переводим в формат, который нужен клавиатуре
        packages = [
            {
                "title": pkg["title"],
                "row": pkg["row"]
            }
            for pkg in packages_raw
        ]

        print(f"📦 Найдено пакетов: {len(packages)}")
        return packages

    except Exception as e:
        print(f"❌ Ошибка load_packages_for_sheet: {e}")
        return []

# ========= ХЭНДЛЕРЫ /start → месяц → лист → пакет =========

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я бот для оформления бронирований паломников 🕋\n\n"
        "Нажми «Начать бронирование».",
        reply_markup=start_keyboard(),
    )


@router.callback_query(F.data == "start_flow")
async def cb_start_flow(callback: CallbackQuery):
    await callback.message.edit_text("Выберите месяц:", reply_markup=get_palm_month_buttons())
    await callback.answer()


@router.callback_query(F.data == "palm_back_to_months")
async def cb_back_months(callback: CallbackQuery):
    await callback.message.edit_text("Выберите месяц:", reply_markup=get_palm_month_buttons())
    await callback.answer()


@router.callback_query(F.data.startswith("palm_month:"))
async def cb_palm_month(callback: CallbackQuery):
    month_key = callback.data.split(":", 1)[1]
    kb = get_palm_sheet_buttons(month_key)
    await callback.message.edit_text(f"Месяц: {month_key}\n\nВыберите вылет:", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("palm_show_all:"))
async def cb_show_all(callback: CallbackQuery):
    month_key = callback.data.split(":", 1)[1]
    kb = get_palm_sheet_buttons(month_key, show_all=True)
    await callback.message.edit_text(f"Месяц: {month_key}\n\nВсе листы:", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("palm_sheet:"))
async def cb_palm_sheet(callback: CallbackQuery):
    _, month_key, ws_title = callback.data.split(":", 2)
    packages = await load_packages_for_sheet(month_key, ws_title)

    kb = build_palm_packages_kb(month_key, ws_title, packages)
    await callback.message.edit_text(
        f"Месяц: {month_key}\n"
        f"Лист: {ws_title}\n\n"
        f"Выберите пакет:",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("palm_back_to_sheets:"))
async def cb_back_sheets(callback: CallbackQuery):
    month_key = callback.data.split(":", 1)[1]
    kb = get_palm_sheet_buttons(month_key)
    await callback.message.edit_text(f"Месяц: {month_key}\n\nВыберите вылет:", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("palm_pkg:"))
async def cb_palm_package(callback: CallbackQuery, state: FSMContext):
    # callback_data = "palm_pkg:{month_key}:{ws_title}:{row}"
    _, month_key, ws_title, row_str = callback.data.split(":", 3)
    pkg_row = int(row_str)

    # Подтягиваем название пакета по row
    packages = await load_packages_for_sheet(month_key, ws_title)
    pkg_title = None
    for p in packages:
        try:
            if int(p.get("row")) == pkg_row:
                pkg_title = p.get("title")
                break
        except Exception:
            continue

    print(f"🔎 Выбран пакет row={pkg_row}, title={pkg_title!r}")

    await state.update_data(
        month_key=month_key,
        ws_title=ws_title,
        pkg_row=pkg_row,
        pkg_title=pkg_title,
    )

    await callback.message.edit_text(
        "Пакет выбран ✅\n\nТеперь выберите пол паломника:",
        reply_markup=gender_keyboard(),
    )
    await state.set_state(BookingStates.choosing_gender)
    await callback.answer()

@router.callback_query(F.data.startswith("gender:"))
async def cb_choose_gender(callback: CallbackQuery, state: FSMContext):
    _, gender = callback.data.split(":", 1)   # "M" или "F"

    await state.update_data(gender=gender)

    text = "Пол выбран: M (мужчина)" if gender == "M" else "Пол выбран: F (женщина)"

    await callback.message.edit_text(
        text + "\n\nТеперь отправьте *карточку клиента из WhatsApp*.",
        parse_mode="Markdown",
        )
    await state.set_state(BookingStates.waiting_for_card_text)
    await callback.answer()


def render_booking_preview_text(state_data: dict) -> str:
    sheet_payload = state_data.get("sheet_payload") or {}
    booking = state_data.get("booking") or {}

    ws_title = state_data.get("ws_title") or "—"
    pkg_title = state_data.get("pkg_title") or booking.get("package_name") or "—"

    return (
        f"📄 Лист: {ws_title}\n"
        f"Пакет: {pkg_title}\n\n"
        f"▪️ Last Name: {sheet_payload.get('Last Name') or '—'}\n"
        f"▪️ First Name: {sheet_payload.get('First Name') or '—'}\n"
        f"▪️ Gender: {sheet_payload.get('Gender') or '—'}\n"
        f"▪️ Avia: {sheet_payload.get('Avia') or '—'}\n"
        f"▪️ Visa: {sheet_payload.get('Visa') or '—'}\n"
        f"▪️ Type of room: {sheet_payload.get('Type of room') or '—'}\n"
        f"▪️ Meal a day: {sheet_payload.get('Meal a day') or '—'}\n"
        f"▪️ Price: {sheet_payload.get('Price') or '—'}\n"
        f"▪️ Comment: {sheet_payload.get('Comment') or '—'}\n"
        f"▪️ Manager: {sheet_payload.get('Manager') or '—'}\n"
        f"▪️ Train: {sheet_payload.get('Train') or '—'}\n"
    )

# ========= ХЭНДЛЕР ПРИНЯТИЯ КАРТОЧКИ =========

@router.message(BookingStates.waiting_for_card_text)
async def process_card(message: Message, state: FSMContext):
    data = await state.get_data()
    text = message.text or ""

    booking = parse_booking_card(text)

    if not booking:
        await message.answer("Не могу разобрать карточку 😢\nПроверь формат.")
        return

    # Применяем выбранный пол из state
    gender = data.get("gender")
    if gender:
        booking["gender"] = gender

    sheet_payload = build_sheet_row_payload(booking)

    data.update(
        booking=booking,
        sheet_payload=sheet_payload,
    )
    await state.set_data(data)

    preview_text = render_booking_preview_text(data)
    await message.answer(preview_text, reply_markup=booking_preview_kb())
    await state.set_state(BookingStates.review)



def booking_preview_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Произвольное размещение",
                    callback_data="booking_place_auto"
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Изменить",
                    callback_data="booking_edit"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="booking_cancel"
                )
            ],
        ]
    )

@router.callback_query(F.data == "booking_place_auto")
async def on_booking_place_auto(callback: CallbackQuery, state: FSMContext):
    """
    Произвольное размещение:
    - ищем первую подходящую комнату нужного типа / пола,
    - записываем паломника в таблицу,
    - НЕ трогаем Type of room и Visa.
    """
    data = await state.get_data()

    month_key = data.get("month_key")
    ws_title = data.get("ws_title")
    pkg_row = data.get("pkg_row")
    payload = data.get("sheet_payload")

    if not (month_key and ws_title and isinstance(pkg_row, int) and payload):
        await callback.message.answer("Не хватает данных для размещения (месяц/лист/пакет).")
        await callback.answer()
        return

    ws = get_worksheet(month_key, ws_title)
    if not ws:
        await callback.message.answer("Не смог найти лист в таблице 😢")
        await callback.answer()
        return

    # ищем свободное место
    slot = find_free_slot_auto(ws, pkg_row, payload)
    if not slot:
        await callback.message.answer("Не нашёл свободную комнату подходящего типа/пола.")
        await callback.answer()
        return

    row_idx, cols = slot

    # Берём текущую строку как основу, чтобы сохранить Type of room / Visa
    base_row = ws.row_values(row_idx + 1)

    # Собираем итоговую строку, не перезаписывая Type of room и Visa
    row_values = build_row_values_from_payload(
        payload,
        cols,
        base_row=base_row,
    )

    # обновляем одну строку (A + индекс строки 1-based)
    ws.update(f"A{row_idx+1}", [row_values])

    await callback.message.answer(
        f"✅ Паломник размещён в строке {row_idx+1} листа «{ws_title}»."
    )

    await state.clear()
    await callback.answer()

