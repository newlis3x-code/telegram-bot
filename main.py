import os
import threading
import time
import schedule
from telebot import TeleBot, types
from dotenv import load_dotenv
from pathlib import Path

# --- Загрузка токена из .env ---
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    print("⚠️ Токен не найден! Проверь файл .env")
    exit()

bot = TeleBot(TOKEN)

# --- Хранилища состояния ---
user_state = {}
user_reminders = {}

# --- Меню ---
def main_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.add("➕ Добавить напоминание")
    m.add("📋 Мои напоминания")
    m.add("❌ Удалить напоминание")
    return m

def period_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.add("📅 Каждый день")
    m.add("📆 День недели")
    m.add("🔁 Каждую неделю")
    return m

def week_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for d in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]:
        m.add(d)
    return m

# --- Хэндлеры ---
@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(message.chat.id,
                     "Привет! Я бот напоминаний 🙂",
                     reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "➕ Добавить напоминание")
def add_reminder(message):
    bot.send_message(message.chat.id, "Напиши текст напоминания:")
    user_state[message.chat.id] = {"step": "text"}

@bot.message_handler(func=lambda m: m.text in ["📅 Каждый день", "📆 День недели", "🔁 Каждую неделю"])
def choose_period(message):
    state = user_state.get(message.chat.id)
    if not state or state.get("step") != "period":
        return
    state["period"] = message.text
    if message.text == "📆 День недели":
        bot.send_message(message.chat.id, "Выбери день недели:", reply_markup=week_menu())
        state["step"] = "week_day"
    else:
        bot.send_message(message.chat.id, "Введи время (HH:MM):")
        state["step"] = "time"

@bot.message_handler(func=lambda m: m.text in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"])
def choose_week_day(message):
    state = user_state.get(message.chat.id)
    if not state or state.get("step") != "week_day":
        return
    state["day"] = message.text
    bot.send_message(message.chat.id, "Введи время (HH:MM):")
    state["step"] = "time"

@bot.message_handler(func=lambda m: m.text == "📋 Мои напоминания")
def show_reminders(message):
    chat_id = message.chat.id
    reminders = user_reminders.get(chat_id)
    if not reminders:
        bot.send_message(chat_id, "У тебя пока нет напоминаний 🙂")
        return
    text = "📋 Твои напоминания:\n\n"
    for i, r in enumerate(reminders, 1):
        text += f"{i}. {r['text']}\n"
        if r["period"] == "📅 Каждый день":
            text += "   Повтор: каждый день\n"
        elif r["period"] == "🔁 Каждую неделю":
            text += "   Повтор: каждую неделю\n"
        else:
            text += f"   Повтор: {r['day']} каждую неделю\n"
        text += f"   Время: {r['time']}\n\n"
    bot.send_message(chat_id, text)

@bot.message_handler(func=lambda m: m.text == "❌ Удалить напоминание")
def delete_start(message):
    chat_id = message.chat.id
    reminders = user_reminders.get(chat_id)
    if not reminders:
        bot.send_message(chat_id, "Удалять нечего 🙂")
        return
    bot.send_message(chat_id, "Напиши номер напоминания для удаления:")
    user_state[chat_id] = {"step": "delete"}

@bot.message_handler(content_types=["text"])
def text_handler(message):
    chat_id = message.chat.id
    state = user_state.get(chat_id)
    if not state:
        return

    if state["step"] == "text":
        state["text"] = message.text
        bot.send_message(chat_id, "Как часто напоминать?", reply_markup=period_menu())
        state["step"] = "period"

    elif state["step"] == "time":
        try:
            h, m = map(int, message.text.split(":"))
            assert 0 <= h < 24 and 0 <= m < 60
        except:
            bot.send_message(chat_id, "Неверный формат. Пример: 09:30")
            return
        state["time"] = message.text
        create_job(chat_id, state)
        bot.send_message(chat_id, "Готово ✅", reply_markup=main_menu())
        user_state.pop(chat_id)

    elif state["step"] == "delete":
        try:
            num = int(message.text) - 1
            reminder = user_reminders[chat_id].pop(num)
            reminder["job"].cancel()
            bot.send_message(chat_id, "Удалено ✅", reply_markup=main_menu())
            user_state.pop(chat_id)
        except:
            bot.send_message(chat_id, "Неверный номер")

# --- Планирование напоминаний ---
def create_job(chat_id, state):
    text = state["text"]
    period = state["period"]
    t = state["time"]

    def job():
        bot.send_message(chat_id, text)

    if period == "📅 Каждый день":
        j = schedule.every().day.at(t).do(job)
    elif period == "🔁 Каждую неделю":
        j = schedule.every().week.at(t).do(job)
    else:
        days = {
            "Пн": schedule.every().monday,
            "Вт": schedule.every().tuesday,
            "Ср": schedule.every().wednesday,
            "Чт": schedule.every().thursday,
            "Пт": schedule.every().friday,
            "Сб": schedule.every().saturday,
            "Вс": schedule.every().sunday,
        }
        j = days[state["day"]].at(t).do(job)

    state["job"] = j
    user_reminders.setdefault(chat_id, []).append(state.copy())

def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(1)

# --- Запуск планировщика в отдельном потоке ---
threading.Thread(target=run_schedule, daemon=True).start()

# --- Запуск бота ---
bot.infinity_polling()
