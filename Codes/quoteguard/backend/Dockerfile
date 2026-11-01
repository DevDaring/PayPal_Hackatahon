FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.lock .
COPY requirements-nodeps.txt .
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-cache-dir --no-deps -r requirements-nodeps.txt
COPY . .
RUN useradd -m -u 10001 app && mkdir -p /data/storage && chown -R app /data /app
USER app
ENV STORAGE_PATH=/data/storage
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && python -m quoteguard.cli seed && uvicorn quoteguard.api.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
