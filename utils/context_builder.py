from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set

from config import ENABLE_EMBEDDING, TIME_WINDOW_HOURS
from database.db_queries import get_messages_by_time_range, get_reply_chain
from embeddings.vector_db import get_faiss_manager
from utils.helpers import MOSCOW_TZ, to_user_timezone

TOP_K = 5


def build_context_for_query(
    user_id: str,
    username: str,
    query_text: str,
    chat_id: int,
    telegram_message_id: Optional[int] = None,
    reply_to_message_id: Optional[int] = None,
) -> str:
    # В базе время хранится в UTC.
    now_utc = datetime.now(timezone.utc)
    start_time = now_utc - timedelta(hours=TIME_WINDOW_HOURS)

    lines: List[str] = []
    excluded_telegram_ids: Set[int] = set()

    if telegram_message_id:
        excluded_telegram_ids.add(telegram_message_id)

    reply_chain: List[Dict] = []
    if reply_to_message_id:
        reply_chain = get_reply_chain(reply_to_message_id, chat_id)
    if reply_chain:
        lines.append("Цепочка ответов на сообщение:")
        for msg in reply_chain:
            # Пользователю показывается московское время.
            utc_date = msg["date"]
            local_date = to_user_timezone(utc_date, MOSCOW_TZ) if utc_date else utc_date
            lines.append(f"    [{local_date}] @{msg['username']}: {msg['content']}")
            if msg.get("message_id"):
                excluded_telegram_ids.add(msg["message_id"])

    recent_messages: List[Dict] = get_messages_by_time_range(
        start_time, chat_id, excluded_telegram_ids
    )
    if recent_messages:
        lines.append(f"Последние сообщения за последние {TIME_WINDOW_HOURS} час(а/ов)")
        if reply_chain:
            lines.append(" (исключая цепочку ответов)")
        lines[-1] += ":"
        for msg in recent_messages:
            # Пользователю показывается московское время.
            utc_date = msg["date"]
            local_date = to_user_timezone(utc_date, MOSCOW_TZ) if utc_date else utc_date
            lines.append(f"    [{local_date}] @{msg['username']}: {msg['content']}")

    if ENABLE_EMBEDDING:
        vector_db = get_faiss_manager()
        topic_messages = vector_db.find_similar_with_scores(query_text, str(chat_id), TOP_K)

        seen_ids = set(excluded_telegram_ids)
        seen_texts = set(msg.get("content", "") for msg in recent_messages + reply_chain)
        filtered = []

        for match in topic_messages:
            if match["message_id"] in seen_ids or match.get("content", "") in seen_texts:
                continue
            seen_ids.add(match["message_id"])
            filtered.append(match)

        if filtered:
            lines.append("Сообщения по теме по всему чату:")
            for msg in filtered[:TOP_K]:
                # Пользователю показывается московское время.
                utc_date = msg["date"]
                local_date = to_user_timezone(utc_date, MOSCOW_TZ) if utc_date else utc_date
                lines.append(f"    [{local_date}] @{msg['username']}: {msg['content']}")

    return "\n".join(lines)
