import telebot
from telebot import types
import os
import json
from dotenv import load_dotenv

from db import Session, engine
from models import *

load_dotenv()

Base.metadata.create_all(bind=engine)
session = Session()

API_KEY = os.environ["API_KEY"]
bot = telebot.TeleBot(API_KEY)


def get_current_user(uid):
    return session.query(User).filter(User.user_id == uid).first()


def is_admin(uid):
    user = get_current_user(uid)
    if user:
        return user.admin_status
    else:
        return False


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
    user = User(message.from_user.id, message.from_user.username)
    if not session.query(User).filter(User.user_id == message.from_user.id).scalar():
        session.add(user)
        session.commit()

    msg = f"Вітаю {message.from_user.first_name}!\n" \
          f"Це бот-архів для зручного доступу до відео тренувань.\n" \
          f"Щоб додати відео натисніть /add_video.\n" \
          f"Щоб переглянути відео натисніть /show_video"
    bot.send_message(message.chat.id, f"{msg}")


@bot.message_handler(commands=["get_admin_12345"])
def set_admin(message):
    user = get_current_user(message.chat.id)
    if user:
        user.admin_status = True
        session.commit()
        bot.send_message(message.chat.id, "Admin status granted!")
    else:
        bot.send_message(message.chat.id, "You have to register first! /start")


@bot.message_handler(commands=["add_video", "show_video", "bulk_add_video"])
@for_admin()
def add_video(message):
    used_command = message.text.replace("/", "").split("_")[0]
    categories_markup = types.InlineKeyboardMarkup(row_width=1)

    try:
        categories = session.query(Category).all()
        for category in categories:
            callback = {
                "mt": "ctg",
                "cmd": used_command,
                "ctg": category.category_id
            }
            category_button = types.InlineKeyboardButton(category.name,
                                                         callback_data=json.dumps(
                                                             callback,
                                                             separators=(',', ':')
                                                         ))
            categories_markup.add(category_button)
        if len(categories) == 0:
            bot.send_message(message.chat.id, "Немає категорій! Використайте /add_category, щоб додати категорію.")
        else:
            bot.send_message(message.chat.id, "Оберіть категорію нижче:", reply_markup=categories_markup)
    except Exception as e:
        print(e)
        bot.send_message(message.chat.id, "Виникла помилка, спробуйте ще раз або зв'яжіться з розробником.")


@bot.message_handler(commands=["add_category"])
@for_admin()
def add_category(message):
    bot.send_message(message.chat.id, "Введіть назву нової категорії:")
    bot.register_next_step_handler(message, add_new_category)


@bot.message_handler(commands=["delete_category"])
@for_admin()
def delete_category(message):
    try:
        categories = session.query(Category).all()
        if categories:
            categories_markup = create_category_markup("ctg_del", categories)
            bot.send_message(message.chat.id, "Оберіть категорію яку ви хочете видалити:",
                             reply_markup=categories_markup)
        else:
            bot.send_message(message.chat.id, "Немає категорій! Використайте /add_category, щоб додати категорію.")
    except Exception as e:
        print(e)
        bot.send_message(message.chat.id, "Виникла помилка, спробуйте ще раз або зв'яжіться з розробником.")


@bot.message_handler(commands=["rename_category"])
@for_admin()
def rename_category(message):
    try:
        categories = session.query(Category).all()
        if categories:
            categories_markup = create_category_markup("ctg_rnm", categories)
            bot.send_message(message.chat.id, "Оберіть категорію яку ви хочете перейменувати:",
                             reply_markup=categories_markup)
        else:
            bot.send_message(message.chat.id, "Немає категорій! Використайте /add_category, щоб додати категорію.")
    except Exception as e:
        print(e)
        bot.send_message(message.chat.id, "Виникла помилка, спробуйте ще раз або зв'яжіться з розробником.")


@bot.callback_query_handler(func=lambda call: check_callback(call, "ctg"))
def category_request_callback(call):
    data = json.loads(call.data)

    difficulty_markup = create_difficulty_markup(data.get("cmd"), data.get("ctg"))
    bot.send_message(call.message.chat.id, f"Оберіть рівень складності:", reply_markup=difficulty_markup)

    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
                                  reply_markup=types.InlineKeyboardMarkup())


@bot.callback_query_handler(func=lambda call: check_callback(call, "diff"))
def difficulty_request_callback(call):
    data = json.loads(call.data)
    difficulty = data.get("diff")
    category_id = data.get("ctg")
    category = session.query(Category).filter_by(category_id=category_id).first()
    videos = session.query(Video).filter_by(category_id=category_id, difficulty=difficulty).all()

    if data.get("cmd") == "add":
        bot.send_message(call.message.chat.id, "Надсилайте відео!")
        bot.register_next_step_handler(call.message, save_video, difficulty, category)
    elif data.get("cmd") == "show":
        if videos:
            for video in videos:
                send_video(call.message.chat.id, video.chat_id, video.video_id, video.description_id)
        else:
            bot.send_message(call.message.chat.id, "Відео нема😪")
    elif data.get("cmd") == "bulk":
        bot.send_message(call.message.chat.id, "Надсилайте відео!")
        bot.register_next_step_handler(call.message, bulk_add, difficulty, category)

    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
                                  reply_markup=types.InlineKeyboardMarkup())


@bot.callback_query_handler(func=lambda call: check_callback(call, "op_s"))
def open_settings_request_callback(call):
    video_id = json.loads(call.data).get("vid")
    change_markup = types.InlineKeyboardMarkup()
    for button_name, button_value in [("Змінити відео", "vd"), ("Змінити інструкцію", "vc"), ("Видалити", "del")]:
        callback = {
            "mt": "chng",
            "vid": video_id,
            "op": button_value
        }
        button = types.InlineKeyboardButton(button_name,
                                            callback_data=json.dumps(
                                                callback,
                                                separators=(',', ':')))
        change_markup.add(button)
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
                                  reply_markup=change_markup)


@bot.callback_query_handler(func=lambda call: check_callback(call, "chng"))
def settings_request_callback(call):
    data = json.loads(call.data)
    operation = data.get("op")

    video = session.query(Video).filter_by(video_id=data.get("vid")).first()
    if video:
        if operation == "vd":
            bot.send_message(call.message.chat.id, "Відправте нове відео:")
            bot.register_next_step_handler(call.message, change_video, video)
        elif operation == "vc":
            bot.send_message(call.message.chat.id, "Відправте нову інструкцію:")
            bot.register_next_step_handler(call.message, change_voice, video)
        elif operation == "del":
            session.delete(video)
            session.commit()
            bot.send_message(call.message.chat.id, "Вправу видалено!")

        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
                                      reply_markup=types.InlineKeyboardMarkup())
    else:
        bot.send_message(call.message.chat.id, "Виникла помилка, спробуйте ще раз або зв'яжіться з розробником.")


@bot.callback_query_handler(func=lambda call: check_callback(call, "ctg_del"))
def category_delete_request_callback(call):
    category_id = json.loads(call.data).get("ctg")
    bot.send_message(call.message.chat.id,
                     "Ви впевненні? При видалені категорії, "
                     "видаляються також усі відео та голосові повідомлення.\n"
                     "Введіть 'Так' для підтвердження.")
    bot.register_next_step_handler(call.message, delete_category_from_db, category_id)
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
                                  reply_markup=types.InlineKeyboardMarkup())


@bot.callback_query_handler(func=lambda call: check_callback(call, "ctg_rnm"))
def category_rename_request_callback(call):
    category_id = json.loads(call.data).get("ctg")
    bot.send_message(call.message.chat.id, "Введіть нову назву для категорії:")
    bot.register_next_step_handler(call.message, rename_category_from_db, category_id)
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
                                  reply_markup=types.InlineKeyboardMarkup())


def send_video(chat_id, from_chat_id, video_id, description_id):
    bot.forward_message(chat_id, from_chat_id, video_id)
    if description_id:
        bot.forward_message(chat_id, from_chat_id, description_id)
    callback = {
        "mt": "op_s",
        "vid": video_id
    }
    settings_markup = types.InlineKeyboardMarkup()
    settings_markup.add(
        types.InlineKeyboardButton(
            "⚙", callback_data=json.dumps(callback, separators=(",", ":"))
        ))
    bot.send_message(chat_id, "Дії над вправою⬇", reply_markup=settings_markup)


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


def bulk_add(message, difficulty, category):
    last_message = bot.send_message(message.chat.id, "Додаю відео....")
    videos = list(range(message.message_id, last_message.message_id))

    try:
        current_user = get_current_user(message.chat.id)
        for video_id in videos:
            video = Video(video_id, None, category, difficulty, current_user)
            session.add(video)
            session.commit()
        bot.send_message(message.chat.id, "Відео додано!")
    except Exception as e:
        print(e)
        bot.send_message(message.chat.id, "Виникла помилка, спробуйте ще раз або зв'яжіться з розробником.")


def change_video(message, video):
    try:
        video.video_id = message.message_id
        session.commit()
        bot.send_message(message.chat.id, "Відео змінено!")
    except Exception as e:
        print(e)
        bot.send_message(message.chat.id, "Виникла помилка, спробуйте ще раз або зв'яжіться з розробником.")


def change_voice(message, video):
    try:
        video.description_id = message.message_id
        session.commit()
        bot.send_message(message.chat.id, "Інструкцію змінено!")
    except Exception as e:
        print(e)
        bot.send_message(message.chat.id, "Виникла помилка, спробуйте ще раз або зв'яжіться з розробником.")


def create_difficulty_markup(cmd, ctg):
    difficulty_markup = types.InlineKeyboardMarkup(row_width=1)
    for button_name, button_value in [("Дім", 1), ("Зал", 2)]:
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


def create_category_markup(method, categories):
    categories_markup = types.InlineKeyboardMarkup(row_width=1)
    for category in categories:
        callback = {
            "mt": method,
            "ctg": category.category_id
        }
        category_button = types.InlineKeyboardButton(category.name,
                                                     callback_data=json.dumps(
                                                         callback,
                                                         separators=(',', ':')
                                                     ))
        categories_markup.add(category_button)

    return categories_markup


def add_new_category(message):
    try:
        new_category = Category(name=message.text)
        session.add(new_category)
        session.commit()
        bot.send_message(message.chat.id, "Нову категорію додано!")
    except Exception as e:
        print(e)
        bot.send_message(message.chat.id, "Виникла помилка, спробуйте ще раз або зв'яжіться з розробником.")


def delete_category_from_db(message, category_id):
    if message.text.lower() == "так":
        try:
            category = session.query(Category).filter_by(category_id=category_id).first()
            for video in category.videos:
                session.delete(video)
            session.delete(category)
            session.commit()
            bot.send_message(message.chat.id, "Категорію успішно видалено!")
        except Exception as e:
            print(e)
            bot.send_message(message.chat.id, "Виникла помилка, спробуйте ще раз або зв'яжіться з розробником.")


def rename_category_from_db(message, category_id):
    try:
        category = session.query(Category).filter_by(category_id=category_id).first()
        category.name = message.text.strip()
        session.commit()
        bot.send_message(message.chat.id, "Категорію успішно перейменовано!")
    except Exception as e:
        print(e)
        bot.send_message(message.chat.id, "Виникла помилка, спробуйте ще раз або зв'яжіться з розробником.")


if __name__ == '__main__':
    print("Start working!")
    bot.polling(none_stop=True)
