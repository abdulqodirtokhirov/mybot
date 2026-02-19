import os, telebot, sqlite3
from flask import Flask
from threading import Thread
from telebot import types
from datetime import datetime

# Созламалар
TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)
app = Flask('')

# --- БАЗА БИЛАН ИШЛАШ ---
def init_db():
    conn = sqlite3.connect('finance.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS finance 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                       uid INTEGER, 
                       type TEXT, 
                       amount INTEGER, 
                       date TEXT)''')
    conn.commit()
    conn.close()

# --- МЕНЮЛАР ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("💸 Харажат", "💰 Даромад")
    markup.add("📊 Статистика", "📅 Ойлик ҳисобот")
    return markup

# --- БОТ БУЙРУҚЛАРИ ---
@bot.message_handler(commands=['start'])
def start(message):
    init_db()
    bot.send_message(message.chat.id, 
                     f"Салом {message.from_user.first_name}! Хизматчи бот тайёр.\n"
                     "Даромад ёки Харажатни босиб, суммани юборинг.", 
                     reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text in ["💸 Харажат", "💰 Даромад"])
def ask_amount(message):
    msg = bot.send_message(message.chat.id, f"{message.text} миқдорини ёзинг (масалан: 20000):")
    bot.register_next_step_handler(msg, save_transaction, message.text)

def save_transaction(message, t_type):
    try:
        # Фақат рақамни ажратиб оламиз ва пробелларни ўчирамиз
        amount = int(message.text.replace(" ", ""))
        user_id = message.chat.id
        date_now = datetime.now().strftime("%Y-%m-%d")

        conn = sqlite3.connect('finance.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO finance (uid, type, amount, date) VALUES (?, ?, ?, ?)",
                       (user_id, t_type, amount, date_now))
        conn.commit()
        conn.close()

        bot.send_message(message.chat.id, f"✅ Сақланди!\n{t_type}: {amount:,} сўм", reply_markup=main_menu())
    except ValueError:
        bot.send_message(message.chat.id, "❌ Хато! Илтимос, суммани фақат рақамда ёзинг (масалан: 50000).", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "📊 Статистика")
def show_stats(message):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute("SELECT type, SUM(amount) FROM finance WHERE uid = ? GROUP BY type", (message.chat.id,))
    data = cursor.fetchall()
    conn.close()

    if not data:
        bot.send_message(message.chat.id, "Ҳали маълумот йўқ.")
        return

    res = "📊 **Умумий ҳисобот:**\n\n"
    total_balance = 0
    for t_type, total in data:
        icon = "💸" if "Харажат" in t_type else "💰"
        res += f"{icon} {t_type}: {total:,} сўм\n"
        if "Даромад" in t_type: total_balance += total
        else: total_balance -= total
    
    res += f"\n💰 **Соф фойда:** {total_balance:,} сўм"
    bot.send_message(message.chat.id, res, parse_mode="Markdown")

# --- RENDER УЧУН ТЕХНИК ҚИСМ ---
@app.route('/')
def home():
    return "Бот 24/7 ишлаяпти!"

if __name__ == "__main__":
    init_db()
    # Render портини тўғри созлаш
    port = int(os.environ.get("PORT", 10000))
    t = Thread(target=lambda: app.run(host='0.0.0.0', port=port))
    t.start()
    print("Бот ёқилди...")
    bot.polling(none_stop=True)
