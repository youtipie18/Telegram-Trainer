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


def create_profile_message(user, chat_id):
    if user.sex:
        sex = "Чоловік" if user.sex == "male" else "Жінка"
    else:
        sex = None
    msg = f"Ваша стать: {sex}\n" \
          f"Ваш вік: {user.age}\n" \
          f"Ваш зріст: {user.height} м.\n" \
          f"Ваша вага: {user.weight} кг.\n" \
          f"Віш час тренування: {user.workout_time} год.\n"
    if user.age and user.weight and user.height:

        if user.sex == "male":
            calories = round((9.99 * user.weight) + (6.25 * user.height) - (4.92 * user.age) + 5, 2)
        else:
            calories = round((9.99 * user.weight) + (6.25 * user.height) - (4.92 * user.age) - 161, 2)
        if user.workout_time:
            water = f"{round(30 * user.weight + 500 * user.workout_time)}-{round(35 * user.weight + 500 * user.workout_time)}"
        else:
            water = f"{round(30 * user.weight)}-{round(35 * user.weight)}"
        msg += f"Ваші калорії: {calories} ккал.\n" \
               f"Ваш водневий баланс: {water} мл.\n"

    callback = {
        "mt": "profile_op_s"
    }
    settings_markup = types.InlineKeyboardMarkup()
    settings_markup.add(
        types.InlineKeyboardButton(
            "⚙", callback_data=json.dumps(callback, separators=(",", ":"))
        ))
    bot.send_message(chat_id, msg, reply_markup=settings_markup)


@bot.message_handler(commands=["profile"])
@for_admin()
def profile(message):
    user = get_current_user(message.chat.id)
    create_profile_message(user, message.chat.id)


@bot.callback_query_handler(func=lambda call: check_callback(call, "profile_op_s"))
def open_profile_settings_request_callback(call):
    change_markup = types.InlineKeyboardMarkup()
    for button_name, button_value in [("Змінити стать", "sex"), ("Змінити вік", "age"), ("Змінити зріст", "height"),
                                      ("Змінити вагу", "weight"), ("Змінити час тренування", "time")]:
        callback = {
            "mt": "prfile_chng",
            "op": button_value
        }
        button = types.InlineKeyboardButton(button_name,
                                            callback_data=json.dumps(
                                                callback,
                                                separators=(',', ':')))
        change_markup.add(button)
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
                                  reply_markup=change_markup)


@bot.callback_query_handler(func=lambda call: check_callback(call, "prfile_chng"))
def change_profile(call):
    data = json.loads(call.data)
    if data.get("op") == "age":
        msg = "Введіть новий вік:"
    elif data.get("op") == "weight":
        msg = "Введіть нову вагу в кг:"
    elif data.get("op") == "height":
        msg = "Введіть новий зріст у метрах:"
    elif data.get("op") == "time":
        msg = "Введіть новий час тренування у годинах (Наприклад одна година, тридцять хвилин буде 1.5):"
    else:
        msg = "Оберіть нову стать:"

    change_markup = types.InlineKeyboardMarkup()
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=change_markup)
    if data.get("op") != "sex":
        bot.send_message(call.message.chat.id, msg)
        bot.register_next_step_handler(call.message, change_profile_db, data.get("op"))
    else:
        markup = types.InlineKeyboardMarkup()
        for button_name, button_value in [("Чоловік", "male"), ("Жінка", "female")]:
            callback = {
                "mt": "chng_sex",
                "v": button_value
            }
            button = types.InlineKeyboardButton(button_name,
                                                callback_data=json.dumps(
                                                    callback,
                                                    separators=(',', ':')))
            markup.add(button)
        bot.send_message(call.message.chat.id, msg, reply_markup=markup)


@bot.callback_query_handler(func=lambda call: check_callback(call, "chng_sex"))
def change_sex(call):
    data = json.loads(call.data)
    user = get_current_user(call.message.chat.id)
    user.sex = data.get("v")
    session.commit()
    change_markup = types.InlineKeyboardMarkup()
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
                                  reply_markup=change_markup)
    bot.send_message(call.message.chat.id, "Стать успішно змінено!")

    user = get_current_user(call.message.chat.id)
    create_profile_message(user, call.message.chat.id)


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

    try:
        categories = session.query(Category).all()
        categories_markup = create_category_markup("ctg", categories=categories, command=used_command)

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
            categories_markup = create_category_markup("ctg_del", categories=categories, command=None)
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
            categories_markup = create_category_markup("ctg_rnm", categories=categories, command=None)
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
    bot.forward_message(chat_id, from_chat_id, video_id, protect_content=True)
    if description_id:
        bot.forward_message(chat_id, from_chat_id, description_id, protect_content=True)
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
    elif message.text.lower() == "стоп":
        bot.send_message(message.chat.id, "Операцію зупинено!")
    else:
        bot.send_message(message.chat.id, "Це не відео. Спробуйте ще раз! "
                                          "Напишіть стоп, щоб припинити додавання відео.")
        bot.register_next_step_handler(message, save_video, difficulty, category)


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
        button_name = f"{button_name}({session.query(Video).filter_by(difficulty=button_value).count()} 🎬)"
        difficulty_button = types.InlineKeyboardButton(button_name,
                                                       callback_data=json.dumps(
                                                           callback,
                                                           separators=(',', ':')))
        difficulty_markup.add(difficulty_button)
    return difficulty_markup


def create_category_markup(method, command, categories):
    categories_markup = types.InlineKeyboardMarkup(row_width=1)
    for category in categories:
        callback = {
            "mt": method,
            "cmd": command,
            "ctg": category.category_id
        }
        button_name = f"{category.name}({len(category.videos)} 🎬)"
        category_button = types.InlineKeyboardButton(button_name,
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


def change_profile_db(message, value_to_change):
    try:
        user = get_current_user(message.chat.id)
        if value_to_change == "age":
            user.age = float(message.text.strip().replace(",", "."))
        elif value_to_change == "weight":
            user.weight = float(message.text.strip().replace(",", "."))
        elif value_to_change == "height":
            user.height = float(message.text.strip().replace(",", "."))
        elif value_to_change == "time":
            user.workout_time = float(message.text.strip().replace(",", "."))
        session.commit()
        bot.send_message(message.chat.id, "Значення успішно змінено!")
        create_profile_message(user, message.chat.id)
    except Exception as e:
        print(e)
        bot.send_message(message.chat.id, "Виникла помилка, спробуйте ще раз або зв'яжіться з розробником.")


if __name__ == '__main__':
    print("Start working!")
    bot.polling(none_stop=True)
