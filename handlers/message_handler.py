import asyncio

from aiogram import Bot, F, Router
from aiogram.types import Message, User

from api.api_selector import get_api_client
from config import ENABLE_EMBEDDING, ENABLE_LEARNING
from database.db_crud import mark_message_as_embedded, save_message, save_user
from database.db_manager import check_message_reply
from database.db_pool import db_connection_context
from embeddings.learning import learner
from embeddings.vector_db import get_faiss_manager
from utils.context_builder import build_context_for_query
from utils.helpers import MOSCOW_TZ, should_respond_to_message, to_user_timezone, to_utc_string
from utils.logger import logger
from utils.prompt_builder import build_prompt

router = Router()
vector_db = get_faiss_manager()
BOT_ID: str | None = None
BOT_USERNAME: str | None = None


@router.startup()
async def on_startup(bot: Bot):
    global BOT_ID, BOT_USERNAME
    bot_info = await bot.get_me()
    BOT_ID = str(bot_info.id)
    BOT_USERNAME = bot_info.username
    logger.info(f"Бот запущен как @{BOT_USERNAME} (ID: {BOT_ID})")


@router.message(F.text)
async def handle_message(message: Message):
    chat_id = message.chat.id
    user = message.from_user
    if not user:
        logger.warning("У сообщения нет данных пользователя, обработка пропущена")
        return

    user_id = str(user.id)
    username = user.username or user.first_name or "неизвестный_пользователь"
    raw_text = message.text.strip() if message.text else ""
    if not raw_text:
        logger.info("Пустое сообщение пропущено")
        return

    timestamp_utc = message.date
    timestamp_str = to_user_timezone(timestamp_utc, MOSCOW_TZ) if timestamp_utc else ""

    reply_to_message_id = None
    replied_to_bot = False
    if message.reply_to_message:
        reply_to_message_id = message.reply_to_message.message_id
        replied_to_row = await asyncio.to_thread(check_message_reply, chat_id, reply_to_message_id)
        if replied_to_row and replied_to_row[0] == BOT_ID:
            replied_to_bot = True

    if not should_respond_to_message(raw_text, BOT_USERNAME, replied_to_bot):
        return

    with db_connection_context() as conn:
        if conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM messages WHERE message_id = ? AND chat_id = ?",
                (message.message_id, str(message.chat.id)),
            )
            row = cursor.fetchone()
            if row:
                db_message_id = row[0]
            else:
                logger.warning(
                    "Не найден ID в базе для сообщения Telegram %s, обработка пропущена",
                    message.message_id,
                )
                return
        else:
            logger.warning("Не удалось подключиться к базе данных, обработка пропущена")
            return

    context = await asyncio.to_thread(
        build_context_for_query,
        user_id,
        username,
        raw_text,
        chat_id,
        message.message_id,
        reply_to_message_id,
    )

    prompt = build_prompt(username, user_id, raw_text, context, timestamp_str)
    logger.info(f"[{username}] {raw_text}")

    try:
        api_client = get_api_client()
        response = await api_client.get_response(prompt)
        bot_msg = await message.reply(response)

        if message.bot:
            bot_user = await message.bot.me()
            await asyncio.to_thread(
                save_user,
                User(
                    id=bot_user.id,
                    is_bot=True,
                    first_name=bot_user.first_name,
                    username=bot_user.username,
                    last_name="",
                ),
                to_utc_string(bot_msg.date) if bot_msg.date else "",
            )

        await asyncio.to_thread(save_message, bot_msg)

        if ENABLE_EMBEDDING and raw_text:
            already_indexed = vector_db.has_message(db_message_id)
            embedding_added = await asyncio.to_thread(
                vector_db.add_message,
                db_message_id,
                raw_text,
                str(chat_id),
            )
            if embedding_added and ENABLE_LEARNING:
                await asyncio.to_thread(learner.update_profile_with_new_message, user_id, raw_text)
            if already_indexed or embedding_added:
                await asyncio.to_thread(mark_message_as_embedded, db_message_id)
    except Exception as error:
        logger.error(f"Ошибка при обработке сообщения: {error}")
        await message.reply("Не удалось обработать сообщение. Попробуйте ещё раз позже.")
