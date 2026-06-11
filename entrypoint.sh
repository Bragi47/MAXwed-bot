#!/bin/sh
set -e

if [ ! -f key.bin ]; then
    echo "=========================================="
    echo "  Токен не найден!"
    echo "  Запусти на хосте:"
    echo "    python3 setup_encrypt.py"
    echo "  Затем перезапусти контейнер"
    echo "=========================================="
    exit 1
fi

touch .env

exec python3 bot.py