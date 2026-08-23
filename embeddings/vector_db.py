import os
import pickle
import random
import sqlite3
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np

try:
    import faiss
except ImportError:
    raise ImportError("Установите faiss: pip install faiss-cpu")

from config import DB_PATH, EMBEDDING_DIM, ENABLE_EMBEDDING, TOPIC_TOP_K, VECTOR_DB_PATH
from database.db_crud import mark_message_as_embedded
from embeddings.embedder import get_embedding
from utils.helpers import to_utc_string
from utils.logger import logger

_FAISS_MANAGER: Optional["FAISSManager"] = None


class FAISSManager:
    def __init__(self, index_path: Optional[str] = None, dimension: Optional[int] = None):
        self.dim = dimension if dimension is not None else EMBEDDING_DIM
        self.index_path = index_path if index_path is not None else VECTOR_DB_PATH
        self.batch_size = 100
        self.pending_additions = []

        if not os.path.exists(self.index_path):
            self.index = faiss.IndexFlatL2(self.dim)
            self.message_metadata = []
        else:
            self.index = faiss.read_index(self.index_path)
            metadata_path = self.index_path + ".ids.pkl"
            if os.path.exists(metadata_path):
                with open(metadata_path, "rb") as f:
                    self.message_metadata = pickle.load(f)
            else:
                self.message_metadata = []
        self._normalize_legacy_metadata()

    def has_message(self, database_id: int) -> bool:
        """Return True when the database message id is already indexed or pending."""
        target_id = int(database_id)
        for meta in self.message_metadata:
            existing_id = meta.get("database_id", meta.get("message_id"))
            if existing_id is not None and int(existing_id) == target_id:
                return True
        for meta, _emb in self.pending_additions:
            existing_id = meta.get("database_id", meta.get("message_id"))
            if existing_id is not None and int(existing_id) == target_id:
                return True
        return False

    def _normalize_legacy_metadata(self) -> None:
        """Backfill database ids for older metadata formats."""
        if not self.message_metadata:
            return

        needs_normalization = any(meta.get("database_id") is None for meta in self.message_metadata)
        if not needs_normalization:
            return

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        normalized = []

        try:
            for meta in self.message_metadata:
                if meta.get("database_id") is not None:
                    normalized.append(meta)
                    continue

                legacy_message_id = meta.get("message_id")
                chat_id = meta.get("chat_id")
                database_id = None
                telegram_message_id = meta.get("telegram_message_id")

                if chat_id is not None and legacy_message_id is not None:
                    cursor.execute(
                        "SELECT id, message_id FROM messages WHERE chat_id = ? AND message_id = ?",
                        (str(chat_id), int(legacy_message_id)),
                    )
                    row = cursor.fetchone()
                    if row:
                        database_id = row[0]
                        telegram_message_id = row[1]

                if database_id is None and legacy_message_id is not None:
                    cursor.execute(
                        "SELECT id, message_id FROM messages WHERE id = ?",
                        (int(legacy_message_id),),
                    )
                    row = cursor.fetchone()
                    if row:
                        database_id = row[0]
                        telegram_message_id = row[1]

                if database_id is not None:
                    meta = dict(meta)
                    meta["database_id"] = int(database_id)
                    meta["message_id"] = int(database_id)
                    meta["telegram_message_id"] = telegram_message_id

                normalized.append(meta)

            self.message_metadata = normalized
        finally:
            conn.close()

    def _with_retry(
        self, func, max_retries: int = 3, base_delay: float = 0.1, max_delay: float = 1.0
    ):
        last_exception = None
        for attempt in range(max_retries + 1):
            try:
                return func()
            except Exception as e:
                last_exception = e
                if attempt == max_retries:
                    break
                delay = min(base_delay * (2**attempt), max_delay)
                jitter = random.uniform(0, delay * 0.1)
                time.sleep(delay + jitter)
        if last_exception is not None:
            raise last_exception
        raise Exception("Retry mechanism failed with no exception captured")

    def add_message(
        self,
        message_id: int,
        text: str,
        chat_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> bool:
        def add_operation():
            if not text.strip():
                logger.warning(f"[ID: {message_id}] Empty text, skipping.")
                return False
            if self.has_message(message_id):
                logger.debug(f"[ID: {message_id}] Message already indexed, skipping.")
                return False
            emb = get_embedding(text)
            if emb is None:
                logger.error(f"[ID: {message_id}] Failed to generate embedding for message.")
                return False
            emb = emb.reshape(1, -1)
            timestamp = (
                metadata.get("date")
                if metadata and metadata.get("date")
                else to_utc_string(datetime.now(timezone.utc))
            )
            telegram_message_id = metadata.get("telegram_message_id") if metadata else None
            database_id_value = metadata.get("database_id") if metadata else None
            database_id = (
                int(database_id_value) if database_id_value is not None else int(message_id)
            )
            msg_metadata = {
                "vector_id": len(self.message_metadata),
                "message_id": database_id,
                "database_id": database_id,
                "telegram_message_id": telegram_message_id,
                "chat_id": str(chat_id) if chat_id is not None else None,
                "timestamp_utc": timestamp,
                "metadata": {
                    "embedding_model": "default",
                    "text_content_preview": text[:100] if text else None,
                },
            }
            self.pending_additions.append((msg_metadata, emb))
            if len(self.pending_additions) >= self.batch_size:
                if not self._flush_pending():
                    return False
            return True

        try:
            return self._with_retry(add_operation)
        except Exception as e:
            logger.error(f"[ID: {message_id}] Failed to embed after retries: {e}")
            return False

    def _flush_pending(self) -> bool:
        if not self.pending_additions:
            return True

        def flush_operation():
            metadata_list, embeddings = zip(*self.pending_additions)
            embeddings_array = np.vstack(embeddings).astype("float32")
            self.index.add(embeddings_array)
            self.message_metadata.extend(metadata_list)
            faiss.write_index(self.index, self.index_path)
            with open(f"{self.index_path}.ids.pkl", "wb") as f:
                pickle.dump(self.message_metadata, f)
            logger.info(f"Flushed {len(self.pending_additions)} embeddings to disk.")
            self.pending_additions = []

        try:
            self._with_retry(flush_operation)
            return True
        except Exception as e:
            logger.error(f"Failed to flush embeddings after retries: {e}")
            return False

    def delete_message(self, message_id: int) -> bool:
        try:
            idx = -1
            for i, meta in enumerate(self.message_metadata):
                existing_id = meta.get("database_id", meta.get("message_id"))
                if existing_id == message_id:
                    idx = i
                    break

            if idx == -1:
                logger.warning(f"Message ID {message_id} not found in index.")
                return False

            embeddings_to_keep = []
            metadata_to_keep = []

            for i in range(self.index.ntotal):
                if i != idx:
                    embedding = self.index.reconstruct(int(i)).reshape(1, -1)
                    embeddings_to_keep.append(embedding)
                    if i < len(self.message_metadata):
                        metadata_to_keep.append(self.message_metadata[i])

            new_index = faiss.IndexFlatL2(self.dim)
            if embeddings_to_keep:
                embeddings_array = np.vstack(embeddings_to_keep).astype("float32")
                new_index.add(embeddings_array)

            self.index = new_index
            self.message_metadata = metadata_to_keep

            faiss.write_index(self.index, self.index_path)
            with open(f"{self.index_path}.ids.pkl", "wb") as f:
                pickle.dump(self.message_metadata, f)

            logger.info(f"Deleted embedding for message ID {message_id}.")
            return True
        except Exception as e:
            logger.error(f"Failed to delete embedding for ID {message_id}: {e}")
            return False

    def find_similar_with_scores(
        self, query_text: str, chat_id: Optional[str] = None, top_k: Optional[int] = None
    ) -> List[Dict]:
        def search_operation():
            if not query_text.strip():
                return []

            search_top_k = top_k or TOPIC_TOP_K

            query_emb = get_embedding(query_text)
            if query_emb is None:
                logger.error("Failed to generate embedding for query text.")
                return []
            query_emb = query_emb.reshape(1, -1)

            search_k = max(100, int((top_k or TOPIC_TOP_K) * 10))
            actual_search_k = min(
                search_k, self.index.ntotal if hasattr(self.index, "ntotal") else search_k
            )
            if actual_search_k > 0:
                D, indices = self.index.search(query_emb, actual_search_k)
            else:
                D, indices = np.array([]), np.array([])

            if getattr(indices, "size", 0) == 0:
                return []

            search_hits = {}
            for position, idx in enumerate(indices[0]):
                if not (0 <= int(idx) < len(self.message_metadata)):
                    continue
                meta = self.message_metadata[int(idx)]
                if chat_id is not None and str(meta.get("chat_id")) != str(chat_id):
                    continue
                database_id = meta.get("database_id", meta.get("message_id"))
                if database_id is None:
                    continue
                distance = float(D[0][position]) if len(D) > 0 and len(D[0]) > position else 0.0
                current = search_hits.get(int(database_id))
                if current is None or distance < current["distance"]:
                    search_hits[int(database_id)] = {
                        "database_id": int(database_id),
                        "distance": distance,
                    }

            if not search_hits:
                return []

            search_hits = sorted(search_hits.values(), key=lambda x: x["distance"])

            database_ids = [hit["database_id"] for hit in search_hits]
            limited_database_ids = database_ids[: min(100, len(database_ids))]
            query = """
                SELECT m.id, m.message_id, m.content, m.date, u.username, m.chat_id
                FROM messages m
                LEFT JOIN users u ON m.user_id = u.user_id
                WHERE m.id IN ({})
            """.format(",".join("?" * len(limited_database_ids)))

            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute(query, limited_database_ids)
            rows = cursor.fetchall()
            conn.close()

            rows_by_id = {int(row[0]): row for row in rows}

            results = []
            for hit in search_hits:
                row = rows_by_id.get(hit["database_id"])
                if not row:
                    continue
                results.append(
                    {
                        "database_id": row[0],
                        "message_id": row[1],
                        "content": row[2],
                        "date": row[3],
                        "username": row[4] or "пользователь",
                        "chat_id": row[5],
                        "distance": hit["distance"],
                    }
                )

            results.sort(key=lambda x: x["distance"])
            return results[:search_top_k]

        try:
            return self._with_retry(search_operation)
        except Exception as e:
            logger.error(f"Failed to find similar messages after retries: {e}")
            return []

    def search_similar_messages(
        self, query_text: str, chat_id: Optional[str] = None, top_k: Optional[int] = None
    ) -> List[Dict]:
        start_time = time.time()

        if not isinstance(query_text, str):
            raise TypeError("query_text must be a string")
        if not query_text.strip():
            raise ValueError("query_text cannot be empty")

        try:
            chat_id_str = str(chat_id) if chat_id is not None else None
            results = self.find_similar_with_scores(query_text, chat_id_str, top_k)
            query_time = (time.time() - start_time) * 1000
            logger.info(
                f"Successfully searched for '{query_text[:50]}...' in chat {chat_id_str}, found {len(results)} results in {query_time:.2f}ms"
            )
            for result in results:
                result["query_time_ms"] = query_time
            return results
        except Exception as e:
            query_time = (time.time() - start_time) * 1000
            logger.error(
                f"Failed to search similar messages for query '{query_text[:50]}...' in {query_time:.2f}ms: {e}"
            )
            raise

    def build_index_from_chats(self, chat_ids: Optional[List[str]] = None) -> bool:
        conn = None

        def build_operation():
            nonlocal conn
            self.index = faiss.IndexFlatL2(self.dim)
            self.message_metadata = []
            self.pending_additions = []

            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            query = """
                SELECT m.id, m.message_id, m.content, m.chat_id, m.date
                FROM messages m
                WHERE m.content IS NOT NULL AND m.content != ''
            """

            if chat_ids:
                placeholders = ",".join("?" * len(chat_ids))
                query += f" AND m.chat_id IN ({placeholders})"
                cursor.execute(query, chat_ids)
            else:
                cursor.execute(query)

            rows = cursor.fetchall()

            for database_id, telegram_message_id, content, chat_id, date in rows:
                if content and content.strip():
                    try:
                        emb = get_embedding(content)
                        if emb is not None:
                            emb = emb.reshape(1, -1).astype("float32")
                            timestamp = date or to_utc_string(datetime.now(timezone.utc))
                            msg_metadata = {
                                "vector_id": len(self.message_metadata),
                                "message_id": database_id,
                                "database_id": database_id,
                                "telegram_message_id": telegram_message_id,
                                "chat_id": str(chat_id),
                                "timestamp_utc": timestamp,
                                "metadata": {
                                    "embedding_model": "default",
                                    "text_content_preview": content[:100] if content else None,
                                },
                            }
                            self.index.add(emb)
                            self.message_metadata.append(msg_metadata)
                    except Exception as e:
                        logger.error(f"Error processing message {database_id}: {e}")

            faiss.write_index(self.index, self.index_path)
            with open(f"{self.index_path}.ids.pkl", "wb") as f:
                pickle.dump(self.message_metadata, f)

            logger.info(
                f"Built index with {len(self.message_metadata)} messages from {len(set([m['chat_id'] for m in self.message_metadata])) if self.message_metadata else 0} chats"
            )
            return True

        try:
            return self._with_retry(build_operation)
        except Exception as e:
            logger.error(f"Error building index from chats after retries: {e}")
            return False
        finally:
            if conn:
                conn.close()

    def sync_with_database(self, chat_ids: Optional[List[str]] = None) -> bool:
        if not ENABLE_EMBEDDING:
            logger.info("Embedding is disabled, skipping FAISS index synchronization.")
            return True

        conn = None

        def sync_operation():
            nonlocal conn
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            indexed_msg_ids = set(
                int(m.get("database_id", m.get("message_id")))
                for m in self.message_metadata
                if m.get("database_id", m.get("message_id")) is not None
            )
            synced_message_ids = []

            query = """
                SELECT m.id, m.message_id, m.content, m.chat_id, m.date
                FROM messages m
                WHERE m.content IS NOT NULL AND m.content != ''
            """

            if chat_ids:
                placeholders = ",".join("?" * len(chat_ids))
                query += f" AND m.chat_id IN ({placeholders})"

            cursor.execute(query, chat_ids or [])
            rows = cursor.fetchall()

            added_count = 0
            for database_id, telegram_message_id, content, chat_id, date in rows:
                if content and content.strip() and database_id not in indexed_msg_ids:
                    success = self.add_message(
                        database_id,
                        content,
                        str(chat_id),
                        {
                            "date": date,
                            "database_id": database_id,
                            "telegram_message_id": telegram_message_id,
                        },
                    )
                    if success:
                        added_count += 1
                        synced_message_ids.append(database_id)

            if not self._flush_pending():
                return False

            for message_db_id in synced_message_ids:
                mark_message_as_embedded(message_db_id)
            logger.info(f"Synchronized index with database, added {added_count} new messages")
            return True

        try:
            return self._with_retry(sync_operation)
        except Exception as e:
            logger.error(f"Error synchronizing index with database after retries: {e}")
            return False
        finally:
            if conn:
                conn.close()

    def get_index_status(self) -> Dict:
        def status_operation():
            chats_indexed = list(
                set(m["chat_id"] for m in self.message_metadata if m.get("chat_id"))
            )
            return {
                "total_vectors": len(self.message_metadata),
                "index_size": self.index.ntotal if hasattr(self.index, "ntotal") else 0,
                "chats_indexed": chats_indexed,
                "chats_count": len(chats_indexed),
                "last_sync_time": getattr(self, "_last_sync_time", None),
                "pending_additions": len(self.pending_additions),
            }

        try:
            return self._with_retry(status_operation)
        except Exception as e:
            logger.error(f"Failed to get index status after retries: {e}")
            return {
                "total_vectors": 0,
                "index_size": 0,
                "chats_indexed": [],
                "chats_count": 0,
                "last_sync_time": None,
                "pending_additions": 0,
                "error": str(e),
            }


VectorDB = FAISSManager
FAISSManager.message_ids = property(
    lambda self: [m.get("message_id") for m in self.message_metadata if m.get("message_id")]
)


def get_faiss_manager() -> FAISSManager:
    """Return a shared FAISS manager instance for the process."""
    global _FAISS_MANAGER
    if _FAISS_MANAGER is None:
        _FAISS_MANAGER = FAISSManager()
    return _FAISS_MANAGER
