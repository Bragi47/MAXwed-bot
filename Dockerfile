FROM python:3.12-slim AS builder

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


FROM python:3.12-slim

RUN addgroup --system --gid 1001 app && \
    adduser --system --uid 1001 --gid 1001 --no-create-home app

WORKDIR /app
RUN chown -R app:app /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages

COPY --chown=app:app . .
RUN chmod +x entrypoint.sh

ENV BOT_LOG_DIR=/tmp

USER app

ENTRYPOINT ["/app/entrypoint.sh"]
