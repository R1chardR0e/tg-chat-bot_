from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from sqlite3 import IntegrityError
from typing import TYPE_CHECKING, Any, Dict, Optional, Union

from aiogram.types import Chat as AiogramChat
from aiogram.types import Message as AiogramMessage
from aiogram.types import User as AiogramUser

if TYPE_CHECKING:
    from pyrogram.types import Chat as PyrogramChat
    from pyrogram.types import Message as PyrogramMessage
    from pyrogram.types import User as PyrogramUser

from database.db_pool import db_connection_context
from utils.helpers import safe_convert_to_datetime, to_utc_string
from utils.logger import logger


def safe_str(value: Any) -> Optional[str]:
    """Safely convert a value to string."""
    if value is None:
        return None
    return str(value)


def safe_int(value: Any) -> Optional[int]:
    """Safely convert a value to int."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def safe_float(value: Any) -> Optional[float]:
    """Safely convert a value to float."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def safe_bool(value: Any) -> Optional[bool]:
    """Safely convert a value to bool."""
    if value is None:
        return None
    return bool(value)


def save_message(message_obj: Union[AiogramMessage, PyrogramMessage]) -> Optional[int]:
    """
    Saves message from aiogram or Pyrogram with all media types support.
    Automatically determines the object type and media.

    Args:
        message_obj: Message object from aiogram or Pyrogram

    Returns:
        Database ID of the saved message or None if failed/duplicate
    """
    try:
        message_id: int
        date_utc: Optional[str] = None

        if hasattr(message_obj, "message_id"):
            message_id = int(message_obj.message_id)
            converted_date = safe_convert_to_datetime(message_obj.date)
            if converted_date:
                date_utc = to_utc_string(converted_date)
        elif hasattr(message_obj, "id"):
            message_id = int(message_obj.id)
            converted_date = safe_convert_to_datetime(message_obj.date)
            if converted_date:
                date_utc = to_utc_string(converted_date)
        else:
            raise ValueError("Message object doesn't contain message_id or id")

        if date_utc is None:
            logger.error("Failed to determine message date")
            return None

        # Дата не входит в хеш: одно сообщение не дублируется из-за часового пояса.
        msg_hash = hashlib.sha256(f"{message_obj.chat.id}_{message_id}".encode()).hexdigest()
        with db_connection_context() as conn:
            if not conn:
                logger.error("Failed to get database connection for save_message")
                return None

            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM message_hashes WHERE hash=?", (msg_hash,))
            if cursor.fetchone():
                logger.debug(f"Message {message_id} is duplicate, skipping")
                return None

        if message_obj.from_user:
            save_user(message_obj.from_user, date_utc)
        save_chat(message_obj.chat)

        media_fields: Dict[str, Optional[Union[str, int, float, bool]]] = {
            "media_type": "text",
            "content": "",
            "file_id": None,
            "file_unique_id": None,
            "file_size": None,
            "mime_type": None,
            "width": None,
            "height": None,
            "duration": None,
            "performer": None,
            "title": None,
            "sticker_emoji": None,
            "sticker_set_name": None,
            "is_animated_sticker": None,
            "is_video_sticker": None,
            "poll_question": None,
            "poll_options": None,
            "poll_total_voters": None,
            "poll_is_closed": None,
            "poll_is_anonymous": None,
            "poll_type": None,
            "latitude": None,
            "longitude": None,
            "contact_phone_number": None,
            "contact_first_name": None,
            "contact_last_name": None,
            "contact_vcard": None,
            "venue_title": None,
            "venue_address": None,
            "venue_latitude": None,
            "venue_longitude": None,
            "dice_value": None,
            "game_title": None,
            "game_description": None,
            "invoice_title": None,
            "invoice_description": None,
            "invoice_total_amount": None,
            "invoice_currency": None,
        }

        reply_to_user_id: Optional[str] = None
        reply_to_message_id: Optional[int] = None

        if hasattr(message_obj, "reply_to_message") and message_obj.reply_to_message:
            if hasattr(message_obj.reply_to_message, "message_id"):
                reply_to_message_id = int(message_obj.reply_to_message.message_id)
                if (
                    hasattr(message_obj.reply_to_message, "from_user")
                    and message_obj.reply_to_message.from_user
                ):
                    reply_to_user_id = str(message_obj.reply_to_message.from_user.id)
        else:
            reply_to_message_id_attr = getattr(message_obj, "reply_to_message_id", None)
            if reply_to_message_id_attr is not None and reply_to_message_id_attr != 0:
                reply_to_message_id = int(reply_to_message_id_attr)

        if hasattr(message_obj, "text") and message_obj.text:
            media_fields["media_type"] = "text"
            media_fields["content"] = message_obj.text
        elif hasattr(message_obj, "caption") and message_obj.caption:
            media_fields["content"] = message_obj.caption
        elif hasattr(message_obj, "poll") and message_obj.poll:
            media_fields["media_type"] = "poll"
            poll = message_obj.poll
            media_fields["poll_question"] = poll.question
            media_fields["poll_options"] = json.dumps([opt.text for opt in poll.options])
            media_fields["poll_total_voters"] = poll.total_voter_count
            media_fields["poll_is_closed"] = poll.is_closed
            media_fields["poll_is_anonymous"] = poll.is_anonymous
            media_fields["poll_type"] = str(poll.type) if hasattr(poll, "type") else "regular"
        elif hasattr(message_obj, "photo") and message_obj.photo:
            media_fields["media_type"] = "photo"
            if isinstance(message_obj.photo, list):
                largest_photo = max(
                    message_obj.photo, key=lambda p: p.file_size if p.file_size else 0
                )
            else:
                largest_photo = message_obj.photo
            media_fields["file_id"] = getattr(largest_photo, "file_id", None)
            media_fields["file_unique_id"] = getattr(largest_photo, "file_unique_id", None)
            media_fields["file_size"] = getattr(largest_photo, "file_size", None)
            media_fields["width"] = getattr(largest_photo, "width", None)
            media_fields["height"] = getattr(largest_photo, "height", None)
            media_fields["content"] = "[Фото]"
            if hasattr(message_obj, "caption") and message_obj.caption:
                media_fields["content"] += f"\n{message_obj.caption}"
        elif hasattr(message_obj, "video") and message_obj.video:
            media_fields["media_type"] = "video"
            media_fields["file_id"] = message_obj.video.file_id
            media_fields["file_unique_id"] = message_obj.video.file_unique_id
            media_fields["file_size"] = message_obj.video.file_size
            media_fields["mime_type"] = message_obj.video.mime_type
            media_fields["width"] = message_obj.video.width
            media_fields["height"] = message_obj.video.height
            media_fields["duration"] = message_obj.video.duration
            media_fields["performer"] = getattr(message_obj.video, "performer", None)
            media_fields["title"] = getattr(message_obj.video, "title", None)
            media_fields["content"] = "[Видео]"
            if hasattr(message_obj, "caption") and message_obj.caption:
                media_fields["content"] += f"\n{message_obj.caption}"
        elif hasattr(message_obj, "audio") and message_obj.audio:
            media_fields["media_type"] = "audio"
            media_fields["file_id"] = message_obj.audio.file_id
            media_fields["file_unique_id"] = message_obj.audio.file_unique_id
            media_fields["file_size"] = message_obj.audio.file_size
            media_fields["mime_type"] = message_obj.audio.mime_type
            media_fields["duration"] = message_obj.audio.duration
            media_fields["performer"] = getattr(message_obj.audio, "performer", None)
            media_fields["title"] = getattr(message_obj.audio, "title", None)
            media_fields["content"] = f"[Аудио] {media_fields['title'] or ''}"
            if hasattr(message_obj, "caption") and message_obj.caption:
                media_fields["content"] += f"\n{message_obj.caption}"
        elif hasattr(message_obj, "voice") and message_obj.voice:
            media_fields["media_type"] = "voice"
            media_fields["file_id"] = message_obj.voice.file_id
            media_fields["file_unique_id"] = message_obj.voice.file_unique_id
            media_fields["file_size"] = message_obj.voice.file_size
            media_fields["mime_type"] = message_obj.voice.mime_type
            media_fields["duration"] = message_obj.voice.duration
            media_fields["content"] = "[Голосовое сообщение]"
        elif hasattr(message_obj, "document") and message_obj.document:
            media_fields["media_type"] = "document"
            media_fields["file_id"] = message_obj.document.file_id
            media_fields["file_unique_id"] = message_obj.document.file_unique_id
            media_fields["file_size"] = message_obj.document.file_size
            media_fields["mime_type"] = message_obj.document.mime_type
            media_fields["content"] = f"[Файл] {message_obj.document.file_name}"
            if hasattr(message_obj, "caption") and message_obj.caption:
                media_fields["content"] += f"\n{message_obj.caption}"
        elif hasattr(message_obj, "sticker") and message_obj.sticker:
            media_fields["media_type"] = "sticker"
            media_fields["file_id"] = message_obj.sticker.file_id
            media_fields["file_unique_id"] = message_obj.sticker.file_unique_id
            media_fields["mime_type"] = message_obj.sticker.mime_type
            media_fields["file_size"] = message_obj.sticker.file_size
            media_fields["width"] = message_obj.sticker.width
            media_fields["height"] = message_obj.sticker.height
            media_fields["sticker_emoji"] = message_obj.sticker.emoji
            media_fields["sticker_set_name"] = message_obj.sticker.set_name
            media_fields["is_animated_sticker"] = message_obj.sticker.is_animated
            media_fields["is_video_sticker"] = message_obj.sticker.is_video
            media_fields["content"] = f"[Стикер] {media_fields['sticker_emoji'] or ''}"
        elif hasattr(message_obj, "animation") and message_obj.animation:
            media_fields["media_type"] = "animation"
            media_fields["file_id"] = message_obj.animation.file_id
            media_fields["file_unique_id"] = message_obj.animation.file_unique_id
            media_fields["file_size"] = message_obj.animation.file_size
            media_fields["mime_type"] = message_obj.animation.mime_type
            media_fields["width"] = message_obj.animation.width
            media_fields["height"] = message_obj.animation.height
            media_fields["duration"] = message_obj.animation.duration
            media_fields["content"] = "[GIF]"
            if hasattr(message_obj, "caption") and message_obj.caption:
                media_fields["content"] += f"\n{message_obj.caption}"
        elif hasattr(message_obj, "video_note") and message_obj.video_note:
            media_fields["media_type"] = "video_note"
            media_fields["file_id"] = message_obj.video_note.file_id
            media_fields["file_unique_id"] = message_obj.video_note.file_unique_id
            media_fields["file_size"] = message_obj.video_note.file_size
            media_fields["duration"] = message_obj.video_note.duration
            media_fields["length"] = message_obj.video_note.length
            media_fields["content"] = "[Видеосообщение]"
        elif hasattr(message_obj, "location") and message_obj.location:
            media_fields["media_type"] = "location"
            media_fields["latitude"] = message_obj.location.latitude
            media_fields["longitude"] = message_obj.location.longitude
            media_fields["content"] = (
                f"[Локация] Широта: {media_fields['latitude']}, Долгота: {media_fields['longitude']}"
            )
        elif hasattr(message_obj, "contact") and message_obj.contact:
            media_fields["media_type"] = "contact"
            media_fields["contact_phone_number"] = message_obj.contact.phone_number
            media_fields["contact_first_name"] = message_obj.contact.first_name
            media_fields["contact_last_name"] = getattr(message_obj.contact, "last_name", None)
            media_fields["contact_vcard"] = getattr(message_obj.contact, "vcard", None)
            media_fields["content"] = (
                f"[Контакт] {media_fields['contact_first_name']} {media_fields['contact_last_name'] or ''}: {media_fields['contact_phone_number']}"
            )
        elif hasattr(message_obj, "venue") and message_obj.venue:
            media_fields["media_type"] = "venue"
            media_fields["venue_title"] = message_obj.venue.title
            media_fields["venue_address"] = message_obj.venue.address
            media_fields["venue_latitude"] = message_obj.venue.location.latitude
            media_fields["venue_longitude"] = message_obj.venue.location.longitude
            media_fields["content"] = (
                f"[Место] {media_fields['venue_title']}: {media_fields['venue_address']}"
            )
        elif hasattr(message_obj, "dice") and message_obj.dice:
            media_fields["media_type"] = "dice"
            media_fields["dice_value"] = message_obj.dice.value
            media_fields["content"] = f"[Кубик] Значение: {media_fields['dice_value']}"
        elif hasattr(message_obj, "game") and message_obj.game:
            media_fields["media_type"] = "game"
            media_fields["game_title"] = message_obj.game.title
            media_fields["game_description"] = message_obj.game.description
            media_fields["content"] = (
                f"[Игра] {media_fields['game_title']}: {media_fields['game_description']}"
            )
        elif getattr(message_obj, "invoice", None):
            media_fields["media_type"] = "invoice"
            invoice_obj = getattr(message_obj, "invoice", None)
            media_fields["invoice_title"] = getattr(invoice_obj, "title", None)
            media_fields["invoice_description"] = getattr(invoice_obj, "description", None)
            media_fields["invoice_total_amount"] = getattr(invoice_obj, "total_amount", None)
            media_fields["invoice_currency"] = getattr(invoice_obj, "currency", None)
            media_fields["content"] = (
                f"[Счёт] {media_fields['invoice_title'] or ''}: {media_fields['invoice_description'] or ''}"
            )
        else:
            media_fields["media_type"] = "unknown"
            media_fields["content"] = "[Неизвестный тип сообщения]"
            logger.warning(f"Unknown message type for message {message_id}")

        with db_connection_context() as conn:
            if not conn:
                logger.error("Failed to get database connection for save_message")
                return None

            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO messages (
                        message_id, chat_id, user_id, date, edit_date,
                        forward_from_user_id, forward_from_chat_id, forward_from_message_id,
                        forward_signature, forward_sender_name, forward_date,
                        reply_to_message_id, reply_to_user_id,
                        media_type, content,
                        file_id, file_unique_id, file_size, mime_type,
                        duration, width, height, performer, title,
                        sticker_emoji, sticker_set_name, is_animated_sticker, is_video_sticker,
                        poll_question, poll_options, poll_total_voters, poll_is_closed, poll_is_anonymous, poll_type,
                        latitude, longitude,
                        contact_phone_number, contact_first_name, contact_last_name, contact_vcard,
                        venue_title, venue_address, venue_latitude, venue_longitude,
                        dice_value,
                        game_title, game_description,
                        invoice_title, invoice_description, invoice_total_amount, invoice_currency,
                        has_protected_content
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        message_id,
                        str(message_obj.chat.id),
                        str(message_obj.from_user.id) if message_obj.from_user else None,
                        date_utc,
                        safe_str(to_utc_string(safe_convert_to_datetime(message_obj.edit_date)))
                        if message_obj.edit_date
                        else None,
                        safe_str(message_obj.forward_from.id) if message_obj.forward_from else None,
                        safe_str(message_obj.forward_from_chat.id)
                        if message_obj.forward_from_chat
                        else None,
                        safe_int(message_obj.forward_from_message_id),
                        safe_str(message_obj.forward_signature),
                        safe_str(message_obj.forward_sender_name),
                        safe_str(to_utc_string(safe_convert_to_datetime(message_obj.forward_date)))
                        if message_obj.forward_date
                        else None,
                        safe_int(reply_to_message_id),
                        safe_str(reply_to_user_id),
                        safe_str(media_fields["media_type"]),
                        safe_str(media_fields["content"]),
                        safe_str(media_fields["file_id"]),
                        safe_str(media_fields["file_unique_id"]),
                        safe_int(media_fields["file_size"]),
                        safe_str(media_fields["mime_type"]),
                        safe_int(media_fields["duration"]),
                        safe_int(media_fields["width"]),
                        safe_int(media_fields["height"]),
                        safe_str(media_fields["performer"]),
                        safe_str(media_fields["title"]),
                        safe_str(media_fields["sticker_emoji"]),
                        safe_str(media_fields["sticker_set_name"]),
                        safe_bool(media_fields["is_animated_sticker"]),
                        safe_bool(media_fields["is_video_sticker"]),
                        safe_str(media_fields["poll_question"]),
                        safe_str(media_fields["poll_options"]),
                        safe_int(media_fields["poll_total_voters"]),
                        safe_bool(media_fields["poll_is_closed"]),
                        safe_bool(media_fields["poll_is_anonymous"]),
                        safe_str(media_fields["poll_type"]),
                        safe_float(media_fields["latitude"]),
                        safe_float(media_fields["longitude"]),
                        safe_str(media_fields["contact_phone_number"]),
                        safe_str(media_fields["contact_first_name"]),
                        safe_str(media_fields["contact_last_name"]),
                        safe_str(media_fields["contact_vcard"]),
                        safe_str(media_fields["venue_title"]),
                        safe_str(media_fields["venue_address"]),
                        safe_float(media_fields["venue_latitude"]),
                        safe_float(media_fields["venue_longitude"]),
                        safe_int(media_fields["dice_value"]),
                        safe_str(media_fields["game_title"]),
                        safe_str(media_fields["game_description"]),
                        safe_str(media_fields["invoice_title"]),
                        safe_str(media_fields["invoice_description"]),
                        safe_int(media_fields["invoice_total_amount"]),
                        safe_str(media_fields["invoice_currency"]),
                        safe_bool(getattr(message_obj, "has_protected_content", None)),
                    ),
                )

                try:
                    cursor.execute("INSERT INTO message_hashes (hash) VALUES (?)", (msg_hash,))
                    conn.commit()
                    return cursor.lastrowid
                except IntegrityError:
                    conn.rollback()
                    logger.debug(f"Message {message_id} is duplicate (hash conflict), skipping")
                    return None

            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to save message {message_id}: {e}")
                raise e

    except Exception as e:
        logger.error(
            f"Failed to process message {getattr(message_obj, 'message_id', getattr(message_obj, 'id', 'unknown'))}: {e}"
        )
        return None


def mark_message_as_embedded(message_db_id: int, has_embedding: bool = True) -> bool:
    """Mark a stored message as embedded once its vector is persisted."""
    with db_connection_context() as conn:
        if not conn:
            logger.error("Failed to get database connection for mark_message_as_embedded")
            return False

        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE messages SET has_embedding = ? WHERE id = ?",
                (1 if has_embedding else 0, message_db_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update has_embedding for message {message_db_id}: {e}")
            return False


def save_user(user: Union[AiogramUser, PyrogramUser], date_utc: str) -> bool:
    with db_connection_context() as conn:
        if not conn:
            logger.error("Failed to get database connection for save_user")
            return False

        cursor = conn.cursor()
        try:
            user_id = str(getattr(user, "id", ""))
            username = getattr(user, "username", None)
            first_name = getattr(user, "first_name", None)
            last_name = getattr(user, "last_name", None) or ""

            cursor.execute("SELECT created_at FROM users WHERE user_id = ?", (user_id,))
            existing_user = cursor.fetchone()

            if existing_user:
                created_at_time = existing_user[0]
                cursor.execute(
                    """INSERT OR REPLACE INTO users (user_id, username, first_name, last_name, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (user_id, username, first_name, last_name, created_at_time, date_utc),
                )
            else:
                cursor.execute(
                    """INSERT OR REPLACE INTO users (user_id, username, first_name, last_name, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (user_id, username, first_name, last_name, date_utc, date_utc),
                )
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to save user {getattr(user, 'id', 'unknown')}: {e}")
            raise e


def save_chat(chat_obj: Union[AiogramChat, PyrogramChat]) -> bool:
    chat_id = getattr(chat_obj, "id", "")
    title = getattr(chat_obj, "title", None)
    username = getattr(chat_obj, "username", None)
    type_ = None

    if hasattr(chat_obj, "type") and chat_obj.type:
        if hasattr(chat_obj.type, "value"):
            type_ = str(getattr(chat_obj.type, "value", chat_obj.type))
        else:
            type_ = str(chat_obj.type)

    current_time_utc = to_utc_string(datetime.now(timezone.utc))

    with db_connection_context() as conn:
        if not conn:
            logger.error("Failed to get database connection for save_chat")
            return False

        cursor = conn.cursor()
        try:
            cursor.execute("SELECT created_at FROM chats WHERE chat_id = ?", (chat_id,))
            existing_chat = cursor.fetchone()

            if existing_chat:
                created_at_time = existing_chat[0]
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO chats (chat_id, type, title, username, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (chat_id, type_, title, username, created_at_time, current_time_utc),
                )
            else:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO chats (chat_id, type, title, username, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (chat_id, type_, title, username, current_time_utc, current_time_utc),
                )
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to save chat {chat_id}: {e}")
            raise e
