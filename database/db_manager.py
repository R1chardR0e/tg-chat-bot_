import sqlite3

from config import DB_PATH


def get_user_history(user_id, limit=5):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT content, date FROM messages WHERE user_id=? ORDER BY date DESC LIMIT ?",
            (user_id, limit),
        )
        return [{"content": row[0], "date": row[1]} for row in cursor.fetchall()]


def get_all_users(limit=100):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users LIMIT ?", (limit,))
        rows = cursor.fetchall()

    return [{"user_id": row[0]} for row in rows]


def check_message_reply(chat_id, reply_to_message_id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT user_id FROM messages WHERE chat_id = ? AND message_id = ?
        """,
            (chat_id, reply_to_message_id),
        )
        replied_to_row = cursor.fetchone()
    return replied_to_row
