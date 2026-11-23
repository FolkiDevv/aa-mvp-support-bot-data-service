"""Клиент data-service агента Support Bot."""

from support_bot_data_client.client import (
    ConflictError,
    DataServiceError,
    DataServiceUnavailableError,
    NotFoundError,
    SupportBotDataClient,
    TlsConfig,
)
from support_bot_data_client.models import (
    MAX_DAYS,
    DailyStats,
    Prompt,
    PromptUpdate,
    Summary,
)

__all__ = (
    'MAX_DAYS',
    'ConflictError',
    'DailyStats',
    'DataServiceError',
    'DataServiceUnavailableError',
    'NotFoundError',
    'Prompt',
    'PromptUpdate',
    'Summary',
    'SupportBotDataClient',
    'TlsConfig',
)
