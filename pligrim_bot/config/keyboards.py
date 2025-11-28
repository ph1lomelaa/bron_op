# bot/handlers/palm_booking_flow.py
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

# Путь к настройкам и утилитам адаптируй под свой проект:
from pligrim_bot.config.settings import PALM_SHEETS
from pligrim_bot.core.builder.booking_builder import save_booking_to_sheet
from pligrim_bot.core.google_sheets import get_palm_sheet_names
from pligrim_bot.core.parsers.booking_parser import parse_booking_card
from pligrim_bot.core.utils.text_utils import safe_cb_text

logger = logging.getLogger(__name__)

router = Router()


# ===== FSM: один стейт – ждём карточку целиком =====

class BookingStates(StatesGroup):
    waiting_for_card_text = State()


# ===== КЛАВИАТУРЫ =====

def start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Начать бронирование",
                    callback_data="start_flow",
                )
            ]
        ]
    )


def get_palm_month_buttons() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=month_key,
                callback_data=f"palm_month:{month_key}",
            )
        ]
        for month_key in PALM_SHEETS.keys()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_palm_sheet_buttons(month_key: str, show_all: bool = False) -> InlineKeyboardMarkup:
    """
    Кнопки листов для выбранного месяца.
    """
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
            rows.append(
                [
                    InlineKeyboardButton(
                        text="📋 Показать все",
                        callback_data=f"palm_show_all:{month_key}",
                    )
                ]
            )

        rows.append(
            [
                InlineKeyboardButton(
                    text="🔙 Назад к месяцам",
                    callback_data="palm_back_to_months",
                )
            ]
        )

        return InlineKeyboardMarkup(inline_keyboard=rows)

    except Exception as e:
        logger.exception(f"Ошибка в get_palm_sheet_buttons: {e}")
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔙 Назад к месяцам",
                        callback_data="palm_back_to_months",
                    )
                ]
            ]
        )


def build_palm_packages_kb(month_key: str, ws_title: str, packages: List[Dict]) -> InlineKeyboardMarkup:
    """
    Кнопки по пакетам в выбранном листе.
    packages = [{"title": "...", "row": 15}, ...]
    """
    rows: List[List[InlineKeyboardButton]] = []
    for p in packages:
        rows.append(
            [
                InlineKeyboardButton(
                    text=p["title"],
                    callback_data=f"palm_pkg:{month_key}:{ws_title}:{p['row']}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="🔙 Назад к листам",
                callback_data=f"palm_back_to_sheets:{month_key}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ===== ЗАГЛУШКА ДЛЯ ПАКЕТОВ (потом подружим с package_parser) =====

async def load_packages_for_sheet(month_key: str, ws_title: str) -> List[Dict]:
    """
    TODO: здесь потом подружим с package_parser/google_sheets.
    Пока – заглушка, чтобы протестировать поток.
    """
    logger.warning("load_packages_for_sheet: пока заглушка, вернись сюда позже")
    return [
        {"title": "Пример пакета 1", "row": 10},
        {"title": "Пример пакета 2", "row": 30},
    ]


# ===== ХЭНДЛЕРЫ: /start → месяц → лист → пакет =====

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я бот для оформления бронирований паломников 🕋\n\n"
        "Нажми «Начать бронирование», чтобы выбрать месяц, вылет и пакет.",
        reply_markup=start_keyboard(),
    )


@router.callback_query(F.data == "start_flow")
async def cb_start_flow(callback: CallbackQuery):
    await callback.message.edit_text(
        "Выберите месяц вылета:",
        reply_markup=get_palm_month_buttons(),
    )
    await callback.answer()


@router.callback_query(F.data == "palm_back_to_months")
async def cb_back_to_months(callback: CallbackQuery):
    await callback.message.edit_text(
        "Выберите месяц вылета:",
        reply_markup=get_palm_month_buttons(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("palm_month:"))
async def cb_palm_month(callback: CallbackQuery):
    month_key = callback.data.split(":", 1)[1]
    kb = get_palm_sheet_buttons(month_key, show_all=False)
    await callback.message.edit_text(
        f"Месяц: {month_key}\n\nТеперь выберите вылет / лист:",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("palm_show_all:"))
async def cb_palm_show_all(callback: CallbackQuery):
    month_key = callback.data.split(":", 1)[1]
    kb = get_palm_sheet_buttons(month_key, show_all=True)
    await callback.message.edit_text(
        f"Месяц: {month_key}\n\nВсе доступные листы:",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("palm_sheet:"))
async def cb_palm_sheet(callback: CallbackQuery):
    parts = callback.data.split(":", 2)
    if len(parts) < 3:
        await callback.answer("Ошибка данных листа", show_alert=True)
        return

    _, month_key, ws_title = parts
    packages = await load_packages_for_sheet(month_key, ws_title)
    if not packages:
        await callback.answer("На этом листе нет пакетов", show_alert=True)
        return

    kb = build_palm_packages_kb(month_key, ws_title, packages)
    await callback.message.edit_text(
        f"Месяц: {month_key}\nЛист: {ws_title}\n\nВыберите пакет:",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("palm_back_to_sheets:"))
async def cb_back_to_sheets(callback: CallbackQuery):
    month_key = callback.data.split(":", 1)[1]
    kb = get_palm_sheet_buttons(month_key, show_all=False)
    await callback.message.edit_text(
        f"Месяц: {month_key}\n\nВыберите вылет / лист:",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("palm_pkg:"))
async def cb_palm_package(callback: CallbackQuery, state: FSMContext):
    _, month_key, ws_title, row_str = callback.data.split(":", 3)
    pkg_row = int(row_str)

    # Ещё раз грузим пакеты и находим выбранный по row
    packages = await load_packages_for_sheet(month_key, ws_title)
    pkg_title = None
    for p in packages:
        try:
            if int(p["row"]) == pkg_row:
                pkg_title = p["title"]
                break
        except Exception:
            continue

    await state.update_data(
        month_key=month_key,
        ws_title=ws_title,
        pkg_row=pkg_row,
        pkg_title=pkg_title,  # <- сюда кладём имя пакета с кнопки
    )

    await callback.message.edit_text(
        "Пакет выбран ✅\n\nТеперь отправьте *карточку клиента из WhatsApp*.\n"
        "Я автоматически её разберу.",
        parse_mode="Markdown",
    )
    await state.set_state(BookingStates.waiting_for_card_text)
    await callback.answer()



# ===== ХЭНДЛЕР: принимаем карточку, парсим, показываем разбор =====

@router.message(BookingStates.waiting_for_card_text)
async def process_card_text(message: Message, state: FSMContext):
    data = await state.get_data()
    raw_text = message.text or ""

    booking = parse_booking_card(raw_text)

    if not booking:
        await message.answer(
            "Не смогла разобрать карточку 😔\n"
            "Проверь, пожалуйста, чтобы в тексте были строки типа:\n"
            "ФИО: ..., Дата вылета: ..., Пакет название: ..., Размещение: ..."
        )
        return

    # 1️⃣ Сохраняем в таблицу (пока просто в конец листа)
    try:
        save_booking_to_sheet(
            month_key=data.get("month_key"),
            ws_title=data.get("ws_title"),
            booking=booking,
        )
        saved_msg = "✅ Бронь сохранена в таблицу."
    except Exception as e:
        saved_msg = f"⚠️ Не получилось сохранить бронь в таблицу: {e}"

    # 2️⃣ Показываем пользователю, что именно распарсили
    summary_lines = [
        f"Месяц: {data.get('month_key')}",
        f"Лист: {data.get('ws_title')}",
        "",
        f"ФИО: {booking.get('full_name')}",
        f"Фамилия: {booking.get('last_name')}",
        f"Имя: {booking.get('first_name')}",
        f"Дата вылета: {booking.get('departure_date')}",
        f"Пакет: {booking.get('package_name')}",
        f"Сумма: {booking.get('amount')} (чисто: {booking.get('amount_clean')})",
        f"Оплата: {booking.get('paid_amount')} (чисто: {booking.get('paid_amount_clean')})",
        f"Размещение: {booking.get('placement')} → код: {booking.get('placement_code')}",
        f"Питание: {booking.get('meal')} → код: {booking.get('meal_code')}",
        f"Курс$: {booking.get('rate')}",
        f"Виза: {booking.get('visa')}",
        f"Регион: {booking.get('region')}",
        f"Вылет: {booking.get('departure_city')}",
        f"Менеджер: {booking.get('manager')}",
        f"Телефон: {booking.get('phone')}",
        "",
        "Комментарии:",
        booking.get('comments') or "—",
        "",
        saved_msg,
        ]

    await message.answer("Я распознала карточку так:\n\n" + "\n".join(summary_lines))
    await state.clear()

