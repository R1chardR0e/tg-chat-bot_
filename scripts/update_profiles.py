import asyncio

from database.db_manager import get_all_users
from embeddings.learning import SelfLearner
from utils.logger import logger

learner = SelfLearner()


async def update_all_profiles():
    logger.info("Начинаю обновление профилей пользователей...")
    users = get_all_users()

    for user in users:
        user_id = user["user_id"]
        logger.info(f"Обновляю профиль для пользователя {user_id}...")
        try:
            learner.load_profile(user_id)  # Полная перезагрузка профиля
        except Exception as error:
            logger.error(f"Ошибка при обработке пользователя {user_id}: {error}")

    logger.info("Профили пользователей успешно обновлены.")


if __name__ == "__main__":
    asyncio.run(update_all_profiles())
