"""HTTP API семантического поиска по сообщениям."""

import time
import uuid

from fastapi import Depends, FastAPI, Header, HTTPException, Path
from pydantic import BaseModel

from config import API_ACCESS_TOKEN, ENABLE_EMBEDDING
from embeddings.vector_db import get_faiss_manager
from utils.logger import logger


def require_api_token(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    if not API_ACCESS_TOKEN:
        raise HTTPException(status_code=503, detail="API-ключ не настроен")
    if x_api_key != API_ACCESS_TOKEN:
        raise HTTPException(status_code=401, detail="Неверный ключ доступа")


app = FastAPI(
    title="API семантического поиска TG Chat Bot",
    description="Поиск сообщений и управление FAISS-индексом нескольких чатов",
    version="1.0.0",
    dependencies=[Depends(require_api_token)],
)

faiss_manager = get_faiss_manager()


class SearchRequest(BaseModel):
    query: str
    top_k: int | None = 10
    min_similarity: float | None = 0.0


class SearchResult(BaseModel):
    message_id: int
    chat_id: str
    text: str
    similarity_score: float
    timestamp: str
    metadata: dict | None = None


class SearchResponse(BaseModel):
    results: list[SearchResult]
    query_time_ms: float | None = None
    total_results: int


class IndexStatusResponse(BaseModel):
    total_vectors: int
    last_sync_time: str | None = None
    sync_status: str = "idle"
    chats_indexed: list[str]
    index_memory_mb: float | None = None


class SyncResponse(BaseModel):
    sync_id: str
    status: str
    message: str


@app.post("/api/v1/search", response_model=SearchResponse)
async def search_messages(request: SearchRequest):
    if not ENABLE_EMBEDDING:
        raise HTTPException(
            status_code=503,
            detail="Семантический поиск отключён (ENABLE_EMBEDDING=0)",
        )

    start_time = time.time()
    try:
        if not request.query or not request.query.strip():
            raise HTTPException(status_code=400, detail="Укажите текст запроса")
        if request.top_k and (request.top_k < 1 or request.top_k > 100):
            raise HTTPException(status_code=400, detail="top_k должен быть от 1 до 100")

        results = faiss_manager.search_similar_messages(
            query_text=request.query, top_k=request.top_k
        )

        processed_results = []
        for result in results:
            distance = result.get("distance", 0.0)
            similarity = 1.0 / (1.0 + distance) if distance > 0 else 1.0
            min_sim = request.min_similarity or 0.0
            if similarity >= min_sim:
                processed_results.append(
                    SearchResult(
                        message_id=result["message_id"],
                        chat_id=result["chat_id"],
                        text=result["content"],
                        similarity_score=similarity,
                        timestamp=result.get("date", ""),
                        metadata={
                            "username": result.get("username"),
                            "database_id": result.get("database_id"),
                        }
                        if result.get("username") or result.get("database_id") is not None
                        else None,
                    )
                )

        query_time_ms = (time.time() - start_time) * 1000
        return SearchResponse(
            results=processed_results[: request.top_k],
            query_time_ms=query_time_ms,
            total_results=len(processed_results),
        )
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Ошибка поиска: {error}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера") from error


@app.post("/api/v1/search/{chat_id}", response_model=SearchResponse)
async def search_in_chat(
    chat_id: str = Path(..., description="ID чата для поиска"),
    request: SearchRequest = ...,
):
    if not ENABLE_EMBEDDING:
        raise HTTPException(
            status_code=503,
            detail="Семантический поиск отключён (ENABLE_EMBEDDING=0)",
        )

    start_time = time.time()
    try:
        if not request.query or not request.query.strip():
            raise HTTPException(status_code=400, detail="Укажите текст запроса")

        results = faiss_manager.search_similar_messages(
            query_text=request.query,
            chat_id=chat_id,
            top_k=request.top_k,
        )

        processed_results = []
        for result in results:
            distance = result.get("distance", 0.0)
            similarity = 1.0 / (1.0 + distance) if distance > 0 else 1.0
            min_sim = request.min_similarity or 0.0
            if similarity >= min_sim:
                processed_results.append(
                    SearchResult(
                        message_id=result["message_id"],
                        chat_id=result["chat_id"],
                        text=result["content"],
                        similarity_score=similarity,
                        timestamp=result.get("date", ""),
                        metadata={
                            "username": result.get("username"),
                            "database_id": result.get("database_id"),
                        }
                        if result.get("username") or result.get("database_id") is not None
                        else None,
                    )
                )

        query_time_ms = (time.time() - start_time) * 1000
        return SearchResponse(
            results=processed_results[: request.top_k],
            query_time_ms=query_time_ms,
            total_results=len(processed_results),
        )
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Ошибка поиска: {error}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера") from error


@app.get("/api/v1/index/status", response_model=IndexStatusResponse)
async def get_index_status():
    try:
        status = faiss_manager.get_index_status()
        return IndexStatusResponse(
            total_vectors=status.get("total_vectors", 0),
            last_sync_time=status.get("last_sync_time"),
            sync_status=status.get("sync_status", "idle"),
            chats_indexed=status.get("chats_indexed", []),
            index_memory_mb=status.get("index_memory_mb"),
        )
    except Exception as error:
        logger.error(f"Ошибка получения состояния индекса: {error}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера") from error


@app.post("/api/v1/index/sync", response_model=SyncResponse)
async def sync_index():
    try:
        sync_id = str(uuid.uuid4())
        success = faiss_manager.sync_with_database()
        return SyncResponse(
            sync_id=sync_id,
            status="completed" if success else "failed",
            message="Синхронизация индекса завершена",
        )
    except Exception as error:
        logger.error(f"Ошибка синхронизации индекса: {error}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера") from error


@app.get("/")
async def root():
    return {"message": "API семантического поиска TG Chat Bot", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
