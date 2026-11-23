"""Синхронный mTLS-клиент data-service Support Bot."""

import ssl
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from types import TracebackType
from typing import Final, Self

import httpx
from pydantic import BaseModel, TypeAdapter, ValidationError

from support_bot_data_client.models import (
    DailyStats,
    Prompt,
    PromptUpdate,
    Summary,
)


class DataServiceError(Exception):
    """Базовая ошибка клиента."""


class NotFoundError(DataServiceError):
    """Запрошенный объект не найден (404)."""


class ConflictError(DataServiceError):
    """Объект изменился с момента чтения (409)."""


class DataServiceUnavailableError(DataServiceError):
    """Сервис недоступен, отказал в TLS или вернул некорректный ответ."""


@dataclass(frozen=True, slots=True, kw_only=True)
class TlsConfig:
    """Файлы mTLS: сертификат и ключ клиента + CA сервера."""

    cert_file: Path
    key_file: Path
    ca_file: Path

    def ssl_context(self) -> ssl.SSLContext:
        """Собрать SSL-контекст для httpx."""
        context = ssl.create_default_context(cafile=str(self.ca_file))
        context.load_cert_chain(str(self.cert_file), str(self.key_file))
        return context


_ERROR_SNIPPET: Final = 200
_PROMPT = TypeAdapter(Prompt)
_PROMPTS = TypeAdapter(list[Prompt])
_DAILY = TypeAdapter(list[DailyStats])
_SUMMARY = TypeAdapter(Summary)


class SupportBotDataClient:
    """Типизированный клиент. Все ошибки — наследники `DataServiceError`.

    В проде создаётся через `SupportBotDataClient.connect(...)`;
    в тестах можно передать любой `httpx.Client` (например,
    `litestar.testing.TestClient`).
    """

    def __init__(self, http: httpx.Client) -> None:
        """Обернуть готовый HTTP-клиент."""
        self._http = http

    @classmethod
    def connect(
        cls,
        base_url: str,
        *,
        tls: TlsConfig | None,
        timeout: float = 5.0,
    ) -> Self:
        """Создать клиент; `tls=None` допустим только для локальной отладки."""
        verify: ssl.SSLContext | bool = tls.ssl_context() if tls else True
        return cls(
            httpx.Client(base_url=base_url, verify=verify, timeout=timeout)
        )

    def __enter__(self) -> Self:
        """Использовать как контекстный менеджер."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Закрыть соединения."""
        self.close()

    def close(self) -> None:
        """Закрыть соединения."""
        self._http.close()

    def list_prompts(self) -> list[Prompt]:
        """Все промпты агента."""
        return _parse(_PROMPTS, self._request('GET', '/prompts'))

    def get_prompt(self, key: str) -> Prompt:
        """Промпт по ключу."""
        return _parse(_PROMPT, self._request('GET', f'/prompts/{key}'))

    def update_prompt(self, key: str, update: PromptUpdate) -> Prompt:
        """Сохранить новую редакцию промпта.

        Raises:
            ConflictError: промпт уже изменил кто-то другой.
            NotFoundError: промпта нет.
        """
        content = self._request('PUT', f'/prompts/{key}', body=update)
        return _parse(_PROMPT, content)

    def daily_stats(self, days: int) -> list[DailyStats]:
        """Агрегаты по дням за последние `days` дней."""
        content = self._request('GET', '/analytics/daily', days=days)
        return _parse(_DAILY, content)

    def summary(self, days: int) -> Summary:
        """Агрегаты за последние `days` дней."""
        content = self._request('GET', '/analytics/summary', days=days)
        return _parse(_SUMMARY, content)

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: BaseModel | None = None,
        days: int | None = None,
    ) -> bytes:
        params = None if days is None else {'days': str(days)}
        content = body.model_dump_json().encode() if body else None
        headers = {'Content-Type': 'application/json'} if body else None
        try:
            response = self._http.request(
                method,
                path,
                params=params,
                content=content,
                headers=headers,
            )
        except httpx.HTTPError as error:
            raise DataServiceUnavailableError(str(error)) from error
        _raise_for_status(response)
        return response.content


def _raise_for_status(response: httpx.Response) -> None:
    status = response.status_code
    if status == HTTPStatus.NOT_FOUND:
        raise NotFoundError(response.text)
    if status == HTTPStatus.CONFLICT:
        raise ConflictError(response.text)
    if status != HTTPStatus.OK:
        snippet = response.text[:_ERROR_SNIPPET]
        msg = f'Unexpected status {status}: {snippet}'
        raise DataServiceUnavailableError(msg)


def _parse[ModelT](adapter: TypeAdapter[ModelT], content: bytes) -> ModelT:
    try:
        return adapter.validate_json(content)
    except ValidationError as error:
        msg = f'Invalid response: {error}'
        raise DataServiceUnavailableError(msg) from error
