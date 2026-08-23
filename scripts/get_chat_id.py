import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyrogram import Client

from config import API_HASH, API_ID, CHAT_URL


def validate_config_values():
    """Проверить параметры Telegram API."""
    if API_ID is None:
        raise ValueError("API_ID не задан. Проверьте файл .env.")
    if API_HASH is None:
        raise ValueError("API_HASH не задан. Проверьте файл .env.")
    if CHAT_URL is None:
        raise ValueError("CHAT_URL не задан. Проверьте файл .env.")

    try:
        api_id = int(API_ID)
    except (ValueError, TypeError) as error:
        raise ValueError("API_ID должен быть целым числом.") from error

    return api_id, API_HASH, CHAT_URL


SESSION_NAME = "my_session"


async def get_chat_id():
    api_id, api_hash, chat_url = validate_config_values()

    async with Client(SESSION_NAME, api_id=api_id, api_hash=api_hash) as app:
        chat = await app.get_chat(chat_url)
        print(f"Название чата: {chat.title}")
        print(f"ID чата: {chat.id}")


if __name__ == "__main__":
    asyncio.run(get_chat_id())
