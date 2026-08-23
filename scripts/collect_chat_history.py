import asyncio
import os
import signal
import sys
import threading

# Pyrogram ожидает активный цикл событий до загрузки остальных модулей в Python 3.14.
asyncio.set_event_loop(asyncio.new_event_loop())

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from pyrogram.client import Client  # noqa: E402

from config import API_HASH, API_ID, CHAT_IDS  # noqa: E402
from database.db_crud import save_message  # noqa: E402
from database.db_migration import init_db  # noqa: E402
from utils.helpers import safe_convert_to_datetime, to_user_timezone  # noqa: E402
from utils.logger import logger  # noqa: E402

SESSION_NAME = "my_session"
BATCH_SIZE = 1000
MAX_MESSAGES = 50_000

_stop_event = threading.Event()


async def collect_history():
    """Загрузить историю разрешённых чатов через Pyrogram."""
    _stop_event.clear()

    if not CHAT_IDS:
        logger.error("CHAT_ID не указан")
        return

    if API_ID is None or API_HASH is None:
        logger.error("API_ID или API_HASH не заданы. Проверьте файл .env")
        return

    loop = asyncio.get_event_loop()

    try:
        loop.add_signal_handler(signal.SIGINT, _stop_event.set)
        loop.add_signal_handler(signal.SIGTERM, _stop_event.set)
    except NotImplementedError:
        pass

    app = Client(
        SESSION_NAME,
        api_id=API_ID,
        api_hash=API_HASH,
    )

    try:
        async with app:
            for CHAT_ID in CHAT_IDS:
                if _stop_event.is_set():
                    logger.info("Сбор истории остановлен пользователем")
                    return

                logger.info(f"Начинаю сбор истории для чата {CHAT_ID}")
                total_saved = 0
                total_fetched = 0
                offset_id = 0
                init_db()

                while total_fetched < MAX_MESSAGES:
                    if _stop_event.is_set():
                        logger.info(
                            f"Сбор истории остановлен пользователем. Сохранено: {total_saved}"
                        )
                        return

                    batch = []
                    logger.info(
                        f"Загружаю порцию из {BATCH_SIZE} сообщений (offset_id={offset_id})"
                    )

                    try:
                        messages = []
                        async for message in app.get_chat_history(
                            chat_id=CHAT_ID, limit=BATCH_SIZE, offset_id=offset_id
                        ):
                            if _stop_event.is_set():
                                break
                            if message and message.text:
                                messages.append(message)
                        batch = messages
                    except (ValueError, KeyError) as error:
                        if "Peer id invalid" in str(error) or "ID not found" in str(error):
                            logger.error(f"Неверный или недоступный ID чата {CHAT_ID}: {error}")
                            break
                        raise

                    if _stop_event.is_set():
                        logger.info(
                            f"Сбор истории остановлен пользователем. Сохранено: {total_saved}"
                        )
                        return

                    for message in batch:
                        if _stop_event.is_set():
                            break
                        if message:
                            success = save_message(message)
                            if success:
                                if message.date:
                                    utc_date = safe_convert_to_datetime(message.date)
                                    local_time = (
                                        to_user_timezone(utc_date, None) if utc_date else None
                                    )
                                    logger.info(f"Локальное время: {local_time}; хранение: UTC")
                                total_saved += 1
                        total_fetched += 1

                    if _stop_event.is_set():
                        logger.info(
                            f"Сбор истории остановлен пользователем. Сохранено: {total_saved}"
                        )
                        return

                    if not batch:
                        logger.info("Новых сообщений больше нет.")
                        break

                    batch.reverse()
                    offset_id = batch[-1].id
                    logger.info(f"Сохранено {total_saved} сообщений из {total_fetched}")

                logger.info(f"Сбор завершён. Всего сохранено: {total_saved} из {total_fetched}")
    except KeyboardInterrupt:
        logger.info("Сбор истории прерван пользователем (Ctrl+C)")


if __name__ == "__main__":
    try:
        asyncio.run(collect_history())
    except KeyboardInterrupt:
        pass
