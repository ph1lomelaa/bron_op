import logging
import sys
import os
import asyncio

# Текущая директория = папка с main.py (pligrim_bot)
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

try:
    from pligrim_bot.config.settings import get_google_client, refresh_sheets
    from pligrim_bot.config.constants import bot, dp

    # Подключаем оба роутера
    from pligrim_bot.handlers.palm_booking_flow import router as booking_router
    from pligrim_bot.handlers.edit_handlers import router as edit_router

    print("✅ Все модули успешно импортированы")
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    sys.exit(1)


async def main():
    print("✅ Бот запускается…")
    await bot.delete_webhook(drop_pending_updates=True)

    # Регистрируем роутеры
    dp.include_router(booking_router)
    dp.include_router(edit_router)

    # Временные папки (если нужны)
    os.makedirs("tmp", exist_ok=True)
    os.makedirs("assets/fonts", exist_ok=True)
    os.makedirs("assets/images", exist_ok=True)

    print("🚀 Polling started…")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 Бот остановлен.")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
