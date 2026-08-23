import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]


def test_entrypoints_import_without_external_calls(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "API_ACCESS_TOKEN": "test-api-token",
            "API_URL": "https://example.invalid/v1/",
            "BOT_TOKEN": "123456:test-token",
            "DB_PATH": str(tmp_path / "chat.db"),
            "EMBEDDING_DIM": "3",
            "EMBEDDING_MODEL": "test-embedding-model",
            "ENABLE_EMBEDDING": "false",
            "ENABLE_LEARNING": "false",
            "IO_NET_API_KEY": "test-io-key",
            "MODEL_NAME": "test-model",
            "VECTOR_DB_PATH": str(tmp_path / "chat.index"),
        }
    )

    result = subprocess.run(
        [sys.executable, "-c", "import bot; import api.server"],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
