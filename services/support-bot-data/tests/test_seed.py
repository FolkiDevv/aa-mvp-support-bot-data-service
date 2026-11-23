from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from support_bot_data import analytics, repository
from support_bot_data.db import ConversationRow, make_engine
from support_bot_data.seed import DEFAULT_DAYS, PROMPTS, main, seed_engine

TODAY = date(2026, 11, 23)

type Call = tuple[str, dict[str, object]]


def snapshot(url: str) -> list[tuple[object, ...]]:
    with Session(make_engine(url)) as session:
        rows = session.execute(
            select(
                ConversationRow.started_at,
                ConversationRow.resolved,
                ConversationRow.rating,
                ConversationRow.tokens,
            ).order_by(ConversationRow.id),
        )
        return [tuple(row) for row in rows]


def test_seed_is_deterministic_and_idempotent(tmp_path: Path) -> None:
    first = f'sqlite:///{tmp_path / "a.sqlite3"}'
    second = f'sqlite:///{tmp_path / "b.sqlite3"}'

    assert seed_engine(make_engine(first), today=TODAY)
    assert seed_engine(make_engine(second), today=TODAY)
    assert not seed_engine(make_engine(first), today=TODAY)

    assert snapshot(first) == snapshot(second)


def test_seeded_data_is_realistic(tmp_path: Path) -> None:
    engine = make_engine(f'sqlite:///{tmp_path / "db.sqlite3"}')
    seed_engine(engine, today=TODAY)

    with Session(engine) as session:
        prompts = repository.list_prompts(session)
        daily = analytics.daily_stats(session, days=DEFAULT_DAYS, today=TODAY)
        summary = analytics.summary(session, days=DEFAULT_DAYS, today=TODAY)
        older = analytics.summary(session, days=90, today=TODAY)

    assert {prompt.key for prompt in prompts} == {
        prompt[0] for prompt in PROMPTS
    }
    assert all(day.conversations > 0 for day in daily)
    assert 60 < round(summary.resolved_rate * 100) < 95
    assert summary.avg_rating is not None
    assert 3 < summary.avg_rating < 5
    assert older.conversations == summary.conversations


def test_reset_replaces_data(tmp_path: Path) -> None:
    engine = make_engine(f'sqlite:///{tmp_path / "db.sqlite3"}')
    seed_engine(engine, today=TODAY, days=3)

    assert seed_engine(engine, today=TODAY, days=2, reset=True)

    with Session(engine) as session:
        days = session.scalar(
            select(
                func.count(func.distinct(func.date(ConversationRow.started_at)))
            ),
        )
    assert days == 2


def test_main(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    url = f'sqlite:///{tmp_path / "cli.sqlite3"}'

    main(['--database-url', url, '--days', '5'])
    main(['--database-url', url])

    output = capsys.readouterr().out.splitlines()
    assert output == [f'{url}: seeded', f'{url}: already seeded, use --reset']


def test_non_sqlite_engine_gets_no_sqlite_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Call] = []

    def fake_create_engine(url: str, **options: object) -> None:
        calls.append((url, options))

    monkeypatch.setattr('support_bot_data.db.create_engine', fake_create_engine)

    make_engine('postgresql+psycopg://agent@db/support_bot')

    assert calls == [('postgresql+psycopg://agent@db/support_bot', {})]
