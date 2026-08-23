from aiogram import F, Router
from aiogram.types import Message

from config import CHAT_IDS, ENABLE_EMBEDDING
from embeddings.vector_db import get_faiss_manager
from utils.logger import logger

router = Router()


@router.message(F.text == "/start")
async def start(message: Message):
    await message.answer("Привет! Я бот-тролль. Пиши что хочешь — я отвечу с издёвкой!")


@router.message(F.text == "/help")
async def help_command(message: Message):
    await message.answer(
        "Моё предназначение — поддерживать разговор, дразнить и шутить.\n\n"
        "Доступные команды:\n"
        "/search [запрос] — поиск похожих сообщений по теме"
    )


@router.message(F.text.startswith("/search "))
async def search_topic(message: Message):
    if not ENABLE_EMBEDDING:
        await message.reply("Поиск по теме отключён (ENABLE_EMBEDDING=0).")
        return

    if not message.text:
        await message.reply("Пожалуйста, укажите запрос для поиска. Пример: /search кто я?")
        return
    query = message.text[8:].strip()
    if not query:
        await message.reply("Пожалуйста, укажите запрос для поиска. Пример: /search кто я?")
        return

    chat_id = CHAT_IDS[0] if CHAT_IDS else message.chat.id

    try:
        db = get_faiss_manager()
        results = db.find_similar_with_scores(query, chat_id)

        if not results:
            await message.reply("Совпадений не найдено.")
            return

        response = f"По запросу '{query}' найдены ближайшие сообщения:\n\n"
        for i, item in enumerate(results, start=1):
            msg_text = item["content"]
            username = item["username"]
            date = item["date"]
            response += f"{i}. [{date}] @{username}: {msg_text}\n\n"

        await message.reply(response[:4000])
    except Exception as error:
        logger.error(f"Ошибка поиска по команде /search: {error}")
        await message.reply("Не удалось выполнить поиск. Попробуйте ещё раз позже.")
