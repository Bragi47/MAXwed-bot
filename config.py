import os
from pathlib import Path

from dotenv import load_dotenv
from cryptography.fernet import Fernet

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
KEY_FILE = BASE_DIR / "key.bin"
TOKEN_ENC_FILE = BASE_DIR / "token.enc"
ADMIN_ENC_FILE = BASE_DIR / "admin.enc"


def _get_token() -> str:
    token = os.getenv("BOT_TOKEN", "")
    if token:
        return token

    if KEY_FILE.exists() and TOKEN_ENC_FILE.exists():
        key = KEY_FILE.read_bytes()
        encrypted = TOKEN_ENC_FILE.read_bytes()
        cipher = Fernet(key)
        token = cipher.decrypt(encrypted).decode()
        if token:
            return token

    raise ValueError(
        "BOT_TOKEN не найден.\n"
        "Варианты:\n"
        "  1) Укажи BOT_TOKEN=... в .env\n"
        "  2) Создай key.bin + token.enc через: python setup_encrypt.py"
    )


def _get_admin_ids() -> list[int]:
    if not KEY_FILE.exists() or not ADMIN_ENC_FILE.exists():
        return []
    try:
        key = KEY_FILE.read_bytes()
        encrypted = ADMIN_ENC_FILE.read_bytes()
        cipher = Fernet(key)
        raw = cipher.decrypt(encrypted).decode()
        return [int(x.strip()) for x in raw.split(",") if x.strip()]
    except Exception:
        return []


BOT_TOKEN: str = _get_token()
ADMIN_IDS: list[int] = _get_admin_ids()
PROXY_URL: str | None = os.getenv("PROXY_URL") or None
WEB_URL: str = os.getenv("WEB_URL", "https://web.max.ru/")
