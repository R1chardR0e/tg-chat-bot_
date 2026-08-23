import sqlite3
from datetime import datetime, timezone

from config import DB_PATH, MAX_DEPTH, RECENT_TOP_K
from utils.helpers import to_utc_string


def get_messages_by_time_range(start_time: datetime, chat_id: int, excluded_ids: set) -> list:
    query = """
        SELECT m.id, m.content, m.date, u.username, m.message_id
        FROM messages m
        LEFT JOIN users u ON m.user_id = u.user_id
        WHERE m.date >= ?
    """
    # Границы запроса приводятся к формату UTC в базе.
    params = [
        to_utc_string(start_time)
        if start_time.tzinfo
        else to_utc_string(start_time.replace(tzinfo=timezone.utc))
    ]
    if chat_id:
        query += " AND m.chat_id = ?"
        params.append(chat_id)
    if excluded_ids:
        query += f" AND m.message_id NOT IN ({','.join('?' * len(excluded_ids))})"
        params.extend(excluded_ids)
    query += " ORDER BY m.date DESC LIMIT ?"
    params.append(RECENT_TOP_K)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()

        chain = [
            {"id": row[4], "content": row[1], "date": row[2], "username": row[3] or "user"}
            for row in rows
        ]
        return chain


def get_reply_chain(reply_to_id: int, chat_id) -> list:
    """Возвращает цепочку ответов на сообщения"""
    chain = []
    current_id = reply_to_id

    for _ in range(MAX_DEPTH):
        if not current_id:
            break

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            query = """
                SELECT m.id, m.content, m.date, u.username, m.message_id
                FROM messages m
                LEFT JOIN users u ON m.user_id = u.user_id
                WHERE m.message_id = ?"""
            params = [current_id]
            if chat_id:
                query += " AND m.chat_id = ?"
                params.append(chat_id)

            cursor.execute(query, tuple(params))
            row = cursor.fetchone()

            if not row:
                break

            chain.append(
                {
                    "message_id": row[4],
                    "content": row[1],
                    "date": row[2],
                    "username": row[3] or "пользователь",
                }
            )

            # Переходим к родительскому сообщению
            cursor.execute(
                """
                SELECT reply_to_message_id FROM messages WHERE message_id = ? AND chat_id = ?
            """,
                (
                    current_id,
                    chat_id,
                ),
            )
            parent = cursor.fetchone()
            if not parent or not parent[0]:
                break

            current_id = parent[0]

    return chain
