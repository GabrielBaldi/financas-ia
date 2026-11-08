"""ASGI entrypoint: `fastapi dev` / `fastapi run` (see [tool.fastapi] in pyproject.toml)."""

from financas.app import create_app

app = create_app()
