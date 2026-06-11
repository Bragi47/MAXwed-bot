#!/bin/sh
set -e

# дать пользователю app доступ к Docker socket (если примонтирован)
if [ -S /var/run/docker.sock ]; then
    DOCKER_GID=$(stat -c '%g' /var/run/docker.sock 2>/dev/null || echo "")
    if [ -n "$DOCKER_GID" ]; then
        addgroup -g "$DOCKER_GID" docker_host 2>/dev/null || true
        adduser app docker_host 2>/dev/null || true
    fi
fi

if [ ! -f key.bin ]; then
    echo "=========================================="
    echo "  Токен не найден!"
    echo "  Запусти на хосте:"
    echo "    python3 setup_encrypt.py"
    echo "  Затем перезапусти контейнер"
    echo "=========================================="
    exit 1
fi

# ensure .env exists for docker compose compat
touch .env

exec su -c "python3 bot.py" app