import time
from typing import Optional

import numpy as np
from openai import APIError, OpenAI

from config import EMBEDDING_DIM, EMBEDDING_MODEL, ENABLE_EMBEDDING, IO_NET_API_KEY
from utils.logger import logger

# Используем клиентский интерфейс OpenAI v1+
client = OpenAI(api_key=IO_NET_API_KEY, base_url="https://api.intelligence.io.solutions/api/v1/")

MODEL_AVAILABLE = None  # Cache model availability


def check_embedding_model() -> bool:
    """Check if embedding model is available, caching result."""
    global MODEL_AVAILABLE
    if MODEL_AVAILABLE is not None:
        return MODEL_AVAILABLE

    if not ENABLE_EMBEDDING:
        logger.info("Embedding is disabled via ENABLE_EMBEDDING config.")
        MODEL_AVAILABLE = False
        return False

    try:
        client.models.retrieve(EMBEDDING_MODEL)
        MODEL_AVAILABLE = True
        logger.info(f"Embedding model {EMBEDDING_MODEL} is available.")
        return True
    except APIError as e:
        logger.error(f"Embedding model {EMBEDDING_MODEL} unavailable: {e}")
        MODEL_AVAILABLE = False
        return False


def get_embedding(text: str, retries: int = 2, backoff: float = 1.0) -> Optional[np.ndarray]:
    """
    Get embedding for text with retries and input validation.
    Returns None on failure.
    """
    if not ENABLE_EMBEDDING:
        return None

    if not check_embedding_model():
        logger.error(f"Cannot embed: Model {EMBEDDING_MODEL} unavailable.")
        return None

    clean_text = text.strip()
    if not clean_text:
        logger.warning("Невозможно получить эмбеддинг для пустого текста.")
        return None

    attempt = 0

    while attempt <= retries:
        try:
            response = client.embeddings.create(
                model=EMBEDDING_MODEL, input=clean_text, encoding_format="float"
            )
            embedding = np.array(response.data[0].embedding, dtype=np.float32)
            if embedding.shape != (EMBEDDING_DIM,):
                logger.error(
                    f"Unexpected embedding shape: {embedding.shape}, expected ({EMBEDDING_DIM},)"
                )
                return None
            return embedding
        except APIError as e:
            attempt += 1
            if attempt > retries:
                logger.error(f"Failed to get embedding after {retries} retries: {e}")
                return None
            logger.warning(f"Embedding attempt {attempt} failed: {e}. Retrying in {backoff}s...")
            time.sleep(backoff)
            backoff *= 2  # Exponential backoff

    return None
