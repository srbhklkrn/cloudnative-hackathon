FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS dependencies
COPY --from=ghcr.io/astral-sh/uv:0.9.28 /uv /bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM python:3.12-slim
WORKDIR /app
ARG APP_VERSION=local
ENV APP_VERSION=$APP_VERSION PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PATH="/app/.venv/bin:$PATH"
RUN groupadd --gid 10001 detour && useradd --uid 10001 --gid detour --no-create-home detour
COPY --from=dependencies /app/.venv /app/.venv
COPY backend/ backend/
COPY --from=web /web/dist frontend/dist/
USER 10001:10001
EXPOSE 8080
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log", "--proxy-headers", "--forwarded-allow-ips", "*"]
