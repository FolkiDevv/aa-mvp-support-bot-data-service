from collections.abc import Iterator
from datetime import datetime

import pytest
from litestar import Litestar
from litestar.testing import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from support_bot_data.app import create_app
from support_bot_data.db import (
    ConversationRow,
    PromptRow,
    create_schema,
    make_engine,
)

NOW = datetime.fromisoformat('2026-11-23T12:00:00+00:00')
CREATED = datetime.fromisoformat('2026-11-01T09:30:00+00:00')

type Client = TestClient[Litestar]


def at(moment: str) -> datetime:
    return datetime.fromisoformat(f'2026-11-{moment}:00+00:00')


@pytest.fixture
def now() -> datetime:
    return NOW


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = make_engine('sqlite://')
    create_schema(engine)
    with Session(engine) as session:
        session.add_all(
            [
                PromptRow(
                    key='system',
                    title='System',
                    text='You are helpful',
                    version=3,
                    updated_at=CREATED,
                ),
                PromptRow(
                    key='greeting',
                    title='Greeting',
                    text='Hi!',
                    version=1,
                    updated_at=CREATED,
                ),
                ConversationRow(
                    started_at=at('23T10:00'),
                    resolved=True,
                    rating=5,
                    tokens=100,
                ),
                ConversationRow(
                    started_at=at('23T11:00'),
                    resolved=False,
                    rating=None,
                    tokens=10,
                ),
                ConversationRow(
                    started_at=at('21T23:59'),
                    resolved=True,
                    rating=3,
                    tokens=1000,
                ),
                ConversationRow(
                    started_at=at('10T08:00'),
                    resolved=False,
                    rating=1,
                    tokens=1,
                ),
            ],
        )
        session.commit()
    yield engine
    engine.dispose()


@pytest.fixture
def client(engine: Engine) -> Iterator[Client]:
    with TestClient(create_app(engine, clock=lambda: NOW)) as test_client:
        yield test_client
