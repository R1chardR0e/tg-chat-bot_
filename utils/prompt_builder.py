from config import ENABLE_LEARNING
from embeddings.learning import learner


def build_prompt(
    username: str,
    user_id: str,
    message_text: str,
    query_context: str | None = None,
    current_time: str | None = None,
) -> str:
    """Сформировать запрос к модели с контекстом и профилем пользователя."""
    prompt = """
Ты злой, язвительный ИИ-бот для группового чата.

Опираясь на полученный контекст, сделай ответ с долей сарказма, стеба и намёков.
В ответе не цитируй полученные сообщения.
"""

    if ENABLE_LEARNING:
        profile = learner.get_profile(user_id)
        traits = profile.get("traits", {})
        personality = traits.get("personality", "нейтральный")
        tone = traits.get("tone", "нейтральный")
        topics = ", ".join(traits.get("topics", [])) or "нет явных тем"
        prompt += f"""
Персонализируй ответ под пользователя:
- Типаж: {personality}
- Стиль общения: {tone}
- Интересы: {topics}
"""
    prompt += f"""
Текущее время: {current_time or "неизвестно"}
Тебе пишет @{username}.
Его сообщение: {message_text}

Контекст беседы:
{query_context or "Нет контекста"}

Ответь на сообщение от пользователя.
"""

    max_length = 4000
    if len(prompt) > max_length:
        prompt = prompt[:max_length] + "\n... (контекст усечен)"

    return prompt.strip()
