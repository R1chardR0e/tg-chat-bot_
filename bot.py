import asyncio
import signal
from collections.abc import Awaitable, Callable
from typing import Any, cast

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.types import Message, TelegramObject

from config import BOT_TOKEN
from database.db_crud import save_chat, save_message, save_user
from database.db_migration import init_db
from embeddings.vector_db import get_faiss_manager
from handlers import command_handler
from handlers.message_handler import router as responder_router
from utils.helpers import safe_convert_to_datetime, to_utc_string
from utils.logger import logger


class SaveMessageMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        message = cast(Message, event)

        try:
            await asyncio.to_thread(save_chat, message.chat)
            if message.from_user:
                await asyncio.to_thread(
                    save_user,
                    message.from_user,
                    to_utc_string(safe_convert_to_datetime(message.date)),
                )

            db_message_id = await asyncio.to_thread(save_message, message)
            if db_message_id:
                username = message.from_user.username if message.from_user else "неизвестно"
                logger.info(
                    "Сохранено сообщение %s от %s",
                    message.message_id,
                    username,
                )
                data["db_message_id"] = db_message_id
            else:
                logger.debug(f"Сообщение {message.message_id} уже существует")
        except Exception as error:
            logger.error(f"Ошибка при сохранении сообщения {message.message_id}: {error}")
        return await handler(event, data)


async def main():
    init_db()

    logger.info("Инициализация FAISS-индекса...")
    faiss_manager = get_faiss_manager()

    try:
        logger.info("Синхронизация FAISS-индекса с базой данных...")
        sync_success = faiss_manager.sync_with_database()
        if sync_success:
            logger.info("FAISS-индекс успешно синхронизирован")
        else:
            logger.warning("Синхронизация FAISS-индекса завершилась с замечаниями")
    except Exception as error:
        logger.error(f"Ошибка при синхронизации FAISS-индекса: {error}")

    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не задан. Проверьте переменные окружения.")
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.message.outer_middleware(SaveMessageMiddleware())

    dp.include_router(command_handler.router)
    dp.include_router(responder_router)

    logger.info("Бот успешно запущен.")

    def signal_handler():
        logger.info("Получен сигнал для завершения работы. Завершение работы...")
        asyncio.create_task(dp.stop_polling())

    signal.signal(signal.SIGINT, lambda s, f: signal_handler())
    signal.signal(signal.SIGTERM, lambda s, f: signal_handler())

    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем.")
    except Exception as error:
        logger.error(f"Ошибка при работе бота: {error}")
    finally:
        await bot.session.close()
        logger.info("Сессия бота закрыта. Программа завершена.")


if __name__ == "__main__":
    asyncio.run(main())
