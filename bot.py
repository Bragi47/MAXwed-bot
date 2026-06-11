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
from typing import Any

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

from config import BOT_TOKEN, PROXY_URL, WEB_URL, ADMIN_IDS


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


# ---- Admin commands ----

ADMIN_COMMANDS = ["admin", "status", "logs", "restart", "stop", "start", "update", "rebuild"]


def is_admin(user_id: int | None) -> bool:
    return user_id in ADMIN_IDS


async def _run_cmd(*args: str, timeout: int = 15) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        out = stdout.decode(errors="replace").strip()
        return out[:1000] if len(out) > 1000 else out
    except asyncio.TimeoutError:
        return "Команда превысила таймаут."
    except Exception as e:
        return f"Ошибка: {e}"


@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="\U0001F4CA Статус", callback_data="admin_status"),
                InlineKeyboardButton(text="\U0001F4BB Перезапустить", callback_data="admin_restart"),
            ],
            [
                InlineKeyboardButton(text="\u23F9 Остановить", callback_data="admin_stop_confirm"),
                InlineKeyboardButton(text="\u25B6 Запустить", callback_data="admin_start"),
            ],
            [
                InlineKeyboardButton(text="\U0001F504 Обновить", callback_data="admin_update_confirm"),
                InlineKeyboardButton(text="\U0001F4DD Логи", callback_data="admin_logs"),
            ],
        ]
    )
    await message.answer("\U0001F6E1 Панель управления:", reply_markup=kb)


async def _admin_cmd_handler(callback: CallbackQuery, action: str):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.answer()

    compose = ["docker", "compose", "-f", "/host-project/docker-compose.yml"]

    if action == "status":
        out = await _run_cmd(*compose, "ps")
        await callback.message.edit_text(f"\U0001F4CA Статус:\n<pre>{out}</pre>", parse_mode="HTML")

    elif action == "logs":
        out = await _run_cmd(*compose, "logs", "--tail", "30")
        await callback.message.edit_text(f"\U0001F4DD Последние логи:\n<pre>{out}</pre>", parse_mode="HTML")

    elif action == "restart":
        msg = await callback.message.edit_text("\U0001F4BB Перезапуск...")
        out = await _run_cmd(*compose, "restart")
        await msg.edit_text(f"\U00002705 Перезапущен:\n<pre>{out}</pre>", parse_mode="HTML")

    elif action == "start":
        out = await _run_cmd(*compose, "up", "-d")
        await callback.message.edit_text(f"\U00002705 Запущен:\n<pre>{out}</pre>", parse_mode="HTML")

    elif action == "stop_confirm":
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="\u26A0 Да, остановить", callback_data="admin_stop_yes"),
                    InlineKeyboardButton(text="\u274C Отмена", callback_data="admin_stop_no"),
                ]
            ]
        )
        await callback.message.edit_text("\u26A0 Точно остановить бота?", reply_markup=kb)

    elif action == "stop_yes":
        out = await _run_cmd(*compose, "down")
        await callback.message.edit_text(f"\u23F9 Остановлен:\n<pre>{out}</pre>", parse_mode="HTML")

    elif action == "stop_no":
        await callback.message.edit_text("\u274C Отменено.")

    elif action == "update_confirm":
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="\u26A0 Да, обновить", callback_data="admin_update_yes"),
                    InlineKeyboardButton(text="\u274C Отмена", callback_data="admin_update_no"),
                ]
            ]
        )
        await callback.message.edit_text("\u26A0 Обновить код и перезапустить бота?", reply_markup=kb)

    elif action == "update_yes":
        msg = await callback.message.edit_text("\U0001F504 Обновление...")
        pull = await _run_cmd("git", "-C", "/host-project", "pull", timeout=30)
        build = await _run_cmd(*compose, "up", "-d", "--build", timeout=120)
        await msg.edit_text(
            f"\U0001F504 Git pull:\n<pre>{pull[:300]}</pre>\n\n"
            f"\U0001F504 Rebuild:\n<pre>{build[:600]}</pre>",
            parse_mode="HTML",
        )

    elif action == "update_no":
        await callback.message.edit_text("\u274C Отменено.")


@dp.callback_query(F.data.startswith("admin_"))
async def callback_admin(callback: CallbackQuery):
    action = callback.data.replace("admin_", "", 1)
    await _admin_cmd_handler(callback, action)


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
        BotCommand(command="admin", description="Панель управления"),
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
    while not stop_event.is_set():
        try:
            await dp.start_polling(bot, stop_signal=stop_event)
        except Exception as e:
            if stop_event.is_set():
                break
            logger.exception("Polling crashed: %s", e)
            logger.info("Перезапуск polling через 5 секунд...")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass

    await shutdown(bot)


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
