from __future__ import annotations

import threading
import time
import logging

import schedule
import telebot
import telebot.apihelper as telebot_apihelper
from requests.exceptions import RequestException

import database
from config import ensure_runtime_directories, load_config
from handlers import register_handlers
from logging_config import redact_sensitive_values, setup_logging
from replacement_service import ReplacementPaths, ReplacementService
from schedule_service import ScheduleRepository


logger = logging.getLogger(__name__)


def main() -> None:
    config = load_config()
    setup_logging(config.log_level, config.log_file)
    logger.info("Starting bot application")

    configure_proxy(config.tg_proxy_url)
    ensure_runtime_directories(config)
    database.initialize_database(config.database_path)
    logger.info("Runtime directories and database are ready")

    bot = telebot.TeleBot(config.bot_token)
    schedules = ScheduleRepository(
        even_week_path=config.even_week_schedule_path,
        odd_week_path=config.odd_week_schedule_path,
    )
    schedules.initialize()
    logger.info("Schedule files loaded")

    replacements = ReplacementService(
        ReplacementPaths(
            offers_dir=config.replacement_offers_dir,
            today_path=config.replacements_today_path,
            tomorrow_path=config.replacements_tomorrow_path,
            tomorrow_default_path=config.replacements_tomorrow_default_path,
        )
    )
    replacements.ensure_storage()
    register_handlers(bot, config, schedules, replacements)
    start_background_jobs(bot, config, replacements)
    logger.info("Handlers registered; starting polling")
    run_polling(bot)


def configure_proxy(proxy_url: str | None) -> None:
    if not proxy_url:
        return

    telebot_apihelper.proxy = {
        "http": proxy_url,
        "https": proxy_url,
    }
    logger.info("Telegram proxy configured")


def start_background_jobs(bot, config, replacements: ReplacementService) -> threading.Thread:
    def check_and_remove_invalid_subscriptions() -> None:
        users = database.list_expired_subscribed_user_ids(config.database_path)
        database.deactivate_subscriptions(config.database_path, users)
        if users:
            logger.info("Deactivated expired subscriptions: count=%s", len(users))
        else:
            logger.debug("Expired subscription cleanup finished: no users")

    schedule.every().day.at("17:00").do(check_and_remove_invalid_subscriptions)
    schedule.every().day.at("00:00").do(replacements.clear_offers)
    schedule.every().day.at("00:00").do(replacements.rotate_daily_replacements)

    thread = threading.Thread(target=run_schedule, daemon=True)
    thread.start()
    logger.info("Background scheduler started")
    return thread


def run_schedule() -> None:
    while True:
        try:
            schedule.run_pending()
        except Exception:
            logger.exception("Background scheduler job failed")
        time.sleep(10)


def run_polling(bot) -> None:
    while True:
        try:
            logger.info("Telegram polling started")
            bot.polling(none_stop=True)
        except RequestException as exc:
            logger.warning(
                "Telegram network error: %s. Retrying in 5 seconds",
                redact_sensitive_values(str(exc)),
            )
            time.sleep(5)
        except ConnectionError as exc:
            logger.warning("Telegram connection error: %s. Retrying in 5 seconds", exc)
            time.sleep(5)
        except Exception as exc:
            logger.exception("Telegram polling crashed: %s. Restarting in 5 seconds", exc)
            time.sleep(5)


if __name__ == "__main__":
    main()
