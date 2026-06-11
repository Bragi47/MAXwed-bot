import os
import re
import asyncio
import signal
import logging
from logging.handlers import RotatingFileHandler
import sys
import html
from collections import defaultdict
from time import time
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
from aiogram.__meta__ import __version__

from config import BOT_TOKEN, PROXY_URL, WEB_URL


def mask_proxy(url: str | None) -> str | None:
    if not url:
        return None
    return re.sub(r"://[^:]+:[^@]+@", r"://***:***@", url)


def setup_logging():
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handlers = [logging.StreamHandler(sys.stdout)]
    if os.environ.get("BOT_LOG_DIR"):
        log_dir = os.environ["BOT_LOG_DIR"]
        log_path = os.path.join(log_dir, "bot.log")
        try:
            handler_file = RotatingFileHandler(
                log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
            )
            handlers.append(handler_file)
        except Exception:
            pass
    for h in handlers:
        h.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=handlers)


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


@dp.callback_query(F.data == "help")
async def callback_help(callback: CallbackQuery):
    text = (
        "\U0001F4CB Доступные команды:\n\n"
        "/start — Приветствие и кнопка для открытия MAX\n"
        "/help  — Список команд\n"
        "/about — О боте"
    )
    try:
        await callback.message.edit_text(text, reply_markup=None)
    except Exception:
        await callback.message.answer(text)
    await callback.answer()


async def shutdown(bot: Bot):
    logger.info("Остановка бота...")
    await bot.session.close()
    await dp.stop_polling()


async def main():
    bot = create_bot()
    commands = [
        BotCommand(command="start", description="Открыть MAX"),
        BotCommand(command="help", description="Список команд"),
        BotCommand(command="about", description="О боте"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())

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
    while not stop_event.is_set():
        try:
            await dp.start_polling(bot, stop_signal=stop_event)
            retries = 0
        except Exception as e:
            if stop_event.is_set():
                break
            retries += 1
            if retries > max_retries:
                logger.critical("Превышено число рестартов (%d). Останавливаюсь.", max_retries)
                break
            logger.exception("Polling crashed (%d/%d): %s", retries, max_retries, e)
            logger.info("Перезапуск polling через 5 секунд...")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass

    await shutdown(bot)


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
