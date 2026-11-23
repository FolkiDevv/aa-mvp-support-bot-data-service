"""Промпты в БД агента. Чистые функции над `Session` — без HTTP."""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from support_bot_data.db import PromptRow
from support_bot_data.schemas import Prompt, PromptUpdate


class PromptNotFoundError(LookupError):
    """Промпта с таким ключом нет."""


class VersionConflictError(Exception):
    """`expected_version` не совпал с текущей версией промпта."""


def list_prompts(session: Session) -> list[Prompt]:
    """Все промпты по ключу."""
    rows = session.scalars(select(PromptRow).order_by(PromptRow.key))
    return [Prompt.model_validate(row) for row in rows]


def get_prompt(session: Session, key: str) -> Prompt:
    """Промпт по ключу.

    Raises:
        PromptNotFoundError: промпта нет.
    """
    row = session.get(PromptRow, key)
    if row is None:
        raise PromptNotFoundError(key)
    return Prompt.model_validate(row)


def update_prompt(
    session: Session,
    key: str,
    change: PromptUpdate,
    *,
    now: datetime,
) -> Prompt:
    """Сохранить новую редакцию атомарно (UPDATE ... WHERE version = ?).

    Raises:
        PromptNotFoundError: промпта нет.
        VersionConflictError: промпт уже изменили.
    """
    statement = (
        update(PromptRow)
        .where(PromptRow.key == key)
        .where(PromptRow.version == change.expected_version)
        .values(
            text=change.text,
            version=PromptRow.version + 1,
            updated_at=now,
        )
        .returning(PromptRow)
    )
    row = session.scalars(statement).one_or_none()
    if row is None:
        session.rollback()
        current = get_prompt(session, key)
        msg = (
            f'Prompt {key!r} has version {current.version}, '
            f'expected {change.expected_version}'
        )
        raise VersionConflictError(msg)
    prompt = Prompt.model_validate(row)
    session.commit()
    return prompt
