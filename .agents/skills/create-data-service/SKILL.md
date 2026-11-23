---
name: create-data-service
description: Создать data-service для БД ИИ-агента (Litestar + SQLAlchemy, доступ только по mTLS) вместе с типизированным клиентом для модуля админ-панели, или добавить в него новую операцию. Используй, когда админке нужен доступ к данным агента, нужно открыть новый эндпоинт для модуля или выпустить dev-сертификаты mTLS.
license: Proprietary
compatibility: Python 3.12+, uv, cookiecutter (через uvx), openssl
metadata:
  owner: admin-core-team
---

# Data-service агента

Data-service — единственный путь админ-панели к БД агента. Его пишет,
деплоит и защищает (mTLS) команда агента. Он живёт в отдельном
репозитории вместе со своим клиентом.

## 1. Сгенерировать репозиторий

```bash
uvx cookiecutter <git-url admin-platform> --directory templates/data-service \
  agent_name="Sales Agent"
cd sales-agent-data-service
uv sync --all-packages
deploy/certs/generate.sh
make check
```

Локально в монорепо admin-platform: `uvx cookiecutter templates/data-service`.
Сразу после генерации `make check` должен быть зелёным — шаблон
собран из эталона, который проходит все проверки. Если не зелёный —
остановись и сообщи команде ядра, не чини шаблон «на месте».

Что получилось:

| Путь | Назначение |
|---|---|
| `services/<agent>-data/src/<agent>_data/db.py` | SQLAlchemy-модели таблиц агента |
| `.../repository.py` | запросы к БД (единственное место с SQL) |
| `.../analytics.py` | агрегаты для аналитики |
| `.../schemas.py` | pydantic-модели ответов сервиса |
| `.../service.py`, `app.py` | Litestar-обработчики и приложение |
| `.../__main__.py` | запуск uvicorn с обязательным mTLS |
| `.../seed.py` | демо-данные для локальной разработки |
| `services/<agent>-data-client/src/<agent>_data_client/models.py` | DTO + docstring-таблица API (контракт) |
| `.../client.py` | `<Agent>DataClient` с mTLS (`TlsConfig`) |
| `deploy/certs/` | dev-CA и сертификаты, README о проде |

## 2. Привести к своему агенту

Пример в шаблоне — промпты и диалоги. Замени его на реальные таблицы:

1. `db.py` — опиши **существующие** таблицы агента (сервис не владеет
   схемой: никаких миграций в БД агента из data-service).
2. Определи операции, которые реально нужны админке (обычно: список и
   редактирование промптов/настроек, агрегаты для графиков). Не делай
   «универсальный SQL-эндпоинт».
3. Для каждой операции — раздел 3. Ненужные операции примера удали
   целиком (эндпоинт + метод клиента + DTO + тесты).

## 3. Новая операция (чек-лист)

1. Запрос в `repository.py` / `analytics.py` (+ тест на тестовой БД).
2. Схема ответа в `schemas.py` сервиса.
3. Обработчик в `service.py` и маршрут в `app.py`; ошибки —
   `{"detail": ...}` с кодами 400/404/409.
4. DTO той же формы в `models.py` клиента и строка в docstring-таблице API.
5. Метод клиента в `client.py` (ошибки — наследники `DataServiceError`).
6. Контрактный тест в `tests/test_contract.py`: настоящий клиент против
   `litestar.testing.TestClient(app)`.
7. Запись — только с оптимистической блокировкой (`expected_version`
   → 409) и только если она действительно нужна админке.
8. `make check` — зелёный. Подними minor-версию сервиса и клиента
   одновременно.

## 4. mTLS

- Сервер не стартует без `<AGENT>_DATA_TLS_CERT`, `_TLS_KEY`,
  `_TLS_CLIENT_CA`.
- Клиентов проверяет отдельный CA «admin-access» агента: любой
  сертификат от него даёт доступ, поэтому этот CA выпускает только
  сертификаты модулей админки.
- Живая проверка после изменений:
  ```bash
  python -m <agent>_data.seed
  python -m <agent>_data &          # с переменными TLS из deploy/certs/out
  curl --cacert deploy/certs/out/server-ca.crt https://localhost:8443/<путь>
  # ожидается отказ TLS: без клиентского сертификата нельзя
  curl --cacert ... --cert ...-admin-module.crt --key ...-admin-module.key https://localhost:8443/<путь>
  ```

## 5. Передать модулю

Опубликуй клиент в приватный индекс и сообщи команде модуля версию.
Модуль подключает клиент через Protocol-порт (скилл `create-admin-module`).
