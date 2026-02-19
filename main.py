import os
import telebot
import sqlite3
from flask import Flask
from threading import Thread
from datetime import datetime
from telebot import types

# Созламалар
TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)
app = Flask('')

# --- БАЗА БИЛАН ИШЛАШ ---
def init_db():
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS transactions 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                       user_id INTEGER, 
                       type TEXT, 
                       category TEXT, 
                       amount INTEGER, 
                       date TEXT)''')
    conn.commit()
    conn.close()

def add_transaction(user_id, t_type, category, amount):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    date = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute("INSERT INTO transactions (user_id, type, category, amount, date) VALUES (?, ?, ?, ?, ?)",
                   (user_id, t_type, category, amount, date))
    conn.commit()
    conn.close()

def get_stats(user_id):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute("SELECT type, SUM(amount) FROM transactions WHERE user_id = ? GROUP BY type", (user_id,))
    data = cursor.fetchall()
    conn.close()
    return data

# --- ТЕЛЕГРАМ МЕНЮСИ ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("➖ Харажат", "➕ Даромад")
    markup.add("📊 Статистика", "📅 Ойлик ҳисобот")
    return markup

# --- БОТ БУЙРУҚЛАРИ ---
@bot.message_handler(commands=['start'])
def start(message):
    init_db()
    bot.send_message(message.chat.id, 
                     f"Салом {message.from_user.first_name}! Хизматчи ботга хуш келибсиз.\n\n"
                     "Қуйидаги менюдан фойдаланинг:", 
                     reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "📊 Статистика")
def show_stats(message):
    stats = get_stats(message.chat.id)
    text = "📊 **Умумий ҳисоб:**\n\n"
    if not stats:
        text += "Ҳали маълумот йўқ."
    else:
        for s_type, s_sum in stats:
            icon = "💰" if s_type == "Даромад" else "💸"
            text += f"{icon} {s_type}: {s_sum:,} сўм\n"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text in ["➖ Харажат", "➕ Даромад"])
def ask_amount(message):
    msg = bot.send_message(message.chat.id, "Суммани ва нималигини ёзинг.\n\nМисол: `Обед 25000` ёки `Ойлик 5000000`", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_transaction, message.text)

def process_transaction(message, t_type):
    try:
        parts = message.text.split()
        if len(parts) < 2:
            raise ValueError
        
        category = parts[0]
        amount = int(parts[1])
        t_real_type = "Даромад" if "Даромад" in t_type else "Харажат"
        
        add_transaction(message.chat.id, t_real_type, category, amount)
        bot.send_message(message.chat.id, f"✅ Сақланди!\n{t_real_type}: {category}\nСумма: {amount:,} сўм", reply_markup=main_menu())
    except:
        bot.send_message(message.chat.id, "❌ Хато! Илтимос, мисолдек ёзинг: `Обед 25000`", reply_markup=main_menu())

# --- RENDER УЧУН ТЕХНИК ҚИСМ ---
@app.route('/')
def home():
    return "Бот 24/7 ишлаяпти!"

if __name__ == "__main__":
    init_db() # Базани яратиш
    port = int(os.environ.get("PORT", 8080))
    t = Thread(target=lambda: app.run(host='0.0.0.0', port=port))
    t.start()
    print("Бот ёқилди...")
    bot.polling(none_stop=True)
