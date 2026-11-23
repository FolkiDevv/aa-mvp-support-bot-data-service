# syntax=docker/dockerfile:1
# Data-service Support Bot: Litestar + SQLAlchemy, доступ ТОЛЬКО по mTLS.
#
# Сборка из корня репозитория:
#   docker build -f deploy/Dockerfile.data-service -t support-bot-data .
#
# Запуск требует сертификат/ключ сервера и CA клиентов («admin-access»):
# SUPPORT_BOT_DATA_TLS_CERT / _TLS_KEY / _TLS_CLIENT_CA. Без них процесс
# завершается с ошибкой. SEED_ON_START=1 — заполнить пустую БД
# демо-данными (повторный запуск данные не трогает).
#
# НЕ ПРОВЕРЕНО в Docker (в среде разработки MVP Docker нет); шаги
# uv export / uv build / uv pip install проверены вне контейнера.

ARG PYTHON_VERSION=3.12

FROM ghcr.io/astral-sh/uv:0.11 AS uv

# ---------------------------------------------------------------- build
FROM python:${PYTHON_VERSION}-slim AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /src
COPY . .
RUN uv export --frozen --no-dev --no-emit-workspace --no-hashes \
        --package support-bot-data -o /tmp/requirements.txt \
 && uv build --wheel --out-dir /wheels --package support-bot-data \
 && uv venv /opt/venv \
 && uv pip install --python /opt/venv/bin/python --no-deps \
        -r /tmp/requirements.txt /wheels/*.whl

# ---------------------------------------------------------------- runtime
FROM python:${PYTHON_VERSION}-slim
COPY --from=build /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8443 \
    DATABASE_URL=sqlite:////data/support_bot.sqlite3 \
    SEED_ON_START=0
# /data — том с SQLite; 1777, чтобы работал любой UID из compose (`user:`).
RUN useradd --system --uid 10001 --no-create-home data \
 && mkdir /data && chmod 1777 /data
USER 10001
VOLUME ["/data"]
EXPOSE 8443
CMD ["sh", "-c", "if [ \"$SEED_ON_START\" = 1 ]; then python -m support_bot_data.seed; fi; exec python -m support_bot_data"]
