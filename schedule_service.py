from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import logging
from pathlib import Path

import openpyxl
from isoweek import Week
from PIL import Image, ImageDraw, ImageFont

from config import (
    EVEN_WEEK_SCHEDULE_PATH,
    FIRST_DAY_START_ROW,
    GROUPS,
    LESSONS_PER_DAY,
    NUNITO_FONT_PATH,
    ODD_WEEK_SCHEDULE_PATH,
    SCHEDULE_TEMPLATE_PATH,
)


logger = logging.getLogger(__name__)

LESSON_NUMBERS = [
    "Первая пара",
    "Вторая пара",
    "Третья пара",
    "Четвёртая пара",
    "Пятая пара",
    "Шестая пара",
    "Седьмая пара",
]


@dataclass
class ScheduleRepository:
    even_week_path: Path = EVEN_WEEK_SCHEDULE_PATH
    odd_week_path: Path = ODD_WEEK_SCHEDULE_PATH

    def __post_init__(self) -> None:
        self._sheets: dict[str, object] = {"even": None, "odd": None}

    def initialize(self) -> None:
        logger.info(
            "Loading schedule files: even=%s odd=%s",
            self.even_week_path,
            self.odd_week_path,
        )
        self._sheets["even"] = load_schedule_file(self.even_week_path)
        self._sheets["odd"] = load_schedule_file(self.odd_week_path)
        logger.info("Schedule repository initialized")

    def sheet_for_week_type(self, week_type: str):
        sheet = self._sheets.get(week_type)
        if sheet is None:
            raise RuntimeError("Schedule files are not loaded")
        return sheet

    def sheet_for_date(self, current_date: date):
        return self.sheet_for_week_type(week_type_for_date(current_date))


def load_schedule_file(filename: Path):
    logger.debug("Loading schedule workbook: %s", filename)
    workbook = openpyxl.load_workbook(filename)
    return workbook.active


def week_type_for_date(current_date: date) -> str:
    return week_type_for_week_number(Week.withdate(current_date).week)


def week_type_for_week_number(week_number: int) -> str:
    return "even" if week_number % 2 == 0 else "odd"


def get_row_range(day_index: int) -> tuple[int, int]:
    start_row = FIRST_DAY_START_ROW + (day_index * LESSONS_PER_DAY)
    return start_row, start_row + LESSONS_PER_DAY - 1


def get_group_column(user_group: str, groups: list[str] | None = None) -> int:
    known_groups = GROUPS if groups is None else groups
    if user_group not in known_groups:
        raise ValueError(f"Unknown group: {user_group}")
    return known_groups.index(user_group) + 3


def get_lesson_number(index: int) -> str:
    return LESSON_NUMBERS[index]


def clean_lesson(value) -> str:
    return " ".join(str(value).split()) if value else "Нет"


def read_lessons(sheet, user_group: str, day_index: int) -> list[str]:
    schedule_column = get_group_column(user_group)
    start_row, end_row = get_row_range(day_index)

    lessons = []
    for row_number in range(start_row, end_row + 1):
        lesson = sheet.cell(row=row_number, column=schedule_column).value
        lessons.append(clean_lesson(lesson))
    return lessons


def format_schedule_lines(lessons: list[str], include_lesson_numbers: bool = True) -> list[str]:
    if not include_lesson_numbers:
        return lessons

    return [
        f"{get_lesson_number(index)}: {lesson}"
        for index, lesson in enumerate(lessons)
    ]


def format_schedule_text(lessons: list[str], include_lesson_numbers: bool = True) -> str:
    return "\n\n".join(format_schedule_lines(lessons, include_lesson_numbers))


def render_schedule_image(
    lessons: list[str],
    output_path: Path,
    template_path: Path = SCHEDULE_TEMPLATE_PATH,
    font_path: Path = NUNITO_FONT_PATH,
) -> Path:
    photo = Image.open(template_path)
    draw = ImageDraw.Draw(photo)
    font = ImageFont.truetype(str(font_path), size=40)

    for index, lesson in enumerate(lessons):
        draw.text((115, 108 + index * 95), lesson, font=font, fill=(0, 0, 0))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    photo.save(output_path)
    return output_path
