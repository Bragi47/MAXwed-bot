import os
import re
import asyncio
import logging
from logging.handlers import RotatingFileHandler
import sys
from collections import defaultdict
from time import time

from aiohttp import ClientSession, TCPConnector
from aiohttp.hdrs import USER_AGENT
from aiohttp.http import SERVER_SOFTWARE
from aiogram import Bot, Dispatcher, types
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    BotCommand,
    BotCommandScopeDefault,
)
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command
from aiogram.__meta__ import __version__

from config import BOT_TOKEN, PROXY_URL

WEB_URL = "https://web.max.ru/"


def mask_proxy(url: str | None) -> str | None:
    if not url:
        return None
    return re.sub(r"://[^:]+:[^@]+@", r"://***:***@", url)


def setup_logging():
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler_file = RotatingFileHandler(
        "bot.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    handler_file.setFormatter(formatter)
    handler_stdout = logging.StreamHandler(sys.stdout)
    handler_stdout.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[handler_file, handler_stdout])


setup_logging()
logger = logging.getLogger(__name__)

dp = Dispatcher()

# Rate limiter: max N messages per user per interval
RATE_LIMIT = 10
RATE_WINDOW = 60
_user_requests: dict[int, list[float]] = defaultdict(list)


@dp.update.outer_middleware
async def rate_limit_middleware(handler, event, data):
    user_id = getattr(event, "from_user", None)
    if user_id:
        user_id = user_id.id
        now = time()
        timestamps = _user_requests[user_id]
        timestamps[:] = [t for t in timestamps if now - t < RATE_WINDOW]
        if len(timestamps) >= RATE_LIMIT:
            return
        timestamps.append(now)
    return await handler(event, data)


class HttpProxySession(AiohttpSession):
    async def create_session(self) -> ClientSession:
        if self._should_reset_connector:
            await self.close()
        if self._session is None or self._session.closed:
            connector = TCPConnector(**self._connector_init)
            self._session = ClientSession(
                connector=connector,
                headers={
                    USER_AGENT: f"{SERVER_SOFTWARE} aiogram/{__version__}",
                },
                trust_env=True,
            )
            self._should_reset_connector = False
        return self._session


def create_bot() -> Bot:
    if PROXY_URL:
        logger.info("Использую прокси: %s", mask_proxy(PROXY_URL))
        os.environ["HTTP_PROXY"] = PROXY_URL
        os.environ["HTTPS_PROXY"] = PROXY_URL
        return Bot(token=BOT_TOKEN, session=HttpProxySession())
    return Bot(token=BOT_TOKEN)


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="\U0001F4FA Открыть MAX",
                    web_app=WebAppInfo(url=WEB_URL),
                )
            ]
        ]
    )
    await message.answer(
        f"Привет, {message.from_user.first_name}! \U0001F44B\n\n"
        f"Нажми кнопку ниже, чтобы открыть веб-версию MAX:",
        reply_markup=keyboard,
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    text = (
        "\U0001F4CB Доступные команды:\n\n"
        "/start — Приветствие и кнопка для открытия MAX\n"
        "/help  — Список команд\n"
        "/about — О боте"
    )
    await message.answer(text)


@dp.message(Command("about"))
async def cmd_about(message: types.Message):
    text = (
        "\U0001F916 MAXwed Bot v1.0\n\n"
        "Telegram-бот для быстрого доступа к веб-версии MAX.\n"
        f"Ссылка: {WEB_URL}"
    )
    await message.answer(text)


async def main():
    bot = create_bot()
    commands = [
        BotCommand(command="start", description="Открыть MAX"),
        BotCommand(command="help", description="Список команд"),
        BotCommand(command="about", description="О боте"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    logger.info("Бот запущен!")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
