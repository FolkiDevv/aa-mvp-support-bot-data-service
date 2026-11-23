import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from support_bot_data_client import (
    ConflictError,
    DataServiceUnavailableError,
    NotFoundError,
    PromptUpdate,
    SupportBotDataClient,
    TlsConfig,
)

PROMPT = {
    'key': 'system',
    'title': 'System',
    'text': 'You are helpful',
    'version': 3,
    'updated_at': '2026-11-01T10:00:00Z',
}
DAY = {
    'day': '2026-11-01',
    'conversations': 10,
    'resolved': 7,
    'avg_rating': 4.5,
    'tokens': 1000,
}
SUMMARY = {
    'period_days': 7,
    'conversations': 70,
    'resolved_rate': 0.7,
    'avg_rating': None,
    'tokens': 7000,
}

type Handler = Callable[[httpx.Request], httpx.Response]


def make_client(handler: Handler) -> SupportBotDataClient:
    http = httpx.Client(
        base_url='https://data.test',
        transport=httpx.MockTransport(handler),
    )
    return SupportBotDataClient(http)


def routes(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == '/prompts':
        return httpx.Response(200, json=[PROMPT])
    if path == '/prompts/system' and request.method == 'GET':
        return httpx.Response(200, json=PROMPT)
    if path == '/prompts/system' and request.method == 'PUT':
        body = json.loads(request.content)
        if body['expected_version'] != PROMPT['version']:
            return httpx.Response(409, json={'detail': 'conflict'})
        return httpx.Response(
            200, json={**PROMPT, 'text': body['text'], 'version': 4}
        )
    if path == '/analytics/daily':
        assert request.url.params['days'] == '7'
        return httpx.Response(200, json=[DAY])
    if path == '/analytics/summary':
        return httpx.Response(200, json=SUMMARY)
    return httpx.Response(404, json={'detail': 'not found'})


def test_happy_path() -> None:
    with make_client(routes) as client:
        assert client.list_prompts()[0].key == 'system'
        assert client.get_prompt('system').version == 3
        updated = client.update_prompt(
            'system',
            PromptUpdate(text='New', expected_version=3),
        )
        assert updated.text == 'New'
        assert updated.version == 4
        assert client.daily_stats(7)[0].resolved == 7
        assert client.summary(7).avg_rating is None


def test_errors_are_mapped() -> None:
    client = make_client(routes)

    with pytest.raises(NotFoundError):
        client.get_prompt('missing')
    with pytest.raises(ConflictError):
        client.update_prompt(
            'system', PromptUpdate(text='x', expected_version=1)
        )


@pytest.mark.parametrize(
    'handler',
    [
        lambda _: httpx.Response(500, text='boom'),
        lambda _: httpx.Response(200, json={'unexpected': True}),
    ],
)
def test_bad_responses(handler: Handler) -> None:
    with pytest.raises(DataServiceUnavailableError):
        make_client(handler).summary(7)


def test_network_error() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError('refused', request=request)

    with pytest.raises(DataServiceUnavailableError):
        make_client(fail).list_prompts()


def test_connect_without_tls() -> None:
    client = SupportBotDataClient.connect('https://data.test', tls=None)
    client.close()


def test_tls_config_requires_existing_files(tmp_path: Path) -> None:
    tls = TlsConfig(
        cert_file=tmp_path / 'c.pem',
        key_file=tmp_path / 'k.pem',
        ca_file=tmp_path / 'ca.pem',
    )

    with pytest.raises(OSError, match=r'.'):
        tls.ssl_context()
