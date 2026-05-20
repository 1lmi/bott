from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


DATE_FORMAT = "%Y-%m-%d"
USER_COLUMNS = (
    "id, user_group, user_telegram_id, subscribe_status, "
    "subscribe_end_date, photo_mode, replacements_mode"
)


@dataclass(frozen=True)
class UserProfile:
    id: int
    user_group: str | None
    telegram_id: str
    subscribe_status: bool
    subscribe_end_date: str | None
    photo_mode: bool
    replacements_mode: bool

    @classmethod
    def from_row(cls, row: tuple) -> "UserProfile":
        return cls(
            id=row[0],
            user_group=row[1],
            telegram_id=str(row[2]),
            subscribe_status=bool(row[3]),
            subscribe_end_date=row[4],
            photo_mode=bool(row[5]),
            replacements_mode=bool(row[6]),
        )

    @property
    def should_send_replacements(self) -> bool:
        return self.subscribe_status and self.replacements_mode


def initialize_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_group TEXT,
                user_telegram_id TEXT NOT NULL,
                subscribe_status BOOLEAN DEFAULT FALSE,
                subscribe_end_date DATE,
                photo_mode BOOLEAN DEFAULT FALSE,
                replacements_mode BOOLEAN DEFAULT TRUE
            )
            """
        )
        conn.commit()


def ensure_user(db_path: Path, telegram_id: int | str) -> None:
    if get_user(db_path, telegram_id) is not None:
        return

    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO users (user_telegram_id) VALUES (?)", (str(telegram_id),))
        conn.commit()


def get_user(db_path: Path, telegram_id: int | str) -> UserProfile | None:
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            f"SELECT {USER_COLUMNS} FROM users WHERE user_telegram_id = ? LIMIT 1",
            (str(telegram_id),),
        )
        row = cursor.fetchone()

    return UserProfile.from_row(row) if row else None


def set_user_group(db_path: Path, telegram_id: int | str, user_group: str) -> None:
    ensure_user(db_path, telegram_id)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE users SET user_group = ? WHERE user_telegram_id = ?",
            (user_group, str(telegram_id)),
        )
        conn.commit()


def get_user_group(db_path: Path, telegram_id: int | str) -> str | None:
    user = get_user(db_path, telegram_id)
    return user.user_group if user else None


def get_subscription_status(db_path: Path, telegram_id: int | str) -> bool:
    user = get_user(db_path, telegram_id)
    return user.subscribe_status if user else False


def toggle_photo_mode(db_path: Path, telegram_id: int | str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE users SET photo_mode = NOT photo_mode WHERE user_telegram_id = ?",
            (str(telegram_id),),
        )
        conn.commit()


def toggle_replacements_mode(db_path: Path, telegram_id: int | str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE users SET replacements_mode = NOT replacements_mode WHERE user_telegram_id = ?",
            (str(telegram_id),),
        )
        conn.commit()


def add_subscription(
    db_path: Path,
    telegram_id: int | str,
    days: int,
    now: datetime | None = None,
) -> str:
    ensure_user(db_path, telegram_id)
    user = get_user(db_path, telegram_id)
    current_end_date = user.subscribe_end_date if user else None
    new_end_date = calculate_subscription_end_date(current_end_date, days, now)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE users SET subscribe_status = ?, subscribe_end_date = ? WHERE user_telegram_id = ?",
            (1, new_end_date, str(telegram_id)),
        )
        conn.commit()

    return new_end_date


def calculate_subscription_end_date(
    current_end_date: str | None,
    days: int,
    now: datetime | None = None,
) -> str:
    if current_end_date is None:
        base_date = now or datetime.now()
    else:
        base_date = datetime.strptime(current_end_date, DATE_FORMAT)

    return (base_date + timedelta(days=days)).strftime(DATE_FORMAT)


def remove_subscription(db_path: Path, telegram_id: int | str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE users SET subscribe_status = ?, subscribe_end_date = ? WHERE user_telegram_id = ?",
            (0, None, str(telegram_id)),
        )
        conn.commit()


def list_subscribed_user_ids(db_path: Path) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute("SELECT user_telegram_id FROM users WHERE subscribe_status = 1")
        return [row[0] for row in cursor.fetchall()]


def list_expired_subscribed_user_ids(db_path: Path) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            "SELECT user_telegram_id FROM users "
            "WHERE subscribe_end_date < datetime('now') AND subscribe_status = 1"
        )
        return [row[0] for row in cursor.fetchall()]


def deactivate_subscriptions(db_path: Path, user_ids: list[int | str]) -> None:
    if not user_ids:
        return

    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "UPDATE users SET subscribe_status = 0, subscribe_end_date = ? WHERE user_telegram_id = ?",
            [(None, str(user_id)) for user_id in user_ids],
        )
        conn.commit()
