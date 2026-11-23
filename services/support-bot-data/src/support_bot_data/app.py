"""Litestar-приложение data-service.

====== ============================ ================ =====================
Метод  Путь                         Тело             Ответ
====== ============================ ================ =====================
GET    /prompts                     —                200 list[Prompt]
GET    /prompts/{key}               —                200 Prompt / 404
PUT    /prompts/{key}               PromptUpdate     200 Prompt / 404 / 409
GET    /analytics/daily?days=N      —                200 list[DailyStats]
GET    /analytics/summary?days=N    —                200 Summary
====== ============================ ================ =====================

`days` — от 1 до 365 (иначе 400). Тела ошибок — `{"detail": "..."}`.
Аутентификация клиента — mTLS на уровне сервера (см. `service`).
"""

import logging
from collections.abc import Callable
from datetime import UTC, date, datetime
from http import HTTPStatus
from typing import Annotated

from litestar import Litestar, Request, Response, get, put
from litestar.datastructures import State
from litestar.exceptions import HTTPException
from litestar.params import FromPath, JSONBody, QueryParameter
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from support_bot_data import analytics, repository
from support_bot_data.schemas import (
    MAX_DAYS,
    DailyStats,
    ErrorBody,
    Prompt,
    PromptUpdate,
    Summary,
)

# Обычный (не PEP 695) алиас: Litestar читает метаданные `Annotated`.
Days = Annotated[int, QueryParameter(ge=1, le=MAX_DAYS)]

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class _Api:
    """Обработчики эндпоинтов; сессия БД — на каждый запрос."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        clock: Callable[[], datetime],
    ) -> None:
        self._sessions = sessions
        self._clock = clock

    def list_prompts(self) -> list[Prompt]:
        with self._sessions() as session:
            return repository.list_prompts(session)

    def get_prompt(self, key: FromPath[str]) -> Prompt:
        with self._sessions() as session:
            return repository.get_prompt(session, key)

    def update_prompt(
        self,
        key: FromPath[str],
        data: JSONBody[PromptUpdate],
    ) -> Prompt:
        with self._sessions() as session:
            return repository.update_prompt(
                session,
                key,
                data,
                now=self._clock(),
            )

    def daily(self, days: Days) -> list[DailyStats]:
        with self._sessions() as session:
            return analytics.daily_stats(
                session,
                days=days,
                today=self._today(),
            )

    def summary(self, days: Days) -> Summary:
        with self._sessions() as session:
            return analytics.summary(session, days=days, today=self._today())

    def _today(self) -> date:
        return self._clock().astimezone(UTC).date()


def create_app(
    engine: Engine,
    *,
    clock: Callable[[], datetime] = _utc_now,
) -> Litestar:
    """Собрать приложение поверх движка БД агента.

    Args:
        engine: движок БД агента.
        clock: текущее время (aware), подменяется в тестах.
    """
    api = _Api(sessionmaker(engine, expire_on_commit=False), clock)
    handlers = [
        get('/prompts', sync_to_thread=True)(api.list_prompts),
        get('/prompts/{key:str}', sync_to_thread=True)(api.get_prompt),
        put('/prompts/{key:str}', sync_to_thread=True)(api.update_prompt),
        get('/analytics/daily', sync_to_thread=True)(api.daily),
        get('/analytics/summary', sync_to_thread=True)(api.summary),
    ]
    return Litestar(
        route_handlers=handlers,
        exception_handlers={Exception: _handle_error},
    )


def _status_and_detail(exc: Exception) -> tuple[HTTPStatus, str]:
    match exc:
        case repository.PromptNotFoundError():
            return HTTPStatus.NOT_FOUND, f'Prompt {exc} not found'
        case repository.VersionConflictError():
            return HTTPStatus.CONFLICT, str(exc)
        case HTTPException() if (
            exc.status_code < HTTPStatus.INTERNAL_SERVER_ERROR
        ):
            return HTTPStatus(exc.status_code), _http_detail(exc)
    logger.error('Request failed', exc_info=exc)
    return HTTPStatus.INTERNAL_SERVER_ERROR, 'Internal server error'


def _http_detail(exc: HTTPException) -> str:
    if not isinstance(exc.extra, list) or not exc.extra:
        return exc.detail
    problems = '; '.join(str(problem) for problem in exc.extra)
    return f'{exc.detail}: {problems}'


def _handle_error(
    _request: Request[object, object, State],
    exc: Exception,
) -> Response[ErrorBody]:
    status, detail = _status_and_detail(exc)
    return Response(content=ErrorBody(detail=detail), status_code=status)
