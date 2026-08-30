FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

RUN pip install --no-cache-dir uv
COPY pyproject.toml ./
COPY src ./src
RUN uv pip install --system .

COPY docs ./docs
COPY artifacts/research ./artifacts/research

EXPOSE 8000
CMD ["sh", "-c", "clockcross serve --host 0.0.0.0 --port ${PORT}"]
