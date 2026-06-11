#!/usr/bin/env python3
"""Мастер первичной настройки MAXwed Bot.

Запусти один раз после клонирования репозитория:
  python setup_encrypt.py
  (или python3, если python не установлен)
"""

import sys
import os
import io
import shutil
from pathlib import Path

from cryptography.fernet import Fernet


BANNER = r"""
+----------------------------------------+
|        MAXwed Bot --  настройка         |
+----------------------------------------+
"""


def prompt_token() -> str:
    print("Вставь токен бота (от @BotFather):")
    token = input("> ").strip()
    if not token:
        print("Ошибка: токен не может быть пустым.")
        sys.exit(1)
    return token


def encrypt_token(token: str, key_path: Path, token_enc_path: Path):
    key = Fernet.generate_key()
    cipher = Fernet(key)
    encrypted = cipher.encrypt(token.encode())
    key_path.write_bytes(key)
    token_enc_path.write_bytes(encrypted)
    print(f"  [OK] {key_path.name} - создан")
    print(f"  [OK] {token_enc_path.name} - создан (токен зашифрован)")


def ensure_env(base: Path):
    env_path = base / ".env"
    example_path = base / ".env.example"
    if env_path.exists():
        print(f"  [OK] .env - уже существует")
        return
    if example_path.exists():
        shutil.copy2(example_path, env_path)
        # убираем пример токена из нового .env
        lines = env_path.read_text(encoding="utf-8").splitlines()
        lines = [l for l in lines if not l.startswith("BOT_TOKEN=") and "your_telegram_bot_token_here" not in l]
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"  [OK] .env - создан из .env.example")


def fix_encoding():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if not stream or not hasattr(stream, "buffer"):
            continue
        try:
            wrapped = io.TextIOWrapper(stream.buffer, encoding="utf-8", errors="replace")
            if stream is sys.stdin:
                sys.stdin = wrapped
            elif stream is sys.stdout:
                sys.stdout = wrapped
            else:
                sys.stderr = wrapped
        except Exception:
            pass


def main():
    fix_encoding()
    print(BANNER)
    base = Path(__file__).resolve().parent
    key_path = base / "key.bin"
    token_enc_path = base / "token.enc"

    if key_path.exists():
        print("Файл key.bin уже существует.")
        ans = input("Перезаписать? (y/N): ").strip().lower()
        if ans != "y":
            print("Настройка отменена.")
            sys.exit(0)
        print()

    token = prompt_token()
    print()
    encrypt_token(token, key_path, token_enc_path)
    ensure_env(base)

    print()
    print("  [OK] Всё готово. Запускаю бота..." )


if __name__ == "__main__":
    main()
