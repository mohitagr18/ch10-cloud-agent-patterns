FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_SYSTEM_PYTHON=1

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml README.md ./
COPY retrieval_service ./retrieval_service

RUN uv sync --frozen || uv sync

EXPOSE 8080

CMD ["uv", "run", "uvicorn", "retrieval_service.app:app", "--host", "0.0.0.0", "--port", "8080"]
