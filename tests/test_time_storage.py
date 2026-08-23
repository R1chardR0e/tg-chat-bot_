import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from utils.helpers import (
    MOSCOW_TZ,
    parse_utc_string,
    safe_convert_to_datetime,
    to_user_timezone,
    to_utc_string,
    utc_now,
)


def test_utc_round_trip() -> None:
    source = datetime(2026, 6, 29, 19, 58, 26, tzinfo=timezone.utc)

    encoded = to_utc_string(source)

    assert encoded == "2026-06-29 19:58:26"
    assert parse_utc_string(encoded) == source


def test_naive_datetime_is_treated_as_utc_for_storage() -> None:
    source = datetime(2026, 6, 29, 19, 58, 26)

    assert to_utc_string(source) == "2026-06-29 19:58:26"


def test_naive_telegram_datetime_is_converted_from_moscow() -> None:
    source = datetime(2026, 6, 29, 19, 58, 26)

    converted = safe_convert_to_datetime(source)

    assert converted == datetime(2026, 6, 29, 16, 58, 26, tzinfo=timezone.utc)


def test_timestamp_and_local_time_conversion() -> None:
    converted = safe_convert_to_datetime(0)

    assert converted == datetime(1970, 1, 1, tzinfo=timezone.utc)
    assert to_user_timezone(converted, MOSCOW_TZ) == "1970-01-01 03:00:00"


def test_utc_now_is_timezone_aware() -> None:
    before = datetime.now(timezone.utc) - timedelta(seconds=1)
    value = utc_now()
    after = datetime.now(timezone.utc) + timedelta(seconds=1)

    assert value.tzinfo is timezone.utc
    assert before <= value <= after


def test_database_schema_accepts_utc_message(tmp_path: Path) -> None:
    schema_path = Path(__file__).parents[1] / "database" / "schema.sql"
    database_path = tmp_path / "chat.db"

    with sqlite3.connect(database_path) as connection:
        connection.executescript(schema_path.read_text(encoding="utf-8"))
        connection.execute(
            """
            INSERT INTO messages (message_id, chat_id, user_id, date, media_type, content)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (1, "test-chat", "test-user", "2026-06-29 19:58:26", "text", "Проверка"),
        )
        row = connection.execute(
            "SELECT message_id, chat_id, date, content FROM messages"
        ).fetchone()

    assert row == (1, "test-chat", "2026-06-29 19:58:26", "Проверка")
