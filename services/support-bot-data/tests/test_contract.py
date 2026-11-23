"""Контракт: настоящий клиент data-service против настоящего сервиса."""

from datetime import datetime

import pytest
from litestar import Litestar
from litestar.testing import TestClient

from support_bot_data_client import (
    ConflictError,
    DataServiceUnavailableError,
    NotFoundError,
    PromptUpdate,
    SupportBotDataClient,
)

type Client = TestClient[Litestar]


@pytest.fixture
def data_client(client: Client) -> SupportBotDataClient:
    return SupportBotDataClient(client)


def test_prompts(data_client: SupportBotDataClient, now: datetime) -> None:
    prompts = data_client.list_prompts()
    system = data_client.get_prompt('system')
    updated = data_client.update_prompt(
        'system',
        PromptUpdate(text='Be brief', expected_version=system.version),
    )

    assert [prompt.key for prompt in prompts] == ['greeting', 'system']
    assert system.version == 3
    assert updated.version == 4
    assert updated.text == 'Be brief'
    assert updated.updated_at == now
    assert data_client.get_prompt('system') == updated


def test_conflict_and_not_found(data_client: SupportBotDataClient) -> None:
    stale = PromptUpdate(text='x', expected_version=1)

    with pytest.raises(ConflictError):
        data_client.update_prompt('system', stale)
    with pytest.raises(NotFoundError):
        data_client.update_prompt('missing', stale)
    with pytest.raises(NotFoundError):
        data_client.get_prompt('missing')


def test_analytics(data_client: SupportBotDataClient) -> None:
    daily = data_client.daily_stats(7)
    summary = data_client.summary(7)

    assert len(daily) == 7
    assert daily[-1].conversations == 2
    assert daily[-2].avg_rating is None
    assert summary.conversations == sum(day.conversations for day in daily)
    assert summary.tokens == sum(day.tokens for day in daily)
    assert summary.avg_rating == pytest.approx(4.0)


def test_out_of_range_days(data_client: SupportBotDataClient) -> None:
    with pytest.raises(DataServiceUnavailableError, match='400'):
        data_client.summary(0)
