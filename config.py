import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent


def _data_path(variable: str, default_name: str) -> str:
    value = os.getenv(variable, "").strip()
    path = Path(value).expanduser() if value else Path(default_name)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return str(path.resolve())


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

IO_NET_API_KEY = os.getenv("IO_NET_API_KEY")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
API_ACCESS_TOKEN = os.getenv("API_ACCESS_TOKEN")
API_PROVIDER = os.getenv("API_PROVIDER", "io_net").lower()

API_URL = os.getenv("API_URL")
MODEL_NAME = os.getenv("MODEL_NAME")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")

CHAT_IDS: list[int] = []
chat_ids_str = os.getenv("CHAT_IDS", "")
if chat_ids_str:
    CHAT_IDS = [int(chat_id.strip()) for chat_id in chat_ids_str.split(",") if chat_id.strip()]

CHAT_URL = os.getenv("CHAT_URL")

ENABLE_EMBEDDING = os.getenv("ENABLE_EMBEDDING", "False").lower() in ("true", "1", "t")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "3584"))
DB_PATH = _data_path("DB_PATH", "chat.db")
VECTOR_DB_PATH = _data_path("VECTOR_DB_PATH", "chat_embeddings.index")

ENABLE_LEARNING = os.getenv("ENABLE_LEARNING", "False").lower() in ("true", "1", "t")
TIME_WINDOW_HOURS = int(os.getenv("TIME_WINDOW_HOURS", "24"))
TOPIC_TOP_K = int(os.getenv("TOPIC_TOP_K", "5"))
RECENT_TOP_K = int(os.getenv("RECENT_TOP_K", "10"))
MAX_DEPTH = int(os.getenv("MAX_DEPTH", "10"))
