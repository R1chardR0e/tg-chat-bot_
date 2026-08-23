from typing import Optional

import numpy as np


def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> Optional[float]:
    """
    Compute cosine similarity between two vectors efficiently.
    Returns None if inputs are invalid (e.g., wrong shape, zero norm).
    """
    if not isinstance(vec1, np.ndarray) or not isinstance(vec2, np.ndarray):
        return None

    if vec1.shape != vec2.shape or vec1.size == 0 or vec2.size == 0:
        return None

    # FAISS ожидает векторы float32.
    vec1 = vec1.astype(np.float32)
    vec2 = vec2.astype(np.float32)

    # Нормализация нужна для корректного косинусного сходства.
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)

    if norm1 == 0 or norm2 == 0:
        return None

    # Для одной пары прямое скалярное произведение быстрее отдельной зависимости.
    return np.dot(vec1, vec2) / (norm1 * norm2)
