import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]


def run_config_probe(environment: dict[str, str]) -> list[str]:
    env = os.environ.copy()
    env.update(environment)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import config; "
                "print(config.DB_PATH); "
                "print(config.VECTOR_DB_PATH); "
                "print(config.API_PROVIDER); "
                "print(config.CHAT_IDS)"
            ),
        ],
        cwd=PROJECT_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip().splitlines()


def test_relative_data_paths_are_resolved_from_project_root() -> None:
    lines = run_config_probe(
        {
            "DB_PATH": "runtime/test.db",
            "VECTOR_DB_PATH": "runtime/test.index",
            "API_PROVIDER": "MISTRAL",
            "CHAT_IDS": "-1001, 2002",
        }
    )

    assert Path(lines[0]) == PROJECT_ROOT / "runtime" / "test.db"
    assert Path(lines[1]) == PROJECT_ROOT / "runtime" / "test.index"
    assert lines[2] == "mistral"
    assert lines[3] == "[-1001, 2002]"
