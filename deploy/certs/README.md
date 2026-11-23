# Dev-сертификаты mTLS (Support Bot)

```bash
deploy/certs/generate.sh          # создать недостающее (идемпотентно)
deploy/certs/generate.sh --force  # пересоздать всё
```

Результат — `deploy/certs/out/` (в `.gitignore`, ключи с правами `600`).
Только для локальной разработки и compose: ключи CA лежат рядом с
сертификатами, сроки длинные.

## Что есть что

Два независимых CA — у каждой стороны TLS свой корень доверия:

| Файл | Что это | Кто использует |
|---|---|---|
| `server-ca.crt` / `.key` | CA сервера data-service | `.crt` — клиенты (модуль; ядро в монолите): `SUPPORT_BOT_DATA_CA` |
| `support-bot-data.crt` / `.key` | сертификат сервера, SAN `localhost`, `127.0.0.1`, `support-bot-data` | data-service: `SUPPORT_BOT_DATA_TLS_CERT` / `_TLS_KEY` |
| `admin-access-ca.crt` / `.key` | CA «support-bot-admin-access»: кому разрешён доступ | data-service: `SUPPORT_BOT_DATA_TLS_CLIENT_CA` |
| `support_bot-admin-module.crt` / `.key` | клиентский сертификат модуля (CN `support_bot-admin-module`, `clientAuth`) | модуль: `SUPPORT_BOT_DATA_CERT` / `_KEY` |

Почему два CA, а не один dev-CA: доверие к серверу и право доступа —
разные решения. Сервер пускает **любой** клиентский сертификат,
подписанный `admin-access-ca` (решение B в `ARCHITECTURE.md`), поэтому
этот CA выпускает только сертификаты клиентов админки и ничего больше.
С одним общим CA любой выпущенный им клиентский сертификат (например,
для другой системы) открывал бы доступ к данным агента, а смена/отзыв
доступа требовали бы перевыпуска и серверного сертификата. Раздельные CA
повторяют прод: серверный PKI живёт своей жизнью, доступ отзывается
ротацией CA доступа.

Ключи — EC P-256; у сертификатов есть SKI/AKI и критичные
`basicConstraints`, чтобы проходить строгую проверку X.509
(`VERIFY_X509_STRICT` в Python 3.13+).

## Кто выдаёт в проде

Всё это зона **команды агента** (владельца data-service и БД):

- серверный сертификат data-service — их обычный PKI/ingress
  (cert-manager, корпоративный CA и т.п.);
- CA «`<agent>-admin-access`» — заводит и хранит команда агента
  (ключ CA — в vault/HSM, не в репозитории);
- клиентский сертификат выдаётся **на модуль** (`<agent>-admin-module`)
  по запросу команды ядра/модуля, с коротким сроком и ротацией;
  отзыв — через CRL/перевыпуск CA или allowlist CN на прокси (решение B);
- ядро и модуль получают только свой клиентский сертификат, ключ и
  `server-ca.crt` — как секреты деплоя (в монолите монтируются в ядро,
  в микросервисах — в сервис модуля).

## Ручная проверка

```bash
export DATABASE_URL=sqlite:///support_bot_data.sqlite3
python -m support_bot_data.seed
SUPPORT_BOT_DATA_TLS_CERT=deploy/certs/out/support-bot-data.crt \
SUPPORT_BOT_DATA_TLS_KEY=deploy/certs/out/support-bot-data.key \
SUPPORT_BOT_DATA_TLS_CLIENT_CA=deploy/certs/out/admin-access-ca.crt \
python -m support_bot_data &

O=deploy/certs/out
# без клиентского сертификата — обрыв на TLS (curl: (56) ...)
curl --cacert $O/server-ca.crt https://localhost:8443/prompts
# с сертификатом модуля — 200
curl --cacert $O/server-ca.crt --cert $O/support_bot-admin-module.crt \
     --key $O/support_bot-admin-module.key https://localhost:8443/prompts
```

За HTTP(S)-прокси добавьте `--noproxy '*'` (и `NO_PROXY=*` для Python).
