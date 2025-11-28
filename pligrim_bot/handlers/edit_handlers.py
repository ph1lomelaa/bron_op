# pligrim_bot/handlers/edit_handlers.py

import logging
from typing import Dict

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from pligrim_bot.handlers.palm_booking_flow import (
    BookingStates,
    booking_preview_kb,
    render_booking_preview_text
)

logger = logging.getLogger(__name__)

router = Router()


class EditBookingStates(StatesGroup):
    waiting_field_choice = State()
    waiting_new_value = State()


# Какие поля можно править в превью
EDITABLE_FIELDS: Dict[str, str] = {
    "Type of room": "Тип комнаты",
    "Meal a day": "Питание",
    "Avia/Visa": "Avia/Visa",
    "Train": "Поезд",
    "Price": "Цена",
    "Comment": "Комментарий",
    "Manager": "Менеджер",
}

@router.callback_query(F.data == "booking_back_to_preview")
async def on_booking_back_to_preview(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text = render_booking_preview_text(data)

    await callback.message.answer(
        text,
        reply_markup=booking_preview_kb(),
    )
    await state.set_state(BookingStates.review)
    await callback.answer()



def edit_fields_kb(current_payload: Dict[str, str]) -> InlineKeyboardMarkup:
    rows = []
    for key, label in EDITABLE_FIELDS.items():
        # Если Train пустой, всё равно даём возможность добавить
        rows.append([
            InlineKeyboardButton(
                text=f"{label}: {current_payload.get(key) or '—'}",
                callback_data=f"edit_field:{key}",
            )
        ])

    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="booking_back_to_preview")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def save_mode_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🧩 Произвольное расположение",
                    callback_data="booking_save_free",
                )
            ],
            [
                InlineKeyboardButton(
                    text="👥 С определённым человеком",
                    callback_data="booking_save_with_person",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="booking_cancel",
                )
            ],
        ]
    )


# ====== КНОПКА ✏️ ИЗМЕНИТЬ ======

@router.callback_query(F.data == "booking_edit")
async def on_booking_edit(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    sheet_payload = data.get("sheet_payload") or {}

    await state.set_state(EditBookingStates.waiting_field_choice)

    await callback.message.answer(
        "Что хотите изменить?",
        reply_markup=edit_fields_kb(sheet_payload),
    )
    await callback.answer()


@router.callback_query(EditBookingStates.waiting_field_choice, F.data.startswith("edit_field:"))
async def on_edit_field_choose(callback: CallbackQuery, state: FSMContext):
    _, field_key = callback.data.split(":", 1)
    await state.update_data(edit_field=field_key)

    human_label = EDITABLE_FIELDS.get(field_key, field_key)
    await state.set_state(EditBookingStates.waiting_new_value)

    await callback.message.answer(
        f"Введите новое значение для поля «{human_label}»:"
    )
    await callback.answer()


@router.message(EditBookingStates.waiting_new_value)
async def on_edit_new_value(message: Message, state: FSMContext):
    data = await state.get_data()
    field_key = data.get("edit_field")
    sheet_payload = data.get("sheet_payload") or {}
    booking = data.get("booking") or {}

    new_value = (message.text or "").strip()

    if not field_key or field_key not in EDITABLE_FIELDS:
        await message.answer("Не поняла, какое поле нужно менять. Попробуйте ещё раз через кнопку «Изменить».")
        await state.set_state(BookingStates.review)
        return

    # Обновляем payload
    sheet_payload[field_key] = new_value

    # Немного синхронизируем booking для некоторых полей
    if field_key == "Type of room":
        booking["placement"] = new_value
        booking["placement_code"] = new_value
    elif field_key == "Meal a day":
        booking["meal"] = new_value
        booking["meal_code"] = new_value
    elif field_key == "Price":
        booking["amount"] = new_value
        booking["amount_clean"] = new_value
    elif field_key == "Comment":
        booking["comments"] = new_value
    elif field_key == "Manager":
        booking["manager"] = new_value
    elif field_key == "Avia/Visa":
        # здесь можем просто оставить в payload (в карточке поля такого нет)
        pass
    elif field_key == "Train":
        booking["train"] = new_value

    await state.update_data(
        sheet_payload=sheet_payload,
        booking=booking,
        edit_field=None,
    )

    # Покажем обновлённое превью (упрощённое)
    train_line = ""
    if sheet_payload.get("Train"):
        train_line = f"▪️ Train: {sheet_payload['Train']}\n"

    await state.update_data(
        sheet_payload=sheet_payload,
        booking=booking,
        edit_field=None,
    )

    new_state = await state.get_data()
    preview_text = render_booking_preview_text(new_state)

    await message.answer(
        preview_text,
        reply_markup=booking_preview_kb(),
    )

    await state.set_state(BookingStates.review)




# ====== КНОПКА ЗАПИСАТЬ → ВЫБОР СПОСОБА РАЗМЕЩЕНИЯ ======

@router.callback_query(F.data == "booking_save")
async def on_booking_save(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Как записать этого паломника в таблицу?",
        reply_markup=save_mode_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "booking_save_free")
async def on_booking_save_free(callback: CallbackQuery, state: FSMContext):
    # Здесь потом будет логика реальной записи в таблицу (произвольное расположение)
    data = await state.get_data()
    sheet_payload = data.get("sheet_payload") or {}

    # Пока просто показываем, что бы записали
    debug = "\n".join(f"{k}: {v}" for k, v in sheet_payload.items())
    await callback.message.answer(
        "Пока что я только показываю, что будет записано (произвольное расположение):\n\n"
        f"{debug}"
    )
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "booking_save_with_person")
async def on_booking_save_with_person(callback: CallbackQuery, state: FSMContext):
    # Здесь потом будет логика выбора конкретного человека/комнаты
    await callback.message.answer(
        "Режим «с определённым человеком» пока не реализован. "
        "Здесь будет выбор комнаты / соседа."
    )
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "booking_cancel")
async def on_booking_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("Ок, бронирование отменено.")
    await callback.answer()
