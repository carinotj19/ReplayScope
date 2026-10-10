FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY migrations/ ./migrations/
RUN python -m pip install --no-cache-dir '.[prod]'

RUN useradd --create-home appuser \
    && mkdir -p /data/uploads /app/instance \
    && chown -R appuser:appuser /data /app/instance
USER appuser

EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "replayscope:create_app()"]
