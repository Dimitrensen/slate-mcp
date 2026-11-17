FROM python:3.13-slim-bookworm AS build

COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_NO_CACHE=1

WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.13-slim-bookworm

RUN useradd \
        --uid 1000 \
        --user-group \
        --create-home \
        --home-dir /home/slate \
        --shell /usr/sbin/nologin \
        slate \
    && mkdir -p /data \
    && chown slate:slate /data

WORKDIR /app
COPY --from=build /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:/usr/local/bin:/usr/bin:/bin" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SLATE_DB=/data/slate.db \
    HOME=/tmp

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod 0755 /entrypoint.sh

VOLUME ["/data"]
EXPOSE 8765
ENTRYPOINT ["/entrypoint.sh"]
