from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


BASE_DIR = Path(__file__).resolve().parent
DOTENV_PATH = BASE_DIR / ".env"
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
ASSETS_DIR = BASE_DIR / "assets"
SCHEDULES_DIR = ASSETS_DIR / "schedules"
IMAGES_DIR = ASSETS_DIR / "images"
FONTS_DIR = ASSETS_DIR / "fonts"

DATABASE_PATH = DATA_DIR / "bot.db"
REPLACEMENT_OFFERS_DIR = DATA_DIR / "replacement_offers"
LOG_FILE_PATH = LOGS_DIR / "bot.log"

EVEN_WEEK_SCHEDULE_PATH = SCHEDULES_DIR / "even_week.xlsx"
ODD_WEEK_SCHEDULE_PATH = SCHEDULES_DIR / "odd_week.xlsx"
SCHEDULE_TEMPLATE_PATH = IMAGES_DIR / "schedule_template.png"
REPLACEMENTS_TODAY_PATH = IMAGES_DIR / "replacements_today.png"
REPLACEMENTS_TOMORROW_PATH = IMAGES_DIR / "replacements_tomorrow.png"
REPLACEMENTS_TOMORROW_DEFAULT_PATH = IMAGES_DIR / "replacements_tomorrow_default.png"
BELL_SCHEDULE_PATH = IMAGES_DIR / "bell_schedule.jpg"
NUNITO_FONT_PATH = FONTS_DIR / "Nunito.ttf"

LESSONS_PER_DAY = 7
FIRST_DAY_START_ROW = 6

GROUPS = [
    "ТОР-25", "РЭГ-25", "КИП-25", "ПР-25/1", "ПР-25/2", "ОПИ-25", "ДПИ-25", "МД-25/1", "МД-25/2",
    "ИСИП-25/1", "ИСИП-25/2", "БУ-25", "БД-25", "ГС-25/1", "ГС-25/2", "ЮР-25/1", "ЮР-25/2", "ПКД-25",
    "ТОР-24", "РЭГ-24", "КИП-24", "СЭЗС-24", "ПР-24", "ОПИ-24", "ДПИ-24", "МД-24/1", "МД-24/2",
    "ИСИП-24/1", "ИСИП-24/2", "БУ-24", "БД-24", "ГС-24/1", "ГС-24/2", "ЮР-24/1", "ЮР-24/2", "ЮР-24/3", "ПКД-24",
    "ТОР-23", "РЭГ-23", "СЭЗС-23", "ПР-23", "ОПИ-23", "ДПИ-23", "МД-23/1", "МД-23/2",
    "ИСИП-23/1", "ИСИП-23/2", "БУ-23", "БД-23", "Ф-23", "ЗИМ-23", "ЮР-23/1", "ЮР-23/2", "ПКД-23",
    "ТОР-22", "РЭГ-22", "СЭЗС-22", "ПР-22", "ОПИ-22", "ДПИ-22", "БУ-22", "МД-22", "ИСИП-22/1", "ИСИП-22/2", "ПКД-22",
]


@dataclass(frozen=True)
class AppConfig:
    bot_token: str
    admin_chat_id: int
    channel_id: int
    tg_proxy_url: str | None
    log_level: str
    log_file: Path = LOG_FILE_PATH
    database_path: Path = DATABASE_PATH
    replacement_offers_dir: Path = REPLACEMENT_OFFERS_DIR
    even_week_schedule_path: Path = EVEN_WEEK_SCHEDULE_PATH
    odd_week_schedule_path: Path = ODD_WEEK_SCHEDULE_PATH
    schedule_template_path: Path = SCHEDULE_TEMPLATE_PATH
    replacements_today_path: Path = REPLACEMENTS_TODAY_PATH
    replacements_tomorrow_path: Path = REPLACEMENTS_TOMORROW_PATH
    replacements_tomorrow_default_path: Path = REPLACEMENTS_TOMORROW_DEFAULT_PATH
    bell_schedule_path: Path = BELL_SCHEDULE_PATH
    font_path: Path = NUNITO_FONT_PATH


def load_config(environ: Mapping[str, str] | None = None) -> AppConfig:
    env = _load_environment(environ)
    errors: list[str] = []

    bot_token = env.get("BOT_TOKEN", "").strip()
    if not bot_token:
        errors.append("BOT_TOKEN")

    admin_chat_id = _read_required_int(env, "ADMIN_CHAT_ID", errors)
    channel_id = _read_required_int(env, "CHANNEL_ID", errors)
    tg_proxy_url = env.get("TG_PROXY_URL", "").strip() or None
    log_level = env.get("LOG_LEVEL", "INFO").strip() or "INFO"

    if errors:
        missing = ", ".join(errors)
        raise RuntimeError(f"Missing or invalid environment variables: {missing}")

    return AppConfig(
        bot_token=bot_token,
        admin_chat_id=admin_chat_id,
        channel_id=channel_id,
        tg_proxy_url=tg_proxy_url,
        log_level=log_level,
    )


def ensure_runtime_directories(config: AppConfig) -> None:
    config.database_path.parent.mkdir(parents=True, exist_ok=True)
    config.replacement_offers_dir.mkdir(parents=True, exist_ok=True)
    config.log_file.parent.mkdir(parents=True, exist_ok=True)


def _load_environment(environ: Mapping[str, str] | None) -> Mapping[str, str]:
    if environ is not None:
        return environ

    dotenv_values = load_dotenv_values(DOTENV_PATH)
    return {**dotenv_values, **os.environ}


def load_dotenv_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue

        values[key] = _clean_dotenv_value(value.strip())

    return values


def _clean_dotenv_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _read_required_int(env: Mapping[str, str], name: str, errors: list[str]) -> int:
    value = env.get(name, "").strip()
    if not value:
        errors.append(name)
        return 0

    try:
        return int(value)
    except ValueError:
        errors.append(name)
        return 0
