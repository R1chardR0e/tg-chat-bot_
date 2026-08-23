"""Точка запуска HTTP API."""

import argparse
import logging

import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Запустить API семантического поиска."""
    parser = argparse.ArgumentParser(description="Запустить API поиска по FAISS-индексу")
    parser.add_argument("--host", default="0.0.0.0", help="Адрес для подключения")
    parser.add_argument("--port", type=int, default=8000, help="Порт сервера")
    parser.add_argument("--reload", action="store_true", help="Перезапускать при изменениях")

    args = parser.parse_args()

    logger.info("Запуск API поиска на %s:%s", args.host, args.port)

    uvicorn.run(
        "api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
