"""Модели API data-service (pydantic).

Форма совпадает с DTO пакета `support-bot-data-client`; сервис его не
импортирует (границу проверяет import-linter), совпадение проверяет
контрактный тест клиента против этого сервиса.
"""

from datetime import UTC, date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_DAYS = 365


class _Schema(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra='forbid',
        from_attributes=True,
    )


class Prompt(_Schema):
    """Промпт агента."""

    key: str
    title: str
    text: str
    version: int = Field(ge=1)
    updated_at: datetime

    @field_validator('updated_at')
    @classmethod
    def _as_utc(cls, value: datetime) -> datetime:
        """SQLite отдаёт naive-время; в БД оно всегда UTC."""
        return value if value.tzinfo else value.replace(tzinfo=UTC)


class PromptUpdate(_Schema):
    """Новая редакция промпта (оптимистическая блокировка по версии)."""

    text: str = Field(min_length=1)
    expected_version: int = Field(ge=1)


class DailyStats(_Schema):
    """Агрегаты диалогов за день."""

    day: date
    conversations: int = Field(ge=0)
    resolved: int = Field(ge=0)
    avg_rating: float | None
    tokens: int = Field(ge=0)


class Summary(_Schema):
    """Агрегаты диалогов за период."""

    period_days: int = Field(ge=1, le=MAX_DAYS)
    conversations: int = Field(ge=0)
    resolved_rate: float = Field(ge=0, le=1)
    avg_rating: float | None
    tokens: int = Field(ge=0)


class ErrorBody(_Schema):
    """Тело любого ответа с ошибкой."""

    detail: str
