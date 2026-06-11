#!/usr/bin/env python3
"""Мастер настройки администраторов MAXwed Bot.

Запусти после setup_encrypt.py:
  python setup_admin.py

ID узнай у @userinfobot в Telegram.
"""

import sys
import io
from pathlib import Path

from cryptography.fernet import Fernet


BANNER = r"""
+----------------------------------------+
|   MAXwed Bot -- настройка админов      |
+----------------------------------------+
"""


def fix_encoding():
    try:
        sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass


def main():
    fix_encoding()
    print(BANNER)
    base = Path(__file__).resolve().parent
    key_path = base / "key.bin"
    admin_enc_path = base / "admin.enc"

    if not key_path.exists():
        print("Ошибки: сначала запусти setup_encrypt.py (нужен key.bin)")
        sys.exit(1)

    print("Введи Telegram ID администраторов через запятую.")
    print("Узнать свой ID: @userinfobot")
    print()
    raw = input("> ").strip()
    if not raw:
        print("Ошибка: ID не может быть пустым.")
        sys.exit(1)

    ids = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            print(f"Ошибка: '{part}' не является числом.")
            sys.exit(1)

    key = key_path.read_bytes()
    cipher = Fernet(key)
    encrypted = cipher.encrypt(",".join(str(i) for i in ids).encode())
    admin_enc_path.write_bytes(encrypted)

    print()
    print(f"  [OK] admin.enc - создан (ID: {', '.join(str(i) for i in ids)})")
    print()
    print("  Перезапусти бота: docker compose restart")


if __name__ == "__main__":
    main()
