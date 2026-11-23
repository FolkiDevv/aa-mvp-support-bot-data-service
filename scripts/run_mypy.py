"""Запустить mypy отдельно для каждого проекта workspace внутри путей.

У каждого проекта свои `tests/` и `conftest.py`, поэтому общий запуск
mypy дал бы конфликт имён модулей. Проект со своей секцией
`[tool.mypy]` (ядро с django-плагином) проверяется своим конфигом.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROOT_CONFIG = ROOT / 'pyproject.toml'


def _is_project(pyproject: Path) -> bool:
    ignored = {'.venv', 'templates'}
    return not ignored.intersection(pyproject.parts)


def _projects(paths: list[str]) -> list[Path]:
    pyprojects = {
        pyproject.parent
        for raw in paths
        for pyproject in (ROOT / raw).resolve().rglob('pyproject.toml')
        if _is_project(pyproject)
    }
    pyprojects.discard(ROOT)
    return sorted(pyprojects)


def _check(project: Path) -> int:
    own = project / 'pyproject.toml'
    config = own if '[tool.mypy]' in own.read_text() else ROOT_CONFIG
    sys.stdout.write(f'mypy {project.relative_to(ROOT)}\n')
    command = [sys.executable, '-m', 'mypy', '--config-file', str(config), '.']
    return subprocess.run(command, cwd=project, check=False).returncode  # noqa: S603


def main() -> int:
    """Вернуть ненулевой код, если mypy упал хотя бы в одном проекте."""
    paths = sys.argv[1:] or ['.']
    codes = [_check(project) for project in _projects(paths)]
    return max(codes, default=0)


if __name__ == '__main__':
    sys.exit(main())
