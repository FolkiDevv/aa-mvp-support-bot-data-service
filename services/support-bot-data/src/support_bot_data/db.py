"""Схема БД агента (SQLAlchemy 2) и создание движка.

Это «БД агента»: в проде она уже существует и принадлежит команде агента,
data-service лишь читает/пишет её. `create_schema` нужен для dev/тестов.
"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Engine,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

DEFAULT_DATABASE_URL = 'sqlite:///support_bot_data.sqlite3'
_IN_MEMORY_URLS = frozenset(('sqlite://', 'sqlite:///:memory:'))
KEY_LENGTH = 64
TITLE_LENGTH = 200

# Время пишется aware-UTC. SQLite пояс не хранит и отдаёт naive —
# схемы API (`schemas`) трактуют naive как UTC.
_UtcDateTime = DateTime(timezone=True)


class Base(DeclarativeBase):
    """Базовый класс моделей БД агента."""


class PromptRow(Base):
    """Промпт агента; `version` растёт при каждом сохранении."""

    __tablename__ = 'prompts'

    key: Mapped[str] = mapped_column(String(KEY_LENGTH), primary_key=True)
    title: Mapped[str] = mapped_column(String(TITLE_LENGTH))
    text: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[datetime] = mapped_column(_UtcDateTime)


class ConversationRow(Base):
    """Диалог агента с пользователем (для аналитики)."""

    __tablename__ = 'conversations'
    __table_args__ = (
        CheckConstraint(
            'rating IS NULL OR rating BETWEEN 1 AND 5',
            name='rating_range',
        ),
        CheckConstraint('tokens >= 0', name='tokens_non_negative'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(_UtcDateTime, index=True)
    resolved: Mapped[bool] = mapped_column(default=False)
    rating: Mapped[int | None]
    tokens: Mapped[int] = mapped_column(default=0)


def make_engine(url: str = DEFAULT_DATABASE_URL) -> Engine:
    """Движок БД; для SQLite — с доступом из пула потоков Litestar."""
    if not url.startswith('sqlite'):
        return create_engine(url)
    connect_args = {'check_same_thread': False}
    if url in _IN_MEMORY_URLS:
        return create_engine(
            url,
            connect_args=connect_args,
            poolclass=StaticPool,
        )
    return create_engine(url, connect_args=connect_args)


def create_schema(engine: Engine) -> None:
    """Создать таблицы, если их нет (dev и тесты)."""
    Base.metadata.create_all(engine)
