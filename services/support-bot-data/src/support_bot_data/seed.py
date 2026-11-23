"""Тестовые данные БД агента: `python -m support_bot_data.seed`.

Данные случайные, но детерминированные (фиксированный seed): одинаковые
при каждом запуске для одной и той же даты «сегодня». Повторный запуск
без `--reset` ничего не меняет.
"""

import argparse
import os
import random
import sys
from collections.abc import Iterator, Sequence
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from support_bot_data.db import (
    DEFAULT_DATABASE_URL,
    ConversationRow,
    PromptRow,
    create_schema,
    make_engine,
)

SEED = 20_261_123
DEFAULT_DAYS = 60
_SECONDS_IN_DAY = 24 * 60 * 60
_WEEKEND = frozenset((5, 6))
_RATINGS = (1, 2, 3, 4, 5)
_RATING_WEIGHTS = (3, 4, 10, 30, 53)
_WEEKDAY_LOAD = 30
_WEEKEND_LOAD = 12
_LOAD_JITTER = (-5, 10)
_RESOLVED_PERCENT = 78
_RATED_PERCENT = 60
_TOKENS_RANGE = (300, 4500)
_PERCENT = 100

PROMPTS = (
    (
        'system',
        'Системный промпт',
        (
            'Ты — вежливый агент поддержки интернет-магазина «Север». '
            'Отвечай кратко и по делу, на языке клиента. Не обещай '
            'компенсаций и сроков, которых нет в базе знаний. Если не '
            'уверен в ответе — уточни детали или предложи оператора.'
        ),
    ),
    (
        'greeting',
        'Приветствие',
        (
            'Здравствуйте! Я виртуальный помощник «Севера». Помогу '
            'отследить заказ, оформить возврат или подобрать товар. '
            'Чем могу помочь?'
        ),
    ),
    (
        'escalation',
        'Передача оператору',
        (
            'Если клиент дважды выразил недовольство, просит человека '
            'или вопрос касается оплаты и персональных данных — '
            'извинись, кратко перескажи суть обращения и передай диалог '
            'оператору с тегом #escalation.'
        ),
    ),
    (
        'summary',
        'Резюме диалога',
        (
            'Составь резюме диалога для CRM в 2–3 предложениях: проблема '
            'клиента, что сделано, решён ли вопрос. Без персональных '
            'данных.'
        ),
    ),
)


def seed(
    session: Session,
    *,
    today: date,
    days: int = DEFAULT_DAYS,
    reset: bool = False,
) -> bool:
    """Заполнить БД; вернуть False, если данные уже были и `reset=False`."""
    if reset:
        session.execute(delete(ConversationRow))
        session.execute(delete(PromptRow))
    elif _has_prompts(session):
        return False
    now = datetime.combine(today, time.min, tzinfo=UTC)
    session.add_all(_prompts(now))
    rng = random.Random(SEED)  # noqa: S311 -- не криптография: нужна воспроизводимость
    session.add_all(_conversations(rng, today, days))
    session.commit()
    return True


def seed_engine(
    engine: Engine,
    *,
    today: date,
    days: int = DEFAULT_DAYS,
    reset: bool = False,
) -> bool:
    """Создать схему (если нет) и заполнить БД."""
    create_schema(engine)
    with Session(engine) as session:
        return seed(session, today=today, days=days, reset=reset)


def main(argv: Sequence[str] | None = None) -> None:
    """Точка входа `python -m support_bot_data.seed`."""
    parser = argparse.ArgumentParser(prog='python -m support_bot_data.seed')
    parser.add_argument(
        '--database-url',
        default=os.environ.get('DATABASE_URL', DEFAULT_DATABASE_URL),
    )
    parser.add_argument('--days', type=int, default=DEFAULT_DAYS)
    parser.add_argument('--reset', action='store_true')
    args = parser.parse_args(argv)
    seeded = seed_engine(
        make_engine(args.database_url),
        today=datetime.now(UTC).date(),
        days=args.days,
        reset=args.reset,
    )
    status = 'seeded' if seeded else 'already seeded, use --reset'
    sys.stdout.write(f'{args.database_url}: {status}\n')


def _has_prompts(session: Session) -> bool:
    first = session.scalars(select(PromptRow.key).limit(1)).first()
    return first is not None


def _prompts(now: datetime) -> list[PromptRow]:
    return [
        PromptRow(
            key=key,
            title=title,
            text=text,
            version=1,
            updated_at=now,
        )
        for key, title, text in PROMPTS
    ]


def _conversations(
    rng: random.Random,
    today: date,
    days: int,
) -> Iterator[ConversationRow]:
    for offset in range(days):
        day = today - timedelta(days=offset)
        midnight = datetime.combine(day, time.min, tzinfo=UTC)
        load = _WEEKEND_LOAD if day.weekday() in _WEEKEND else _WEEKDAY_LOAD
        for _ in range(load + rng.randint(*_LOAD_JITTER)):
            yield _conversation(rng, midnight)


def _conversation(rng: random.Random, midnight: datetime) -> ConversationRow:
    resolved = rng.randrange(_PERCENT) < _RESOLVED_PERCENT
    rated = rng.randrange(_PERCENT) < _RATED_PERCENT
    rating = rng.choices(_RATINGS, _RATING_WEIGHTS)[0] if rated else None
    if rating is not None and not resolved:
        rating = min(rating, rng.randint(1, 3))
    return ConversationRow(
        started_at=midnight + timedelta(seconds=rng.randrange(_SECONDS_IN_DAY)),
        resolved=resolved,
        rating=rating,
        tokens=rng.randint(*_TOKENS_RANGE),
    )


if __name__ == '__main__':  # pragma: no cover
    main()
