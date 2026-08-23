from collections import defaultdict
from typing import Dict, List, Optional

import numpy as np

from config import EMBEDDING_DIM, ENABLE_EMBEDDING, ENABLE_LEARNING
from database.db_manager import get_user_history
from embeddings.embedder import get_embedding
from embeddings.vector_db import get_faiss_manager


class SelfLearner:
    def __init__(self):
        self.dim = EMBEDDING_DIM
        self.max_memory = 5
        if not ENABLE_EMBEDDING or not ENABLE_LEARNING:
            self.vector_db = None
            self.user_profiles = {}
            return
        self.vector_db = get_faiss_manager()
        self.user_profiles = {}

    def load_profile(self, user_id: str) -> None:
        """Загружает минимальный профиль из БД или создаёт новый"""
        if not ENABLE_EMBEDDING or not ENABLE_LEARNING:
            self.user_profiles[user_id] = {
                "embedding": np.zeros(self.dim, dtype=np.float32),
                "traits": {
                    "tone": "neutral",
                    "topics": [],
                    "personality": "normal",
                    "last_messages": [],
                },
            }
            return

        history: List[Dict] = get_user_history(user_id, limit=self.max_memory)
        if not history:
            self.user_profiles[user_id] = {
                "embedding": np.zeros(self.dim, dtype=np.float32),
                "traits": {
                    "tone": "neutral",
                    "topics": [],
                    "personality": "normal",
                    "last_messages": [],
                },
            }
            return

        texts = [msg["content"].strip() for msg in history if msg.get("content")]
        embeddings = [get_embedding(text) for text in texts if text.strip()]
        valid_embeddings = [emb for emb in embeddings if emb is not None]
        if valid_embeddings:
            avg_embedding = np.mean(np.vstack(valid_embeddings), axis=0)
        else:
            avg_embedding = np.zeros(self.dim, dtype=np.float32)

        traits = self.analyze_traits(history)

        self.user_profiles[user_id] = {
            "embedding": avg_embedding,
            "traits": traits,
            "last_messages": texts[: self.max_memory],
        }

    def update_profile_with_new_message(
        self, user_id: str, new_text: str, timestamp: Optional[str] = None
    ):
        """Обновляет профиль на основе нового сообщения"""
        if user_id not in self.user_profiles:
            self.load_profile(user_id)

        profile = self.user_profiles[user_id]
        traits = profile["traits"]

        traits["last_messages"].insert(0, new_text)
        if len(traits["last_messages"]) > self.max_memory:
            traits["last_messages"].pop()

        new_traits = self.analyze_traits([{"content": new_text}])
        for key in ["tone", "personality"]:
            traits[key] = new_traits[key]
        traits["topics"] = list(set(traits["topics"] + new_traits["topics"]))[:3]

        new_emb = get_embedding(new_text)
        if new_emb is not None:
            alpha = 0.3
            profile["embedding"] = (1 - alpha) * profile["embedding"] + alpha * new_emb

    def get_profile(self, user_id: str) -> Dict:
        if user_id not in self.user_profiles:
            self.load_profile(user_id)
        return self.user_profiles.get(
            user_id,
            {
                "embedding": np.zeros(self.dim, dtype=np.float32),
                "traits": {
                    "tone": "neutral",
                    "topics": [],
                    "personality": "normal",
                    "last_messages": [],
                },
            },
        )

    def analyze_traits(self, history: List[Dict]) -> Dict:
        """Analyzes traits using rule-based + potential embedding similarity in future."""
        tones = {
            "sarcastic": ["ну конечно", "как же", "очевидно", "да ладно"],
            "aggressive": ["пошёл", "заткнись", "тупой"],
            "friendly": ["спасибо", "пожалуйста", "привет", "здарова", "добрый", "хорошо"],
            "formal": ["уважаемый", "прошу", "в связи с", "сообщаю", "информирую"],
            "humorous": ["ха-ха", "лол", "рофл", "прикол", "смешно"],
        }

        topics_keywords = {
            "работа": ["работа", "офис", "коллеги", "босс", "зарплата", "трудовой"],
            "игры": ["игра", "steam", "cs", "warcraft", "minecraft", "fortnite", "pubg"],
            "отношения": ["жена", "муж", "девушка", "парень", "любовь", "свидание"],
            "политика": ["правительство", "выборы", "протесты", "президент", "партия"],
            "технологии": ["компьютер", "интернет", "программа", "приложение", "код"],
            "спорт": ["футбол", "баскетбол", "хоккей", "тренер", "чемпионат"],
            "путешествия": ["поездка", "отпуск", "туризм", "отель", "ресторан"],
            "еда": ["обед", "ужин", "рецепт", "ресторан", "вкусно"],
        }

        tone_counts = defaultdict(int)
        topic_counts = defaultdict(int)
        question_count = 0
        exclamation_count = 0
        emoji_count = 0
        word_count = 0

        for msg in history:
            text = msg["content"].lower()
            for tone, kws in tones.items():
                tone_counts[tone] += sum(1 for kw in kws if kw in text)
            for topic, kws in topics_keywords.items():
                topic_counts[topic] += sum(1 for kw in kws if kw in text)
            if "?" in text:
                question_count += 1
            if "!" in text:
                exclamation_count += 1
            if any(
                char in text
                for char in ["😀", "😂", "🤣", "😍", "🥰", "😊", "😉", "😎", "🤩", "🥳"]
            ):
                emoji_count += 1
            word_count += len(text.split())

        max_tone = "neutral"
        if any(tone_counts.values()) > 1:
            max_tone = max(tone_counts, key=lambda k: tone_counts[k])
        top_topics = [t for t, _ in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)][
            :5
        ]

        if question_count / len(history) > 0.7:
            personality = "curious"
        elif word_count / len(history) < 5:
            personality = "concise"
        elif exclamation_count / len(history) > 0.3:
            personality = "expressive"
        elif emoji_count / len(history) > 0.2:
            personality = "playful"
        elif len(history) > 10 and all(len(msg["content"].split()) < 5 for msg in history[-5:]):
            personality = "lazy"
        else:
            personality = "normal"

        if word_count / len(history) > 20:
            response_style = "detailed"
        elif word_count / len(history) < 8:
            response_style = "brief"
        else:
            response_style = "balanced"

        if len(history) > 20:
            frequency = "frequent"
        elif len(history) > 5:
            frequency = "regular"
        else:
            frequency = "occasional"

        return {
            "tone": max_tone,
            "topics": top_topics,
            "personality": personality,
            "preferred_response_style": response_style,
            "communication_frequency": frequency,
        }

    def get_advanced_profile(self, user_id: str) -> Dict:
        return self.get_profile(user_id)

    def update_profile_with_advanced_learner(
        self, user_id: str, new_text: str, timestamp: Optional[str] = None
    ) -> None:
        self.update_profile_with_new_message(user_id, new_text)


learner = SelfLearner()
