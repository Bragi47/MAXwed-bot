FROM python:3.12-slim

RUN addgroup --system --gid 1001 app && \
    adduser --system --uid 1001 --gid 1001 --no-create-home app

WORKDIR /app
RUN chown -R app:app /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends git docker.io && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app . .
RUN chmod +x entrypoint.sh

ENV BOT_LOG_DIR=/tmp

ENTRYPOINT ["/app/entrypoint.sh"]
