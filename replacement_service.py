from __future__ import annotations

import os
import shutil
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from config import (
    REPLACEMENT_OFFERS_DIR,
    REPLACEMENTS_TODAY_PATH,
    REPLACEMENTS_TOMORROW_DEFAULT_PATH,
    REPLACEMENTS_TOMORROW_PATH,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReplacementPaths:
    offers_dir: Path = REPLACEMENT_OFFERS_DIR
    today_path: Path = REPLACEMENTS_TODAY_PATH
    tomorrow_path: Path = REPLACEMENTS_TOMORROW_PATH
    tomorrow_default_path: Path = REPLACEMENTS_TOMORROW_DEFAULT_PATH


class ReplacementService:
    def __init__(self, paths: ReplacementPaths | None = None) -> None:
        self.paths = paths or ReplacementPaths()
        self.can_add_offers = True
        self.photo_data: dict[str, int] = {}

    def ensure_storage(self) -> None:
        self.paths.offers_dir.mkdir(parents=True, exist_ok=True)
        self.paths.today_path.parent.mkdir(parents=True, exist_ok=True)
        logger.debug("Replacement storage is ready: offers_dir=%s", self.paths.offers_dir)

    def clear_offers(self) -> None:
        self.ensure_storage()
        removed_count = 0
        for photo in self.paths.offers_dir.iterdir():
            if photo.is_file():
                photo.unlink()
                removed_count += 1
        self.photo_data.clear()
        logger.info("Replacement offers cleared: removed=%s", removed_count)

    def rotate_daily_replacements(self, now: datetime | None = None) -> bool:
        current_datetime = now or datetime.today()
        if current_datetime.weekday() in (5, 6):
            logger.info("Daily replacement rotation skipped on weekend")
            return False

        if not self._daily_files_exist():
            logger.warning(
                "Один из файлов отсутствует, проверьте наличие replacements_today.png, "
                "replacements_tomorrow.png и replacements_tomorrow_default.png."
            )
            return False

        self.paths.today_path.unlink()
        shutil.copy(self.paths.tomorrow_path, self.paths.today_path)
        self.paths.tomorrow_path.unlink()
        shutil.copy(self.paths.tomorrow_default_path, self.paths.tomorrow_path)
        self.can_add_offers = True
        logger.info("Daily replacements rotated")
        return True

    def get_next_photo_number(self) -> int:
        self.ensure_storage()
        return get_next_photo_number_from_files([path.name for path in self.paths.offers_dir.iterdir()])

    def save_offer(self, photo_bytes: bytes, user_id: int) -> str:
        if not self.can_add_offers:
            raise RuntimeError("Replacement offers are closed")

        photo_number = self.get_next_photo_number()
        photo_filename = f"{photo_number}.png"
        photo_path = self.paths.offers_dir / photo_filename
        photo_path.write_bytes(photo_bytes)
        self.photo_data[photo_filename] = user_id
        logger.info("Replacement offer saved: filename=%s user_id=%s", photo_filename, user_id)
        return photo_filename

    def list_offer_files(self) -> list[str]:
        self.ensure_storage()
        return sorted(
            [path.name for path in self.paths.offers_dir.iterdir() if path.is_file()],
            key=lambda filename: int(filename.split(".")[0]),
        )

    def get_offer_path(self, photo_filename: str) -> Path:
        return self.paths.offers_dir / photo_filename

    def accept_offer(self, photo_filename: str) -> tuple[int | None, list[int]]:
        photo_path = self.get_offer_path(photo_filename)
        if self.paths.tomorrow_path.exists():
            self.paths.tomorrow_path.unlink()
        os.replace(photo_path, self.paths.tomorrow_path)

        accepted_user = self.photo_data.get(photo_filename)
        rejected_users = [
            user_id
            for filename, user_id in self.photo_data.items()
            if filename != photo_filename
        ]

        self.clear_offers()
        self.can_add_offers = False
        logger.info(
            "Replacement offer accepted: filename=%s accepted_user=%s rejected_count=%s",
            photo_filename,
            accepted_user,
            len(rejected_users),
        )
        return accepted_user, rejected_users

    def save_direct_replacement(self, target: str, photo_bytes: bytes) -> Path:
        if target == "today":
            filename = self.paths.today_path
        elif target == "tomorrow":
            filename = self.paths.tomorrow_path
        else:
            raise ValueError(f"Unknown replacement target: {target}")

        filename.parent.mkdir(parents=True, exist_ok=True)
        filename.write_bytes(photo_bytes)
        logger.info("Direct replacement saved: target=%s path=%s", target, filename)
        return filename

    def replacement_path(self, target: str) -> Path:
        if target == "today":
            return self.paths.today_path
        if target == "tomorrow":
            return self.paths.tomorrow_path
        raise ValueError(f"Unknown replacement target: {target}")

    def _daily_files_exist(self) -> bool:
        return (
            self.paths.today_path.exists()
            and self.paths.tomorrow_path.exists()
            and self.paths.tomorrow_default_path.exists()
        )


def get_next_photo_number_from_files(filenames: list[str]) -> int:
    numbers = []
    for filename in filenames:
        if not filename.endswith(".png"):
            continue
        stem = filename.rsplit(".", 1)[0]
        if stem.isdigit():
            numbers.append(int(stem))

    return max(numbers) + 1 if numbers else 1
