FROM node:22-alpine AS frontend-builder
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY backend/pyproject.toml backend/uv.lock ./
COPY backend/ ./
RUN uv sync --frozen --no-dev
COPY --from=frontend-builder /frontend/dist/ /app/app/static/
RUN chmod +x /app/scripts/start_web.sh
EXPOSE 8000
CMD ["/app/scripts/start_web.sh"]
