from __future__ import annotations

import logging
import re
from datetime import datetime
from telebot import types
from telebot.types import LabeledPrice

import database
from config import AppConfig, GROUPS
from keyboards import (
    BTN_ABOUT,
    BTN_BELL_SCHEDULE,
    BTN_PROFILE,
    BTN_REPLACEMENTS,
    BTN_SCHEDULE_OTHER_DAY,
    BTN_SCHEDULE_TODAY,
    BTN_SCHEDULE_TOMORROW,
    create_buy_subscription_keyboard,
    create_days_keyboard,
    create_group_keyboard,
    create_main_keyboard,
    create_profile_keyboard,
    create_replace_review_keyboard,
    create_replacements_keyboard,
)
from replacement_service import ReplacementService
from schedule_service import format_schedule_text, read_lessons, render_schedule_image


logger = logging.getLogger(__name__)


def register_handlers(bot, config: AppConfig, schedules, replacements: ReplacementService) -> None:
    last_command: dict[int, str] = {}

    def check_channel_subscription(user_id: int) -> bool:
        try:
            status = bot.get_chat_member(config.channel_id, user_id).status
        except Exception as exc:
            logger.warning("Failed to check channel subscription: user_id=%s error=%s", user_id, exc)
            bot.send_message(user_id, f"Произошла ошибка при получении информации о подписке: {str(exc)}")
            return True

        logger.debug("Channel subscription checked: user_id=%s status=%s", user_id, status)
        return status in ["member", "administrator", "creator"]

    def require_channel_subscription(message) -> bool:
        if check_channel_subscription(message.from_user.id):
            return True

        bot.send_message(
            message.from_user.id,
            "❗ Для использования бота вам нужно подписаться на канал\n https://t.me/+2-z2QYzz6NIyOGVi",
        )
        return False

    def send_replacement_photo(chat_id: int, target: str, caption: str) -> None:
        try:
            with replacements.replacement_path(target).open("rb") as photo_file:
                bot.send_photo(chat_id, photo_file, caption=caption)
            logger.info("Replacement photo sent: chat_id=%s target=%s", chat_id, target)
        except Exception as exc:
            logger.exception("Failed to send replacement photo: chat_id=%s target=%s", chat_id, target)
            bot.send_message(
                chat_id,
                "Не удалось отправить фотографию: "
                + str(exc)
                + "\n\nПопробуйте ещё раз, если не получиться напишите @uu44uu44",
            )

    def notify_subscribers() -> None:
        sent_count = 0
        failed_count = 0
        for user_id in database.list_subscribed_user_ids(config.database_path):
            try:
                bot.send_message(user_id, "⌛ Появились замены")
                sent_count += 1
            except Exception as exc:
                failed_count += 1
                logger.warning("Failed to notify subscriber: user_id=%s error=%s", user_id, exc)
                bot.send_message(config.admin_chat_id, f"ошибка: {str(exc)}")
        logger.info("Replacement notifications sent: sent=%s failed=%s", sent_count, failed_count)

    def send_schedule(message, day_index: int, caption: str, replacement_target: str | None) -> None:
        logger.info(
            "Schedule requested: user_id=%s chat_id=%s day_index=%s caption=%s photo_target=%s",
            message.from_user.id,
            message.chat.id,
            day_index,
            caption,
            replacement_target,
        )
        if not require_channel_subscription(message):
            logger.info("Schedule request blocked by channel subscription: user_id=%s", message.from_user.id)
            return

        user = database.get_user(config.database_path, message.from_user.id)
        if not user or user.user_group not in GROUPS:
            logger.warning("Schedule request has no valid group: user_id=%s", message.from_user.id)
            bot.send_message(
                message.chat.id,
                "❗ Не удалось определить вашу группу. Попробуйте перезапустить бота командой /start",
            )
            return

        try:
            sheet = schedules.sheet_for_date(datetime.today().date())
            lessons = read_lessons(sheet, user.user_group, day_index)
        except Exception as exc:
            logger.exception("Failed to build schedule: user_id=%s day_index=%s", message.from_user.id, day_index)
            bot.send_message(message.chat.id, "❗ Произошла ошибка, попробуйте ещё раз " + str(exc))
            return

        if user.photo_mode:
            send_schedule_image(message, lessons, caption)
        else:
            bot.send_message(
                message.chat.id,
                format_schedule_text(lessons, include_lesson_numbers=True),
                reply_markup=create_main_keyboard(),
            )
            logger.info("Schedule text sent: user_id=%s group=%s", message.from_user.id, user.user_group)

        if replacement_target and user.should_send_replacements:
            send_replacement_photo(message.chat.id, replacement_target, replacement_caption(replacement_target))

    def send_schedule_image(message, lessons: list[str], caption: str) -> None:
        output_path = config.database_path.parent / f"schedule_{message.from_user.id}.png"
        try:
            render_schedule_image(
                lessons,
                output_path=output_path,
                template_path=config.schedule_template_path,
                font_path=config.font_path,
            )
            with output_path.open("rb") as photo_file:
                bot.send_photo(message.chat.id, photo_file, caption=caption)
            logger.info("Schedule image sent: user_id=%s output=%s", message.from_user.id, output_path)
        except Exception as exc:
            logger.exception("Failed to render/send schedule image: user_id=%s", message.from_user.id)
            bot.send_message(message.chat.id, "❗ Произошла ошибка, попробуйте ещё раз " + str(exc))
        finally:
            output_path.unlink(missing_ok=True)

    def replacement_caption(target: str) -> str:
        return "Замены на сегодня" if target == "today" else "Замены на завтра"

    def assert_admin(message) -> bool:
        if message.from_user.id == config.admin_chat_id:
            return True
        logger.warning("Admin command denied: user_id=%s text=%s", message.from_user.id, message.text)
        bot.send_message(message.chat.id, "У вас нет прав для выполнения этой команды.")
        return False

    @bot.message_handler(commands=["start"])
    def handle_start(message):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Ознакомиться", callback_data="start_use_bot"))
        bot.send_message(
            message.chat.id,
            f"👋 Привет, {message.from_user.first_name}! Ознакомься с правилами",
            reply_markup=markup,
        )

    @bot.callback_query_handler(func=lambda call: call.data == "start_use_bot")
    def callback_start_use_bot(call):
        database.ensure_user(config.database_path, call.from_user.id)
        logger.info("User accepted rules: user_id=%s", call.from_user.id)
        bot.send_message(
            call.message.chat.id,
            "Одно и самое главное правило: не мешать работе бота методом использования багов, недоработок",
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Выбрать группу", callback_data="start_using"))
        bot.send_message(call.message.chat.id, "✅ Теперь вы можете начать использовать бота.", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data == "start_using")
    def callback_start_using(call):
        bot.send_message(call.message.chat.id, "Выберите вашу группу", reply_markup=create_group_keyboard(GROUPS))

    @bot.callback_query_handler(func=lambda call: call.data.startswith("choose_group_"))
    def callback_choose_group(call):
        chosen_group = call.data[len("choose_group_"):]
        database.set_user_group(config.database_path, call.from_user.id, chosen_group)
        logger.info("User group selected: user_id=%s group=%s", call.from_user.id, chosen_group)
        bot.send_message(call.message.chat.id, f"✅ Вы успешно выбрали группу: {chosen_group}")
        bot.send_message(
            call.message.chat.id,
            "Теперь вы можете выбрать нужную опцию:",
            reply_markup=create_main_keyboard(),
        )

    @bot.message_handler(func=lambda message: message.text == BTN_SCHEDULE_TODAY)
    def get_schedule_today(message):
        send_schedule(
            message,
            day_index=datetime.today().weekday(),
            caption="Расписание на сегодня",
            replacement_target="today",
        )

    @bot.message_handler(func=lambda message: message.text == BTN_SCHEDULE_TOMORROW)
    def get_schedule_tomorrow(message):
        tomorrow_day = (datetime.today().weekday() + 1) % 7
        send_schedule(
            message,
            day_index=tomorrow_day,
            caption="Расписание на завтра",
            replacement_target="tomorrow",
        )

    @bot.message_handler(func=lambda message: message.text == BTN_SCHEDULE_OTHER_DAY)
    def get_schedule_other_day(message):
        if require_channel_subscription(message):
            bot.send_message(message.chat.id, "Выберите день недели:", reply_markup=create_days_keyboard())

    @bot.callback_query_handler(func=lambda call: call.data.startswith("day_"))
    def handle_day_button(call):
        user_group = database.get_user_group(config.database_path, call.from_user.id)
        if not user_group or user_group not in GROUPS:
            bot.send_message(
                call.message.chat.id,
                "❗ Не удалось определить вашу группу. Попробуйте перезапустить бота командой /start",
            )
            return

        day_index = int(call.data.split("_")[1])
        sheet = schedules.sheet_for_date(datetime.today().date())
        lessons = read_lessons(sheet, user_group, day_index)
        bot.send_message(call.message.chat.id, format_schedule_text(lessons, include_lesson_numbers=True))

    @bot.message_handler(func=lambda message: message.text == BTN_BELL_SCHEDULE)
    def get_bell_schedule(message):
        try:
            with config.bell_schedule_path.open("rb") as photo_file:
                bot.send_photo(message.chat.id, photo_file)
        except FileNotFoundError:
            logger.exception("Bell schedule image is missing: path=%s", config.bell_schedule_path)

    @bot.message_handler(func=lambda message: message.text == BTN_ABOUT)
    def about_creator(message):
        bot.send_message(message.chat.id, "Разработчик: Максим ИСИП-22/2\nСвязь: @uu44uu44")

    @bot.message_handler(func=lambda message: message.text == BTN_REPLACEMENTS)
    def show_replacements(message):
        user = database.get_user(config.database_path, message.from_user.id)
        if not user:
            logger.warning("Profile request has no user row: user_id=%s", message.from_user.id)
            bot.send_message(
                message.chat.id,
                "Не удалось определить вашу группу. Попробуйте перезапустить бота командой /start",
            )
            return

        if not user.subscribe_status:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("Купить подписку", callback_data="subscription"))
            bot.send_message(
                message.chat.id,
                "❗ Замены предоставляются по подписке\nЦена - 1⭐/Месяц\n\n"
                "Так-же подписку можно получить, если отправить замены через команду "
                "/replace_offers (эта команда есть в меню)\n"
                "Отправленная замена дает 10 дней подписки",
                reply_markup=markup,
            )
            return

        bot.send_message(message.chat.id, "Получить замены на:", reply_markup=create_replacements_keyboard())

    @bot.callback_query_handler(func=lambda call: call.data == "today_replace")
    def today_replace(call):
        if database.get_subscription_status(config.database_path, call.from_user.id):
            send_replacement_photo(call.message.chat.id, "today", "Замены на сегодня")
        else:
            bot.send_message(call.message.chat.id, "❗ У вас нет премиум подписки ")

    @bot.callback_query_handler(func=lambda call: call.data == "tomorrow_replace")
    def tomorrow_replace(call):
        if database.get_subscription_status(config.database_path, call.from_user.id):
            send_replacement_photo(call.message.chat.id, "tomorrow", "Замены на завтра")
        else:
            bot.send_message(call.message.chat.id, "❗ У вас нет премиум подписки ")

    @bot.message_handler(func=lambda message: message.text == BTN_PROFILE)
    def show_profile(message):
        user = database.get_user(config.database_path, message.from_user.id)
        if not user:
            bot.send_message(
                message.chat.id,
                "Не удалось определить вашу группу. Попробуйте перезапустить бота командой /start",
            )
            return

        bot.send_message(
            message.chat.id,
            format_profile(user, message.from_user.id),
            reply_markup=create_profile_keyboard(user.subscribe_status),
            parse_mode="HTML",
        )

    @bot.callback_query_handler(func=lambda call: call.data == "change_group")
    def call_change_group(call):
        if not ensure_profile_owner(call):
            return
        callback_start_using(call)

    @bot.callback_query_handler(func=lambda call: call.data == "change_photo_mode")
    def call_change_photo_mode(call):
        if not ensure_profile_owner(call):
            return

        database.toggle_photo_mode(config.database_path, call.from_user.id)
        logger.info("Photo mode toggled: user_id=%s", call.from_user.id)
        bot.answer_callback_query(call.id, "Фото режим изменен")
        update_profile_message(call)

    @bot.callback_query_handler(func=lambda call: call.data == "subscription")
    def call_subscription(call):
        has_subscription = database.get_subscription_status(config.database_path, call.from_user.id)
        if has_subscription:
            text = "У вас есть подписка ✅\n\nНажмите кнопку ниже, чтобы купить ещё 30 дней подписки:"
        else:
            text = "💎 Стоимость 30 дней = 1⭐\n\nНажмите кнопку ниже, чтобы оплатить:"

        bot.send_message(call.message.chat.id, text, reply_markup=create_buy_subscription_keyboard())

    @bot.callback_query_handler(func=lambda call: call.data == "subscription_stars")
    def call_subscription_stars(call):
        prices = [LabeledPrice(label="Подписка на 30 дней", amount=1)]
        logger.info("Subscription invoice requested: user_id=%s", call.from_user.id)
        bot.send_invoice(
            chat_id=call.message.chat.id,
            title="Подписка на 30 дней",
            description="Оплата подписки через Telegram Stars",
            invoice_payload=f"sub_30d_{call.from_user.id}",
            provider_token="",
            currency="XTR",
            prices=prices,
            start_parameter="subscription-stars",
        )

    @bot.pre_checkout_query_handler(func=lambda query: True)
    def checkout(pre_checkout_query):
        bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

    @bot.message_handler(content_types=["successful_payment"])
    def got_payment(message):
        payload = message.successful_payment.invoice_payload
        user_id = message.from_user.id
        if payload.startswith("sub_30d_"):
            database.add_subscription(config.database_path, user_id, 30)
            logger.info("Subscription payment received: user_id=%s payload=%s", user_id, payload)
            bot.send_message(config.admin_chat_id, f"Пользователь {user_id} купил подписку!!!!")
            bot.send_message(message.chat.id, "✅ Спасибо за оплату 1⭐!\nВам начислена подписка на 30 дней.")

    @bot.callback_query_handler(func=lambda call: call.data == "toggle_replacements")
    def call_toggle_replacements(call):
        if not ensure_profile_owner(call):
            return

        database.toggle_replacements_mode(config.database_path, call.from_user.id)
        logger.info("Replacement auto-send toggled: user_id=%s", call.from_user.id)
        bot.answer_callback_query(call.id, "Режим авто отправки замен изменен")
        update_profile_message(call)

    @bot.message_handler(commands=["sub_add"])
    def handle_sub_add(message):
        if not assert_admin(message):
            return

        parts = message.text.split()
        if len(parts) != 3:
            bot.send_message(
                message.chat.id,
                "Пожалуйста, укажите данные в виде: "
                "'/sub_add (телеграм айди пользователя) (кол-во дней подписки)' "
                "для добавления подписки. ",
            )
            return

        username_to_add = parts[1]
        add_days = int(parts[2])
        database.add_subscription(config.database_path, username_to_add, add_days)
        logger.info(
            "Admin added subscription: admin_id=%s target_user_id=%s days=%s",
            message.from_user.id,
            username_to_add,
            add_days,
        )
        bot.send_message(username_to_add, f"💎Вам начислено {add_days} дней подписки ")
        bot.send_message(message.chat.id, f"Подписка для пользователя {username_to_add} добавлена")

    @bot.message_handler(commands=["sub_del"])
    def handle_sub_del(message):
        if not assert_admin(message):
            return

        parts = message.text.split()
        if len(parts) != 2:
            bot.send_message(
                message.chat.id,
                "Пожалуйста, укажите данные в виде: "
                "'/sub_del (телеграм айди пользователя)' "
                "для удаления подписки. ",
            )
            return

        database.remove_subscription(config.database_path, parts[1])
        logger.info(
            "Admin removed subscription: admin_id=%s target_user_id=%s",
            message.from_user.id,
            parts[1],
        )
        bot.send_message(message.chat.id, f"Подписка для пользователя {parts[1]} удалена")

    @bot.message_handler(commands=["replace_offers"])
    def handle_replace_offers(message):
        if not replacements.can_add_offers:
            logger.info("Replacement offer request rejected because offers are closed: user_id=%s", message.from_user.id)
            bot.send_message(message.chat.id, "Актуальные замены уже есть, команда станет доступна вновь в 8:00 ")
            return

        if message.from_user.id in replacements.photo_data.values():
            logger.info("Duplicate replacement offer request rejected: user_id=%s", message.from_user.id)
            bot.send_message(message.chat.id, "❗ Вы уже отправили фото, подождите пока его обработает администратор")
            return

        logger.info("Replacement offer flow started: user_id=%s", message.from_user.id)
        bot.send_message(message.chat.id, "Пожалуйста, отправьте фото для замены.")
        bot.register_next_step_handler(message, save_photo)

    def save_photo(message):
        if not replacements.can_add_offers:
            bot.send_message(message.chat.id, "Актуальные замены уже есть, команда станет доступна вновь в 8:00 ")
            return
        if not message.photo:
            bot.send_message(message.chat.id, "Пожалуйста, отправьте фото.")
            return

        downloaded_file = download_largest_photo(message)
        photo_filename = replacements.save_offer(downloaded_file, message.from_user.id)
        logger.info("Replacement offer photo received: user_id=%s filename=%s", message.from_user.id, photo_filename)
        if photo_filename == "1.png":
            bot.send_message(config.admin_chat_id, "Первая замена отправлена")

        photo_number = photo_filename.split(".")[0]
        bot.send_message(message.chat.id, f"Ваше фото было сохранено под номером {photo_number}. Ожидайте проверки.")

    @bot.message_handler(commands=["show_replace"])
    def handle_show_replace(message):
        if message.chat.id != config.admin_chat_id:
            logger.warning("Replacement review denied: user_id=%s", message.from_user.id)
            bot.send_message(message.chat.id, "У вас нет прав для этой команды.")
            return

        photos = replacements.list_offer_files()
        logger.info("Admin requested replacement review: count=%s", len(photos))
        if photos:
            show_photo(message.chat.id, photos[0])
        else:
            bot.send_message(message.chat.id, "Нет предложенных фото.")

    def show_photo(chat_id: int, photo_filename: str):
        try:
            with replacements.get_offer_path(photo_filename).open("rb") as photo_file:
                bot.send_photo(
                    chat_id,
                    photo_file,
                    reply_markup=create_replace_review_keyboard(photo_filename),
                )
        except Exception:
            logger.exception("Failed to show replacement photo: chat_id=%s filename=%s", chat_id, photo_filename)
            bot.send_message(chat_id, "Фото нет")

    def edit_photo(call, photo_filename: str):
        try:
            with replacements.get_offer_path(photo_filename).open("rb") as photo_file:
                media = types.InputMediaPhoto(photo_file.read())
                bot.edit_message_media(
                    media,
                    call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=create_replace_review_keyboard(photo_filename),
                )
        except Exception:
            logger.exception("Failed to edit replacement photo: filename=%s", photo_filename)
            bot.send_message(call.message.chat.id, "Фото закончились")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("next_"))
    def callback_next(call):
        current_photo = call.data.split("_")[1]
        photos = replacements.list_offer_files()
        try:
            current_index = photos.index(current_photo)
            next_photo = photos[(current_index + 1) % len(photos)]
            logger.info("Replacement review moved to next photo: current=%s next=%s", current_photo, next_photo)
            edit_photo(call, next_photo)
        except (ValueError, ZeroDivisionError):
            logger.warning("Failed to find next replacement photo: current=%s count=%s", current_photo, len(photos))
            bot.send_message(call.message.chat.id, "Ошибка при поиске следующего фото.")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("accept_"))
    def callback_accept(call):
        accepted_photo = call.data.split("_")[1]
        accepted_user, rejected_users = replacements.accept_offer(accepted_photo)
        logger.info(
            "Admin accepted replacement photo: filename=%s accepted_user=%s rejected_count=%s",
            accepted_photo,
            accepted_user,
            len(rejected_users),
        )

        if accepted_user is not None:
            database.add_subscription(config.database_path, accepted_user, 10)
            bot.send_message(
                accepted_user,
                "✅ Ваша замена была принята!\nВам начислено 10 дней премиум подписки",
            )

        for user_id in rejected_users:
            bot.send_message(user_id, "❌ К сожалению, ваша замена не была принята. ")

        notify_subscribers()
        bot.send_message(call.message.chat.id, "Фото принято и сохранено как replacements_tomorrow.png.")

    @bot.message_handler(commands=["rasp_s"])
    def handle_rasp_s(message):
        if message.from_user.id != config.admin_chat_id:
            logger.warning("Direct today replacement command denied: user_id=%s", message.from_user.id)
            bot.send_message(message.chat.id, "У вас нет прав на выполнение этой команды")
            return

        logger.info("Direct today replacement upload requested: admin_id=%s", message.from_user.id)
        last_command[message.from_user.id] = "/rasp_s"
        bot.send_message(message.chat.id, "Отправьте фото для замены на сегодня.")
        bot.register_next_step_handler(message, save_replace_photo)

    @bot.message_handler(commands=["rasp_z"])
    def handle_rasp_z(message):
        if message.from_user.id != config.admin_chat_id:
            logger.warning("Direct tomorrow replacement command denied: user_id=%s", message.from_user.id)
            bot.send_message(message.chat.id, "У вас нет прав на выполнение этой команды")
            return

        logger.info("Direct tomorrow replacement upload requested: admin_id=%s", message.from_user.id)
        last_command[message.from_user.id] = "/rasp_z"
        bot.send_message(message.chat.id, "Пожалуйста, отправьте фото для замены на завтра.")
        bot.register_next_step_handler(message, save_replace_photo)

    @bot.message_handler(commands=["clean_repl"])
    def clear_replacements(message):
        if message.from_user.id != config.admin_chat_id:
            logger.warning("Replacement cleanup command denied: user_id=%s", message.from_user.id)
            bot.send_message(message.chat.id, "У вас нет прав на выполнение этой команды")
            return

        try:
            replacements.clear_offers()
            replacements.can_add_offers = True
            logger.info("Replacement offers manually cleared: admin_id=%s", message.from_user.id)
            bot.send_message(message.chat.id, "Отчистка произошла успешно")
        except Exception as exc:
            logger.exception("Failed to clear replacement offers")
            bot.send_message(message.chat.id, f"Произошла ошибка: {exc}")

    def save_replace_photo(message):
        if not message.photo:
            bot.send_message(message.chat.id, "Пожалуйста, отправьте фото.")
            return

        command = last_command.get(message.from_user.id)
        if command == "/rasp_s":
            target = "today"
        elif command == "/rasp_z":
            target = "tomorrow"
        else:
            return

        try:
            filename = replacements.save_direct_replacement(target, download_largest_photo(message))
        except Exception as exc:
            logger.exception("Failed to save direct replacement photo: target=%s", target)
            bot.send_message(message.chat.id, "Не удалось сохранить фотографию: " + str(exc))
            return

        logger.info("Direct replacement photo saved: target=%s path=%s", target, filename)
        bot.reply_to(message, f"Фото успешно сохранено как {filename.name}")

    @bot.message_handler(func=lambda message: message.chat.type == "private")
    def echo_message(message):
        bot.send_message(message.chat.id, "Не знаю такую команду, используйте команду /start")

    def update_profile_message(call) -> None:
        user = database.get_user(config.database_path, call.from_user.id)
        if not user:
            logger.warning("Profile update failed because user row is missing: user_id=%s", call.from_user.id)
            bot.send_message(
                call.from_user.id,
                "❗ Произошла ошибка ❗\nСкорее всего сообщение не обновилось, "
                'для получения актуальной информации профиля рекомендуется ещё раз нажать кнопку "💻 Профиль"',
            )
            return

        try:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=format_profile(user, call.from_user.id),
                reply_markup=create_profile_keyboard(user.subscribe_status),
                parse_mode="HTML",
            )
        except Exception:
            logger.exception("Failed to update profile message: user_id=%s", call.from_user.id)
            bot.send_message(
                call.from_user.id,
                "❗ Произошла ошибка ❗\nСкорее всего сообщение не обновилось, "
                'для получения актуальной информации профиля рекомендуется ещё раз нажать кнопку "💻 Профиль"',
            )

    def ensure_profile_owner(call) -> bool:
        message_owner = extract_profile_owner_id(call.message.text or "")
        if message_owner is not None and call.from_user.id == message_owner:
            return True

        logger.warning(
            "Profile callback denied: user_id=%s message_owner=%s callback=%s",
            call.from_user.id,
            message_owner,
            call.data,
        )
        bot.answer_callback_query(call.id, "Нет доступа к чужому профилю")
        return False

    def download_largest_photo(message) -> bytes:
        photo = message.photo[-1]
        file_info = bot.get_file(photo.file_id)
        return bot.download_file(file_info.file_path)


def extract_profile_owner_id(text: str) -> int | None:
    match = re.search(r"ID:\s*(?:<code>)?(\d+)(?:</code>)?", text)
    if match:
        return int(match.group(1))
    return None


def format_profile(user: database.UserProfile, telegram_id: int) -> str:
    space_line = "================"
    user_group = user.user_group

    if user.subscribe_status:
        subscription_end_date = f"\n📅 Дата окончания подписки: {user.subscribe_end_date}\n{space_line}"
        user_subscribe_status = f"✅ Активна\n{space_line}"
    else:
        subscription_end_date = ""
        user_subscribe_status = "❌ Неактивна"

    if user.photo_mode:
        user_photo_mode = f"✅ Включён\n{space_line}"
    else:
        user_photo_mode = f"❌ Выключен\n{space_line}"

    if user.subscribe_status:
        if user.replacements_mode:
            user_replacements_mode = "\n🔁 Автоматическая отправка замен: ✅ Включёна"
        else:
            user_replacements_mode = "\n🔁 Автоматическая отправка замен: ❌ Выключена"
    else:
        user_replacements_mode = ""

    return (
        f"📙 Профиль\n\n👤 ID: <code>{telegram_id}</code> \n{space_line}\n"
        f"👥 Группа: {user_group}\n{space_line}\n"
        f"📷 Фото режим: {user_photo_mode}\n"
        f"💎 Статус подписки: {user_subscribe_status}{subscription_end_date}{user_replacements_mode}"
    )
