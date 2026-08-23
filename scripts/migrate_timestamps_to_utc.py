#!/usr/bin/env python3
"""Перевод старых московских временных меток в UTC."""

import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DB_PATH
from utils.logger import logger

MIGRATION_MARKER = "utc_timestamp_migration_v1"


def _ensure_migration_meta_table(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS migration_meta (
            name TEXT PRIMARY KEY,
            applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _migration_already_applied(cursor) -> bool:
    _ensure_migration_meta_table(cursor)
    cursor.execute("SELECT 1 FROM migration_meta WHERE name = ?", (MIGRATION_MARKER,))
    return cursor.fetchone() is not None


def migrate_timestamps_to_utc(force: bool = False):
    """Перевести сохранённые московские временные метки в UTC."""
    if not os.path.exists(DB_PATH):
        logger.error(f"База данных не найдена: {DB_PATH}")
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        if _migration_already_applied(cursor):
            logger.info("Миграция UTC уже выполнена")
            return False

        cursor.execute("SELECT COUNT(*) FROM messages WHERE date > datetime('now', '+30 minutes')")
        future_count = cursor.fetchone()[0]

        if future_count > 0:
            logger.info(f"Найдено сообщений с будущей датой: {future_count}")
        elif not force:
            logger.info("Московские временные метки автоматически не обнаружены")
            return False

        cursor.execute("UPDATE messages SET date = datetime(date, '-3 hours')")

        tables = ["users", "chats", "messages", "reactions", "chat_members"]

        for table in tables:
            cursor.execute(f"UPDATE {table} SET created_at = datetime(created_at, '-3 hours')")
            cursor.execute(f"UPDATE {table} SET updated_at = datetime(updated_at, '-3 hours')")

        cursor.execute(
            "INSERT OR REPLACE INTO migration_meta (name) VALUES (?)", (MIGRATION_MARKER,)
        )

        conn.commit()
        logger.info("Миграция успешно завершена")
        return True

    except Exception as error:
        logger.error(f"Ошибка миграции: {error}")
        conn.rollback()
        return False
    finally:
        conn.close()


def cleanup_duplicate_hashes():
    """Удалить хеши, которые должны быть пересозданы после миграции."""
    if not os.path.exists(DB_PATH):
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS message_hashes_backup AS SELECT * FROM message_hashes"
        )

        cursor.execute("DELETE FROM message_hashes")
        conn.commit()
        logger.info("Хеши сообщений очищены и будут созданы заново")
        return True
    except Exception as error:
        logger.error(f"Ошибка очистки хешей: {error}")
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Перевести старые временные метки в UTC")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Запустить миграцию без автоматического обнаружения",
    )
    args = parser.parse_args()

    migrated = migrate_timestamps_to_utc(force=args.force)
    if migrated:
        cleanup_duplicate_hashes()
