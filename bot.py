import os
import re
import json
import asyncio
import signal
import logging
from logging.handlers import RotatingFileHandler
import sys
import html
from collections import defaultdict
from time import time
from datetime import timedelta
from pathlib import Path

from aiohttp import ClientSession, TCPConnector, ClientTimeout
from aiohttp.hdrs import USER_AGENT
from aiohttp.http import SERVER_SOFTWARE
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    BotCommand,
    BotCommandScopeDefault,
    CallbackQuery,
)
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command
from aiogram.exceptions import Unauthorized
from aiogram.__meta__ import __version__

from config import BOT_TOKEN, PROXY_URL, WEB_URL, NOTIFY_CHAT_ID


BASE_DIR = Path(__file__).resolve().parent
VERSION_FILE = BASE_DIR / "VERSION"
BOT_VERSION = VERSION_FILE.read_text(encoding="utf-8").strip() if VERSION_FILE.exists() else "dev"
START_TIME = time()
_metrics = {"total_updates": 0, "errors": 0, "start_time": START_TIME}
_unique_users: set[int] = set()


class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }, ensure_ascii=False)


def mask_proxy(url: str | None) -> str | None:
    if not url:
        return None
    return re.sub(r"://[^:]+:[^@]+@", r"://***:***@", url)


def setup_logging():
    text_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handlers = [logging.StreamHandler(sys.stdout)]
    handlers[0].setFormatter(text_formatter)
    if os.environ.get("BOT_LOG_DIR"):
        log_dir = os.environ["BOT_LOG_DIR"]
        log_path = os.path.join(log_dir, "bot.log")
        try:
            handler_file = RotatingFileHandler(
                log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
            )
            handler_file.setFormatter(JsonFormatter())
            handlers.append(handler_file)
        except Exception:
            pass
    logging.basicConfig(level=logging.INFO, handlers=handlers)


logger = logging.getLogger(__name__)

dp = Dispatcher()

RATE_LIMIT = 10
RATE_WINDOW = 60
_user_requests: dict[int, list[float]] = defaultdict(list)


@dp.update.outer_middleware
async def rate_limit_middleware(handler, event, data):
    user_id = getattr(event, "from_user", None)
    if user_id:
        user_id = user_id.id
        _unique_users.add(user_id)
        _metrics["total_updates"] += 1
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
                headers={USER_AGENT: f"{SERVER_SOFTWARE} aiogram/{__version__}"},
                trust_env=True,
                timeout=ClientTimeout(total=30),
            )
            self._should_reset_connector = False
        return self._session


def create_bot() -> Bot:
    if PROXY_URL:
        logger.info("Использую прокси: %s", mask_proxy(PROXY_URL))
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
            ],
            [
                InlineKeyboardButton(
                    text="\U0001F4CB Помощь",
                    callback_data="help",
                )
            ],
        ]
    )
    safe_name = html.escape(message.from_user.first_name)
    await message.answer(
        f"Привет, {safe_name}! \U0001F44B\n\n"
        f"Нажми кнопку ниже, чтобы открыть веб-версию MAX:",
        reply_markup=keyboard,
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    text = (
        "\U0001F4CB Доступные команды:\n\n"
        "/start — Приветствие и кнопка для открытия MAX\n"
        "/help  — Список команд\n"
        "/about — О боте\n"
        "/stats — Статистика"
    )
    await message.answer(text)


@dp.message(Command("about"))
async def cmd_about(message: types.Message):
    uptime_seconds = int(time() - START_TIME)
    uptime_str = str(timedelta(seconds=uptime_seconds))
    text = (
        f"\U0001F916 MAXwed Bot v{BOT_VERSION}\n\n"
        f"Telegram-бот для быстрого доступа к веб-версии MAX.\n"
        f"Ссылка: {WEB_URL}\n\n"
        f"\U00023F1B Аптайм: {uptime_str}"
    )
    await message.answer(text)


@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    uptime_seconds = int(time() - START_TIME)
    uptime_str = str(timedelta(seconds=uptime_seconds))
    text = (
        "\U0001F4CA Статистика:\n\n"
        f"\U0001F465 Уникальных пользователей: {len(_unique_users)}\n"
        f"\U0001F4AC Всего запросов: {_metrics['total_updates']}\n"
        f"\U0000274C Ошибок: {_metrics['errors']}\n"
        f"\U000023F1B Аптайм: {uptime_str}"
    )
    await message.answer(text)


@dp.callback_query(F.data == "help")
async def callback_help(callback: CallbackQuery):
    text = (
        "\U0001F4CB Доступные команды:\n\n"
        "/start — Приветствие и кнопка для открытия MAX\n"
        "/help  — Список команд\n"
        "/about — О боте\n"
        "/stats — Статистика"
    )
    try:
        await callback.message.edit_text(text, reply_markup=None)
    except Exception:
        await callback.message.answer(text)
    await callback.answer()


async def notify_admin(bot: Bot, text: str):
    if NOTIFY_CHAT_ID:
        try:
            await bot.send_message(NOTIFY_CHAT_ID, text)
        except Exception as e:
            logger.warning("Не удалось отправить уведомление: %s", e)


async def shutdown(bot: Bot):
    logger.info("Остановка бота...")
    await bot.session.close()
    await dp.stop_polling()


async def main():
    bot = create_bot()

    try:
        me = await bot.get_me()
        logger.info("Бот авторизован: @%s", html.escape(me.username))
    except Unauthorized:
        logger.critical("Токен невалиден! Проверь BOT_TOKEN в .env или пересоздай key.bin/token.enc")
        await bot.session.close()
        return

    commands = [
        BotCommand(command="start", description="Открыть MAX"),
        BotCommand(command="help", description="Список команд"),
        BotCommand(command="about", description="О боте"),
        BotCommand(command="stats", description="Статистика"),
    ]
    try:
        await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    except Exception as e:
        logger.warning("Не удалось установить команды: %s", e)

    await notify_admin(bot, "\u2705 MAXwed Bot запущен")

    stop_event = asyncio.Event()

    def signal_handler():
        logger.info("Получен сигнал завершения...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            pass

    logger.info("Бот запущен!")
    max_retries = 5
    retries = 0
    notified_critical = False
    while not stop_event.is_set():
        try:
            await dp.start_polling(bot, stop_signal=stop_event)
            retries = 0
        except Exception as e:
            if stop_event.is_set():
                break
            _metrics["errors"] += 1
            retries += 1
            if retries > max_retries:
                logger.critical("Превышено число рестартов (%d). Останавливаюсь.", max_retries)
                _metrics["errors"] += 1
                await notify_admin(bot, "\u274C MAXwed Bot остановлен: превышено число рестартов")
                notified_critical = True
                break
            logger.exception("Polling crashed (%d/%d): %s", retries, max_retries, e)
            logger.info("Перезапуск polling через 5 секунд...")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass

    if not notified_critical:
        await notify_admin(bot, "\u23F9 MAXwed Bot остановлен")
    await shutdown(bot)


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
