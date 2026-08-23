import os
import sqlite3

from config import DB_PATH


def init_db():
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = f.read()
    with sqlite3.connect(DB_PATH) as conn:
        try:
            conn.executescript(schema)
        except sqlite3.OperationalError as error:
            if "already exists" not in str(error):
                raise
        conn.commit()
    print("База данных инициализирована.")


def migrate_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(messages)")
        columns = [column[1] for column in cursor.fetchall()]
        if "has_embedding" not in columns:
            print("Миграция: добавление столбца has_embedding")
            cursor.execute("ALTER TABLE messages ADD COLUMN has_embedding BOOLEAN DEFAULT FALSE")
            conn.commit()
        else:
            print("Столбец has_embedding уже существует")
