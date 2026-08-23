import importlib
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def api_context(tmp_path_factory: pytest.TempPathFactory):
    runtime_path = tmp_path_factory.mktemp("api-runtime")
    test_environment = {
        "API_ACCESS_TOKEN": "test-api-token",
        "ENABLE_EMBEDDING": "false",
        "EMBEDDING_DIM": "3",
        "EMBEDDING_MODEL": "test-embedding-model",
        "IO_NET_API_KEY": "test-io-key",
        "API_URL": "https://example.invalid/v1/",
        "MODEL_NAME": "test-model",
        "DB_PATH": str(runtime_path / "chat.db"),
        "VECTOR_DB_PATH": str(runtime_path / "chat.index"),
    }
    previous_environment = {key: os.environ.get(key) for key in test_environment}
    os.environ.update(test_environment)

    api_app = importlib.import_module("api.app")
    client = TestClient(api_app.app)

    yield api_app, client

    client.close()
    database_pool = importlib.import_module("database.db_pool")
    database_pool._pool.close_all()
    for key, previous_value in previous_environment.items():
        if previous_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous_value


def test_api_rejects_missing_token(api_context) -> None:
    _, client = api_context
    response = client.get("/")

    assert response.status_code == 401
    assert response.json() == {"detail": "Неверный ключ доступа"}


def test_root_returns_service_information(api_context) -> None:
    _, client = api_context
    response = client.get("/", headers={"X-API-Key": "test-api-token"})

    assert response.status_code == 200
    assert response.json() == {
        "message": "API семантического поиска TG Chat Bot",
        "version": "1.0.0",
    }


def test_search_is_disabled_without_embeddings(api_context) -> None:
    _, client = api_context
    response = client.post(
        "/api/v1/search",
        headers={"X-API-Key": "test-api-token"},
        json={"query": "проверка"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Семантический поиск отключён (ENABLE_EMBEDDING=0)"}


def test_public_api_routes_are_preserved(api_context) -> None:
    api_app, _ = api_context
    paths = api_app.app.openapi()["paths"]

    assert {
        "/",
        "/api/v1/index/status",
        "/api/v1/index/sync",
        "/api/v1/search",
        "/api/v1/search/{chat_id}",
    } <= set(paths)
