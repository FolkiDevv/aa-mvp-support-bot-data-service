import ssl
from pathlib import Path

import pytest
import uvicorn
from litestar import Litestar

from support_bot_data.service import (
    CERT_ENV,
    CLIENT_CA_ENV,
    KEY_ENV,
    Settings,
    main,
    parse_settings,
    run,
)


@pytest.fixture
def tls_env(tmp_path: Path) -> dict[str, str]:
    env = {}
    for name in (CERT_ENV, KEY_ENV, CLIENT_CA_ENV):
        path = tmp_path / f'{name.lower()}.pem'
        path.write_text('dummy')
        env[name] = str(path)
    return env


def test_settings_from_environment(tls_env: dict[str, str]) -> None:
    env = {**tls_env, 'HOST': '10.0.0.5', 'PORT': '9443', 'DATABASE_URL': 'x'}

    settings = parse_settings([], env)

    assert settings.host == '10.0.0.5'
    assert settings.port == 9443
    assert settings.database_url == 'x'
    assert settings.client_ca == Path(tls_env[CLIENT_CA_ENV])


def test_flags_override_environment(tls_env: dict[str, str]) -> None:
    settings = parse_settings(['--port', '1234', '--host', 'h'], tls_env)

    assert (settings.host, settings.port) == ('h', 1234)


@pytest.mark.parametrize('missing', [CERT_ENV, KEY_ENV, CLIENT_CA_ENV])
def test_tls_is_mandatory(
    tls_env: dict[str, str],
    missing: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env = {name: path for name, path in tls_env.items() if name != missing}

    with pytest.raises(SystemExit):
        parse_settings([], env)

    assert 'mTLS is mandatory' in capsys.readouterr().err


def test_tls_files_must_exist(
    tls_env: dict[str, str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        parse_settings(['--ssl-certfile', '/nonexistent.pem'], tls_env)

    assert 'file not found' in capsys.readouterr().err


def test_run_requires_client_certificates(
    tmp_path: Path,
    tls_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(app: Litestar, **options: object) -> None:
        calls.append(options)

    monkeypatch.setattr(uvicorn, 'run', fake_run)
    settings = parse_settings(
        ['--database-url', f'sqlite:///{tmp_path / "db.sqlite3"}'],
        tls_env,
    )

    run(settings)

    assert calls[0]['ssl_cert_reqs'] == ssl.CERT_REQUIRED
    assert calls[0]['ssl_ca_certs'] == settings.client_ca
    assert calls[0]['ssl_certfile'] == settings.certfile
    assert (tmp_path / 'db.sqlite3').exists()


def test_main(
    tls_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[Settings] = []
    monkeypatch.setattr('support_bot_data.service.run', seen.append)
    for name, path in tls_env.items():
        monkeypatch.setenv(name, path)

    main(['--port', '8000'])

    assert seen[0].port == 8000
