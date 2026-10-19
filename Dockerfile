FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/logs /app/data \
    && chown -R appuser:appuser /app

USER appuser

ENV DATABASE_URL=sqlite:////app/data/customer_needs_agent.db \
    LOG_FILE=/app/logs/agent.jsonl

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

CMD ["uvicorn", "customer_needs_agent.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

