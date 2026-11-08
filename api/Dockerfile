# API image (not built in the development environment: see the README).
FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Dependencies first, so code changes do not reinstall them.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

COPY . .
RUN uv sync --locked --no-dev
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8102
# Migrate, (re)create the demo user, then serve. PORT is set by hosts such as Render.
CMD ["sh", "-c", "alembic upgrade head && python -m financas.seed && fastapi run --port ${PORT:-8102}"]
