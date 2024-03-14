import telebot
from telebot import types
import os
import json
# TODO: Improve requests sending with encoding
import zlib

from db import Session, engine
from models import *

Base.metadata.create_all(bind=engine)
session = Session()

API_KEY = os.environ["API_KEY"]
bot = telebot.TeleBot(API_KEY)


def get_current_user(uid):
    return session.query(User).filter(User.user_id == uid).one()


def is_admin(uid):
    admin_status = session.query(User).filter(User.user_id == uid).one().admin_status
    return admin_status


def for_admin():
    def decorator(func):
        def wrapper(*args):
            message = args[0]
            if type(message) == telebot.types.Message:
                if is_admin(message.from_user.id):
                    func(message)
                else:
                    bot.send_message(message.chat.id, "У вас нема прав!")
            else:
                raise ValueError(f"Invalid arg type. Got: {type(message)}, expected: {telebot.types.Message}")

        return wrapper

    return decorator


def check_callback(call, method):
    data = json.loads(call.data)
    return data.get("mt") == method


@bot.message_handler(commands=["start"])
def start(message):
    user = User(message.from_user.id)
    if not session.query(User).filter(User.user_id == message.from_user.id).scalar():
        session.add(user)
        session.commit()

    msg = f"Вітаю {message.from_user.first_name}!\n" \
          f"Це бот-архів для зручного доступу до відео тренувань.\n" \
          f"Щоб додати відео натисніть /add_video.\n" \
          f"Щоб переглянути відео натисніть /show_video"
    bot.send_message(message.chat.id, f"{msg}")


@bot.message_handler(commands=["add_video", "show_video"])
@for_admin()
def add_video(message):
    used_command = message.text.replace("/", "")
    categories_markup = types.InlineKeyboardMarkup(row_width=1)

    try:
        categories = session.query(Category).all()
        for category in categories:
            callback = {
                "mt": "ctg",
                "cmd": used_command,
                "data": category.category_id
            }
            category_button = types.InlineKeyboardButton(category.name,
                                                         callback_data=json.dumps(
                                                             callback,
                                                             separators=(',', ':')
                                                         ))
            categories_markup.add(category_button)
        if used_command == "add_video":
            callback = {
                "mt": "ctg",
                "cmd": used_command,
                "data": "new"
            }
            new_category_button = types.InlineKeyboardButton("Нова категорія",
                                                             callback_data=json.dumps(
                                                                 callback,
                                                                 separators=(',', ':')
                                                             ))
            categories_markup.add(new_category_button)
        if used_command == "show_video" and len(categories) == 0:
            bot.send_message(message.chat.id, "Немає категорій! Використайте /add_video, щоб додати категорію.")
        else:
            bot.send_message(message.chat.id, "Оберіть категорію нижче:", reply_markup=categories_markup)
    except Exception as e:
        print(e)
        bot.send_message(message.chat.id, "Виникла помилка, спробуйте ще раз або зв'яжіться з розробником.")


@bot.callback_query_handler(func=lambda call: check_callback(call, "ctg"))
def category_request_callback(call):
    data = json.loads(call.data)

    if data.get("data") == "new":
        bot.send_message(call.message.chat.id, "Введіть назву нової категорії:")
        bot.register_next_step_handler(call.message, add_new_category)
    else:
        difficulty_markup = create_difficulty_markup(data.get("cmd"), data.get("data"))
        bot.send_message(call.message.chat.id, f"Оберіть рівень складності:", reply_markup=difficulty_markup)
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
                                  reply_markup=types.InlineKeyboardMarkup())


@bot.callback_query_handler(func=lambda call: check_callback(call, "diff"))
def difficulty_request_callback(call):
    data = json.loads(call.data)
    difficulty = data.get("diff")
    category_id = data.get("ctg")
    category = session.query(Category).filter_by(category_id=category_id).first()

    if data.get("cmd") == "add_video":
        bot.send_message(call.message.chat.id, "Надсилайте відео!")
        bot.register_next_step_handler(call.message, save_video, difficulty, category)
    elif data.get("cmd") == "show_video":
        for video in category.videos:
            send_video(call.message.chat.id, video.chat_id, video.video_id, video.description_id)

    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
                                  reply_markup=types.InlineKeyboardMarkup())


def send_video(chat_id, from_chat_id, video_id, description_id):
    bot.forward_message(chat_id, from_chat_id, video_id)
    bot.forward_message(chat_id, from_chat_id, description_id)


def save_video(message, difficulty, category):
    if message.video:
        bot.send_message(message.chat.id, "Тепер надсилайте інструкцію:")
        bot.register_next_step_handler(message, save_voice, message.message_id, difficulty, category)
    else:
        bot.send_message(message.chat.id, "Це не відео єблан")


def save_voice(message, video_id, difficulty, category):
    try:
        current_user = get_current_user(message.chat.id)
        new_video = Video(video_id, message.message_id, category, difficulty, current_user)
        session.add(new_video)
        session.commit()

        bot.send_message(message.chat.id, "Відео та інструкцію додано!")
    except Exception as e:
        print(e)
        bot.send_message(message.chat.id, "Виникла помилка, спробуйте ще раз або зв'яжіться з розробником.")


def create_difficulty_markup(cmd, ctg):
    difficulty_markup = types.InlineKeyboardMarkup(row_width=1)
    for button_name, button_value in [("Новачок", 1), ("Середнячок", 2), ("Профі", 3)]:
        callback = {
            "mt": "diff",
            "cmd": cmd,
            "ctg": ctg,
            "diff": button_value
        }
        difficulty_button = types.InlineKeyboardButton(button_name,
                                                       callback_data=json.dumps(
                                                           callback,
                                                           separators=(',', ':')))
        difficulty_markup.add(difficulty_button)
    return difficulty_markup


def add_new_category(message):
    try:
        new_category = Category(name=message.text)
        session.add(new_category)
        session.commit()
        bot.send_message(message.chat.id, "Нову категорію додано!")

        bot.send_message(message.chat.id, f"Оберіть рівень складності:",
                         reply_markup=create_difficulty_markup("add_video", new_category.category_id))
    except Exception as e:
        print(e)
        bot.send_message(message.chat.id, "Виникла помилка, спробуйте ще раз або зв'яжіться з розробником.")


if __name__ == '__main__':
    print("Start working!")
    bot.polling(none_stop=True)
