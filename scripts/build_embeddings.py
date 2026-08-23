import argparse
import os
import sqlite3
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from config import DB_PATH  # noqa: E402
from database.db_crud import mark_message_as_embedded  # noqa: E402
from embeddings.vector_db import FAISSManager  # noqa: E402
from utils.logger import logger  # noqa: E402


def count_tokens(text: str) -> int:
    """Приблизительно оценить число токенов в тексте."""
    return max(1, len(text) // 4)


def build_embeddings(batch_size: int = 500, silent: bool = False) -> int:
    """Построить недостающие эмбеддинги и вернуть число обработанных сообщений."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, message_id, content, chat_id
        FROM messages
        WHERE has_embedding = 0 OR has_embedding IS NULL
        ORDER BY date ASC
        """
    )
    all_messages = cursor.fetchall()

    if not all_messages:
        if not silent:
            logger.info("Нет новых сообщений для индексации")
        conn.close()
        return 0

    if not silent:
        logger.info(f"Построение эмбеддингов для {len(all_messages)} сообщений...")

    vector_db = FAISSManager()
    vector_db.batch_size = batch_size
    processed = 0
    pending_mark_ids = []

    for msg_id, _telegram_msg_id, text, chat_id in all_messages:
        if not text.strip():
            continue

        if vector_db.has_message(msg_id):
            mark_message_as_embedded(msg_id)
            continue

        try:
            success = vector_db.add_message(msg_id, text, str(chat_id))
            if not success:
                logger.error(f"[ID в БД: {msg_id}] Эмбеддинг не сохранён")
                continue
            pending_mark_ids.append(msg_id)
            processed += 1
            if processed % batch_size == 0:
                if vector_db._flush_pending():
                    for pending_id in pending_mark_ids:
                        mark_message_as_embedded(pending_id)
                    pending_mark_ids.clear()
                    if not silent:
                        logger.info(f"Обработано сообщений: {processed}")
                else:
                    logger.error("Не удалось сохранить пакет эмбеддингов")
        except Exception as error:
            logger.error(f"[ID в БД: {msg_id}] Ошибка эмбеддинга: {error}")

    if vector_db._flush_pending():
        for pending_id in pending_mark_ids:
            mark_message_as_embedded(pending_id)
    else:
        logger.error("Не удалось сохранить последний пакет эмбеддингов")
    conn.close()

    if not silent:
        logger.info(f"Построено эмбеддингов: {processed}")

    return processed


def main():
    parser = argparse.ArgumentParser(description="Построить эмбеддинги для сообщений")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Показать объём работы без обработки сообщений",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Размер пакета, по умолчанию 500",
    )
    parser.add_argument("--silent", action="store_true", help="Не выводить прогресс")
    args = parser.parse_args()

    if args.dry_run:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, message_id, chat_id
            FROM messages
            WHERE has_embedding = 0 OR has_embedding IS NULL
            """
        )
        messages = cursor.fetchall()
        print(f"Будет обработано сообщений: {len(messages)}")
        for msg_id, telegram_id, chat_id in messages[:10]:
            print(f"  ID в БД: {msg_id}, ID Telegram: {telegram_id}, чат: {chat_id}")
        if len(messages) > 10:
            print(f"  ... и ещё {len(messages) - 10}")
        conn.close()
        return 0

    return build_embeddings(batch_size=args.batch_size, silent=args.silent)


if __name__ == "__main__":
    exit(main())
