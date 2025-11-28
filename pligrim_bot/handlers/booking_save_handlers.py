from aiogram import F
from aiogram.dispatcher import router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from pligrim_bot.core.room_allocator import find_free_slot_auto, build_row_values_from_payload
from pligrim_bot.config.settings import get_worksheet

@router.callback_query(F.data == "booking_place_auto")
async def on_booking_place_auto(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    month_key = data["month_key"]
    ws_title = data["ws_title"]
    pkg_row = data["pkg_row"]
    payload = data["sheet_payload"]

    ws = get_worksheet(month_key, ws_title)
    if not ws:
        await callback.message.answer("Не смог найти лист в таблице 😢")
        await callback.answer()
        return

    res = find_free_slot_auto(ws, pkg_row, payload)
    if not res:
        await callback.message.answer("Не нашёл свободное место подходящего типа/пола.")
        await callback.answer()
        return

    row_idx, cols = res
    row_values = build_row_values_from_payload(payload, cols)

    # Обновляем одну строку (row_idx 0-based -> +1 для Google Sheets)
    ws.update(f"A{row_idx+1}", [row_values])

    await callback.message.answer("✅ Паломник успешно размещён в комнате (произвольно).")
    await callback.answer()
