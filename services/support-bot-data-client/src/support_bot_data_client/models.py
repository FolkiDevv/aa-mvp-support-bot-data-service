"""DTO data-service Support Bot — контракт между сервисом и модулем.

HTTP API сервиса (все запросы — только по mTLS):

====== ============================ ================ =====================
Метод  Путь                         Тело             Ответ
====== ============================ ================ =====================
GET    /prompts                     —                200 list[Prompt]
GET    /prompts/{key}               —                200 Prompt / 404
PUT    /prompts/{key}               PromptUpdate     200 Prompt / 404 / 409
GET    /analytics/daily?days=N      —                200 list[DailyStats]
GET    /analytics/summary?days=N    —                200 Summary
====== ============================ ================ =====================

`days` — от 1 до 365. 409 — `expected_version` не совпал с текущей
версией промпта (оптимистическая блокировка). Тела ошибок —
`{"detail": "..."}`.
"""

from datetime import date, datetime
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

MAX_DAYS: Final = 365


class _Dto(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')


class Prompt(_Dto):
    """Промпт агента."""

    key: str
    title: str
    text: str
    version: int = Field(ge=1)
    updated_at: datetime


class PromptUpdate(_Dto):
    """Новая редакция промпта."""

    text: str = Field(min_length=1)
    expected_version: int = Field(ge=1)


class DailyStats(_Dto):
    """Агрегаты диалогов за день."""

    day: date
    conversations: int = Field(ge=0)
    resolved: int = Field(ge=0)
    avg_rating: float | None
    tokens: int = Field(ge=0)


class Summary(_Dto):
    """Агрегаты диалогов за период."""

    period_days: int = Field(ge=1, le=MAX_DAYS)
    conversations: int = Field(ge=0)
    resolved_rate: float = Field(ge=0, le=1)
    avg_rating: float | None
    tokens: int = Field(ge=0)
