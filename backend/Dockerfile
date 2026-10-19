# ── Builder ────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime ────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# The release workflow passes the tag (e.g. 0.1.0).
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}
LABEL org.opencontainers.image.title="Integration Platform API" \
      org.opencontainers.image.licenses="EUPL-1.2" \
      org.opencontainers.image.version="${APP_VERSION}"

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY app/ ./app/
COPY seed/ ./seed/
COPY alembic/ ./alembic/
COPY alembic.ini .
COPY tests/ ./tests/
COPY pytest.ini .

# Non-root user for security
RUN useradd -m -u 1001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# Run migrations then start server
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
