"""Агрегаты диалогов для аналитики. Чистые функции над `Session`."""

from datetime import UTC, date, datetime, time, timedelta
from typing import NamedTuple

from sqlalchemy import ColumnElement, RowMapping, case, func, select
from sqlalchemy.orm import Session

from support_bot_data.db import ConversationRow
from support_bot_data.schemas import DailyStats, Summary

_RATING_DIGITS = 2
_AGGREGATES = (
    func.count(ConversationRow.id).label('conversations'),
    func.coalesce(
        func.sum(case((ConversationRow.resolved, 1), else_=0)),
        0,
    ).label('resolved'),
    func.avg(ConversationRow.rating).label('avg_rating'),
    func.coalesce(func.sum(ConversationRow.tokens), 0).label('tokens'),
)


class _Totals(NamedTuple):
    conversations: int = 0
    resolved: int = 0
    avg_rating: float | None = None
    tokens: int = 0


def daily_stats(
    session: Session, *, days: int, today: date
) -> list[DailyStats]:
    """Агрегаты по каждому дню окна `days` дней, включая пустые дни."""
    start = today - timedelta(days=days - 1)
    by_day = _totals_by_day(session, start, today)
    return [
        _day_stats(start + timedelta(days=offset), by_day)
        for offset in range(days)
    ]


def summary(session: Session, *, days: int, today: date) -> Summary:
    """Агрегаты за последние `days` дней (включая сегодня)."""
    start = today - timedelta(days=days - 1)
    statement = select(*_AGGREGATES).where(*_window(start, today))
    totals = _totals(session.execute(statement).mappings().one())
    count = totals.conversations
    return Summary(
        period_days=days,
        conversations=count,
        resolved_rate=totals.resolved / count if count else 0,
        avg_rating=_round(totals.avg_rating),
        tokens=totals.tokens,
    )


def _totals_by_day(
    session: Session,
    start: date,
    end: date,
) -> dict[date, _Totals]:
    day = func.date(ConversationRow.started_at).label('day')
    window = _window(start, end)
    statement = select(day, *_AGGREGATES).where(*window).group_by(day)
    rows = session.execute(statement).mappings()
    return {_parse_day(row['day']): _totals(row) for row in rows}


def _day_stats(day: date, by_day: dict[date, _Totals]) -> DailyStats:
    totals = by_day.get(day, _Totals())
    return DailyStats(
        day=day,
        conversations=totals.conversations,
        resolved=totals.resolved,
        avg_rating=_round(totals.avg_rating),
        tokens=totals.tokens,
    )


def _totals(row: RowMapping) -> _Totals:
    return _Totals(
        conversations=row['conversations'],
        resolved=row['resolved'],
        avg_rating=row['avg_rating'],
        tokens=row['tokens'],
    )


def _window(start: date, end: date) -> tuple[ColumnElement[bool], ...]:
    since = datetime.combine(start, time.min, tzinfo=UTC)
    until = since + timedelta(days=(end - start).days + 1)
    return (
        ConversationRow.started_at >= since,
        ConversationRow.started_at < until,
    )


def _parse_day(raw: object) -> date:
    """SQLite отдаёт `date()` строкой, PostgreSQL — объектом `date`."""
    return raw if isinstance(raw, date) else date.fromisoformat(str(raw))


def _round(rating: float | None) -> float | None:
    return None if rating is None else round(float(rating), _RATING_DIGITS)
