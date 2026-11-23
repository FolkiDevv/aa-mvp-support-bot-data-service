"""Запуск data-service: uvicorn со строго обязательным mTLS.

Параметры — флаги или переменные окружения:

======================= ============================== =====================
Флаг                    Переменная                     Что это
======================= ============================== =====================
``--host``              ``HOST``                       адрес (127.0.0.1)
``--port``              ``PORT``                       порт (8443)
``--database-url``      ``DATABASE_URL``               БД агента
``--ssl-certfile``      ``SUPPORT_BOT_DATA_TLS_CERT``  сертификат сервера
``--ssl-keyfile``       ``SUPPORT_BOT_DATA_TLS_KEY``   ключ сервера
``--ssl-ca-certs``      ``SUPPORT_BOT_DATA_TLS_CLIENT_CA`` CA клиентов
======================= ============================== =====================

Без всех трёх TLS-файлов сервис не стартует: клиент без сертификата,
подписанного CA клиентов («admin-access»), отклоняется на TLS-рукопожатии.
"""

import argparse
import os
import ssl
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import uvicorn

from support_bot_data.app import create_app
from support_bot_data.db import DEFAULT_DATABASE_URL, create_schema, make_engine

DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 8443
CERT_ENV = 'SUPPORT_BOT_DATA_TLS_CERT'
KEY_ENV = 'SUPPORT_BOT_DATA_TLS_KEY'
CLIENT_CA_ENV = 'SUPPORT_BOT_DATA_TLS_CLIENT_CA'


@dataclass(frozen=True, slots=True, kw_only=True)
class Settings:
    """Настройки запуска сервиса."""

    host: str
    port: int
    database_url: str
    certfile: Path
    keyfile: Path
    client_ca: Path


def parse_settings(
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> Settings:
    """Собрать настройки из флагов и окружения (флаги важнее).

    Raises:
        SystemExit: не задан или не найден один из TLS-файлов.
    """
    parser = _parser(os.environ if environ is None else environ)
    args = parser.parse_args(argv)
    tls_files = {
        'server certificate': args.ssl_certfile,
        'server key': args.ssl_keyfile,
        'client CA': args.ssl_ca_certs,
    }
    for name, path in tls_files.items():
        _require_file(parser, name, path)
    return Settings(
        host=args.host,
        port=args.port,
        database_url=args.database_url,
        certfile=Path(args.ssl_certfile),
        keyfile=Path(args.ssl_keyfile),
        client_ca=Path(args.ssl_ca_certs),
    )


def run(settings: Settings) -> None:
    """Запустить uvicorn: TLS + обязательный клиентский сертификат."""
    engine = make_engine(settings.database_url)
    create_schema(engine)
    uvicorn.run(
        create_app(engine),
        host=settings.host,
        port=settings.port,
        ssl_certfile=settings.certfile,
        ssl_keyfile=settings.keyfile,
        ssl_ca_certs=settings.client_ca,
        ssl_cert_reqs=ssl.CERT_REQUIRED,
    )


def _parser(env: Mapping[str, str]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='python -m support_bot_data',
        description='Support Bot data-service (mTLS only).',
    )
    parser.add_argument('--host', default=env.get('HOST', DEFAULT_HOST))
    parser.add_argument(
        '--port',
        type=int,
        default=int(env.get('PORT', DEFAULT_PORT)),
    )
    parser.add_argument(
        '--database-url',
        default=env.get('DATABASE_URL', DEFAULT_DATABASE_URL),
    )
    parser.add_argument('--ssl-certfile', default=env.get(CERT_ENV))
    parser.add_argument('--ssl-keyfile', default=env.get(KEY_ENV))
    parser.add_argument('--ssl-ca-certs', default=env.get(CLIENT_CA_ENV))
    return parser


def _require_file(
    parser: argparse.ArgumentParser,
    name: str,
    path: str | None,
) -> None:
    if not path:
        parser.error(f'mTLS is mandatory: {name} is not set')
    if not Path(path).is_file():
        parser.error(f'{name} file not found: {path}')


def main(argv: Sequence[str] | None = None) -> None:
    """Точка входа `python -m support_bot_data`."""
    run(parse_settings(argv))
