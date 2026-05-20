from __future__ import annotations

from telebot import types


BTN_SCHEDULE_TODAY = "📖 Расписание на сегодня"
BTN_SCHEDULE_TOMORROW = "📖 Расписание на завтра"
BTN_SCHEDULE_OTHER_DAY = "✉️ Расписание на другой день"
BTN_BELL_SCHEDULE = "⏳ Расписание звонков"
BTN_REPLACEMENTS = "🔁 Замены"
BTN_ABOUT = "👤 О авторе"
BTN_PROFILE = "💻 Профиль"


def create_main_keyboard() -> types.ReplyKeyboardMarkup:
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        types.KeyboardButton(BTN_SCHEDULE_TODAY),
        types.KeyboardButton(BTN_SCHEDULE_TOMORROW),
    ).add(types.KeyboardButton(BTN_SCHEDULE_OTHER_DAY))
    markup.add(
        types.KeyboardButton(BTN_ABOUT),
        types.KeyboardButton(BTN_REPLACEMENTS),
        types.KeyboardButton(BTN_PROFILE),
    )
    markup.add(types.KeyboardButton(BTN_BELL_SCHEDULE))
    return markup


def create_group_keyboard(groups: list[str]) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    for group in groups:
        markup.add(types.InlineKeyboardButton(group, callback_data=f"choose_group_{group}"))
    return markup


def create_days_keyboard() -> types.InlineKeyboardMarkup:
    days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        *[
            types.InlineKeyboardButton(text=day, callback_data=f"day_{index}")
            for index, day in enumerate(days)
        ]
    )
    return markup


def create_replacements_keyboard() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Сегодня", callback_data="today_replace"))
    markup.add(types.InlineKeyboardButton("Завтра", callback_data="tomorrow_replace"))
    return markup


def create_buy_subscription_keyboard() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(text="Купить за 1⭐", callback_data="subscription_stars"))
    return markup


def create_profile_keyboard(show_replacements_toggle: bool) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(text="Сменить группу", callback_data="change_group"))
    markup.add(types.InlineKeyboardButton(text="Изменить фото режим", callback_data="change_photo_mode"))
    markup.add(types.InlineKeyboardButton(text="Подписка", callback_data="subscription"))

    if show_replacements_toggle:
        markup.add(
            types.InlineKeyboardButton(
                text="Изменить режим отправки замен",
                callback_data="toggle_replacements",
            )
        )

    return markup


def create_replace_review_keyboard(photo_filename: str) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Следующее", callback_data=f"next_{photo_filename}"))
    markup.add(types.InlineKeyboardButton("Принять", callback_data=f"accept_{photo_filename}"))
    return markup
