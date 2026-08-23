import re
from datetime import datetime, timezone
from typing import Optional, Union

import pytz

UTC = timezone.utc
MOSCOW_TZ = pytz.timezone("Europe/Moscow")


def utc_now() -> datetime:
    """Returns current UTC time as timezone-aware datetime."""
    return datetime.now(UTC)


def to_utc_string(dt: Optional[datetime]) -> Optional[str]:
    """Converts any datetime to UTC ISO format string.

    Args:
        dt: Datetime object to convert (can be naive or timezone-aware)

    Returns:
        String in 'YYYY-MM-DD HH:MM:SS' format in UTC, or None if input is None.
    """
    if dt is None:
        return None

    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC)
    else:
        dt = dt.replace(tzinfo=UTC)

    return dt.strftime("%Y-%m-%d %H:%M:%S")


def parse_utc_string(s: str) -> datetime:
    """Parses a UTC timestamp string to timezone-aware datetime."""
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)


def to_user_timezone(
    utc_time: Optional[Union[datetime, str]], user_tz: Optional[object] = None
) -> Optional[str]:
    """Converts UTC timestamp to user's local timezone for presentation.

    Args:
        utc_time: UTC datetime or ISO string to convert (must be UTC source)
        user_tz: Target timezone (defaults to Moscow if None)

    Returns:
        Local time string or None if input is None
    """
    if utc_time is None:
        return None

    if user_tz is None:
        user_tz = MOSCOW_TZ

    if isinstance(utc_time, str):
        utc_time = parse_utc_string(utc_time)

    local_dt = utc_time.astimezone(user_tz)
    return local_dt.strftime("%Y-%m-%d %H:%M:%S")


def safe_convert_to_datetime(date_value: any) -> Optional[datetime]:
    """Safely convert int timestamps or datetime objects to UTC datetime objects.

    Args:
        date_value: Either an int timestamp, a datetime object, or None.
                    Naive datetimes are assumed to be Moscow time and converted to UTC.

    Returns:
        UTC datetime object or None if conversion fails
    """
    if date_value is None:
        return None

    if isinstance(date_value, datetime):
        if date_value.tzinfo is not None:
            return date_value.astimezone(UTC)
        # В старых данных naive datetime трактуется как московское время.
        moscow_dt = MOSCOW_TZ.localize(date_value)
        return moscow_dt.astimezone(UTC)

    if isinstance(date_value, (int, float)):
        try:
            return datetime.fromtimestamp(date_value, tz=UTC)
        except (ValueError, OSError):
            return None

    return None


def to_msk(date: datetime) -> str:
    """Converts a datetime object to Moscow time string.

    DEPRECATED: Use to_user_timezone() for explicit timezone conversion.
    This function exists for backward compatibility.

    Args:
        date: Datetime object to convert (assumed to be UTC if naive)

    Returns:
        String in 'YYYY-MM-DD HH:MM:SS' format in Moscow time, or None if date is None.
    """
    if date is None:
        return None

    if date.tzinfo is not None:
        dt = date.astimezone(MOSCOW_TZ)
    else:
        dt = date.replace(tzinfo=UTC).astimezone(MOSCOW_TZ)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def contains_bot_mention(text: str, bot_username: Optional[str]) -> bool:
    """Проверить наличие точного упоминания текущего Telegram-бота."""
    if not text or not bot_username:
        return False

    username = bot_username.strip().lstrip("@")
    if not username:
        return False

    mention_pattern = rf"(?<![A-Za-z0-9_])@{re.escape(username)}(?![A-Za-z0-9_])"
    return re.search(mention_pattern, text, flags=re.IGNORECASE) is not None


def should_respond_to_message(
    text: str,
    bot_username: Optional[str],
    replied_to_bot: bool,
) -> bool:
    """Определить, нужно ли отвечать на сообщение в групповом чате."""
    return replied_to_bot or "?" in text or contains_bot_mention(text, bot_username)
