from datetime import datetime

import pytest
from litestar import Litestar
from litestar.testing import TestClient
from sqlalchemy import Engine

from support_bot_data import repository
from support_bot_data.app import create_app

type Client = TestClient[Litestar]


def test_list_prompts_sorted_by_key(client: Client) -> None:
    response = client.get('/prompts')

    assert response.status_code == 200
    assert [item['key'] for item in response.json()] == ['greeting', 'system']
    assert response.json()[1] == {
        'key': 'system',
        'title': 'System',
        'text': 'You are helpful',
        'version': 3,
        'updated_at': '2026-11-01T09:30:00Z',
    }


def test_get_prompt(client: Client) -> None:
    assert client.get('/prompts/greeting').json()['text'] == 'Hi!'


def test_missing_prompt_not_found(client: Client) -> None:
    response = client.get('/prompts/missing')

    assert response.status_code == 404
    assert response.json() == {'detail': 'Prompt missing not found'}


def test_update_prompt_bumps_version(client: Client, now: datetime) -> None:
    response = client.put(
        '/prompts/system',
        json={'text': 'Be concise', 'expected_version': 3},
    )

    assert response.status_code == 200
    assert response.json() == {
        'key': 'system',
        'title': 'System',
        'text': 'Be concise',
        'version': 4,
        'updated_at': now.isoformat().replace('+00:00', 'Z'),
    }
    assert client.get('/prompts/system').json()['version'] == 4


def test_stale_version_conflicts(client: Client) -> None:
    body = {'text': 'Mine', 'expected_version': 3}
    assert client.put('/prompts/system', json=body).status_code == 200

    response = client.put('/prompts/system', json=body)

    assert response.status_code == 409
    assert response.json() == {
        'detail': "Prompt 'system' has version 4, expected 3",
    }
    assert client.get('/prompts/system').json()['text'] == 'Mine'


def test_update_missing_prompt(client: Client) -> None:
    response = client.put(
        '/prompts/missing',
        json={'text': 'x', 'expected_version': 1},
    )

    assert response.status_code == 404
    assert set(response.json()) == {'detail'}


@pytest.mark.parametrize(
    'body',
    [
        {'text': '', 'expected_version': 3},
        {'text': 'x', 'expected_version': 0},
        {'text': 'x'},
        {'text': 'x', 'expected_version': 3, 'extra': True},
    ],
)
def test_invalid_update_rejected(
    client: Client, body: dict[str, object]
) -> None:
    response = client.put('/prompts/system', json=body)

    assert response.status_code == 400
    assert set(response.json()) == {'detail'}
    assert 'Validation failed' in response.json()['detail']


def test_daily_stats_fill_empty_days(client: Client) -> None:
    response = client.get('/analytics/daily', params={'days': 7})

    assert response.status_code == 200
    days = response.json()
    assert [item['day'] for item in days][:2] == ['2026-11-17', '2026-11-18']
    assert days[-3:] == [
        {
            'day': '2026-11-21',
            'conversations': 1,
            'resolved': 1,
            'avg_rating': 3.0,
            'tokens': 1000,
        },
        {
            'day': '2026-11-22',
            'conversations': 0,
            'resolved': 0,
            'avg_rating': None,
            'tokens': 0,
        },
        {
            'day': '2026-11-23',
            'conversations': 2,
            'resolved': 1,
            'avg_rating': 5.0,
            'tokens': 110,
        },
    ]
    assert len(days) == 7


@pytest.mark.parametrize(
    ('days', 'expected'),
    [
        (
            7,
            {
                'period_days': 7,
                'conversations': 3,
                'resolved_rate': 2 / 3,
                'avg_rating': 4.0,
                'tokens': 1110,
            },
        ),
        (
            30,
            {
                'period_days': 30,
                'conversations': 4,
                'resolved_rate': 0.5,
                'avg_rating': 3.0,
                'tokens': 1111,
            },
        ),
        (
            1,
            {
                'period_days': 1,
                'conversations': 2,
                'resolved_rate': 0.5,
                'avg_rating': 5.0,
                'tokens': 110,
            },
        ),
    ],
)
def test_summary(
    client: Client, days: int, expected: dict[str, object]
) -> None:
    response = client.get('/analytics/summary', params={'days': days})

    assert response.status_code == 200
    assert response.json() == expected


def test_summary_of_empty_period(engine: Engine, now: datetime) -> None:
    far_future = now.replace(year=2030)
    app = create_app(engine, clock=lambda: far_future)
    with TestClient(app) as client:
        summary = client.get('/analytics/summary?days=5').json()

    assert summary == {
        'period_days': 5,
        'conversations': 0,
        'resolved_rate': 0,
        'avg_rating': None,
        'tokens': 0,
    }


@pytest.mark.parametrize('path', ['/analytics/daily', '/analytics/summary'])
@pytest.mark.parametrize('query', ['days=0', 'days=366', 'days=x', ''])
def test_days_are_validated(client: Client, path: str, query: str) -> None:
    response = client.get(f'{path}?{query}')

    assert response.status_code == 400
    assert set(response.json()) == {'detail'}


def test_unknown_route_has_detail(client: Client) -> None:
    response = client.delete('/prompts/system')

    assert response.status_code == 405
    assert set(response.json()) == {'detail'}


def test_unexpected_error_hides_details(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def explode(*args: object) -> None:
        raise RuntimeError('db password leaked')

    monkeypatch.setattr(repository, 'list_prompts', explode)

    response = client.get('/prompts')

    assert response.status_code == 500
    assert response.json() == {'detail': 'Internal server error'}
    assert 'Request failed' in caplog.text


def test_openapi_schema_is_published(client: Client) -> None:
    schema = client.get('/schema/openapi.json').json()

    assert '/prompts/{key}' in schema['paths']
    assert 'PromptUpdate' in schema['components']['schemas']


def test_default_clock_is_utc_now(engine: Engine) -> None:
    with TestClient(create_app(engine)) as client:
        summary = client.get('/analytics/summary?days=1').json()

    assert summary['period_days'] == 1
