import os, telebot, sqlite3
from flask import Flask
from threading import Thread
from telebot import types
from datetime import datetime
import time

TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)
app = Flask('')

# --- БАЗАНИ СОЗЛАШ ---
def init_db():
    conn = sqlite3.connect('finance.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS finance 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                       uid INTEGER, type TEXT, category TEXT, amount INTEGER, date TEXT)''')
    conn.commit()
    conn.close()

def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("💸 Харажат", "💰 Даромад")
    markup.add("📊 Статистика", "📅 Ойлик ҳисобот")
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    init_db()
    bot.send_message(message.chat.id, "Салом! Мен тайёрман.\n\n"
                     "1. Тугмани босиб сумма ёзинг.\n"
                     "2. Ёки шунчаки 'Обед 20000' деб ёзинг.\n"
                     "3. Ёки фақат рақам ёзинг (автоматик харажат бўлади).", reply_markup=main_menu())

# --- ТУГМАЛАР УЧУН ЛОГИКА ---
@bot.message_handler(func=lambda m: m.text in ["💸 Харажат", "💰 Даромад"])
def handle_button(message):
    t_type = message.text
    msg = bot.send_message(message.chat.id, f"{t_type} суммасини ёзинг (ёки 'Номи Сумма'):", reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, process_manual_entry, t_type)

def process_manual_entry(message, t_type):
    try:
        text = message.text.strip()
        parts = text.split()
        
        if text.isdigit():
            category = "Boshqa"
            amount = int(text)
        elif len(parts) >= 2 and parts[-1].isdigit():
            category = " ".join(parts[:-1])
            amount = int(parts[-1])
        else:
            raise ValueError

        save_to_db(message.chat.id, t_type, category, amount)
        bot.send_message(message.chat.id, f"✅ Сақланди!\n{t_type}: {category}\nСумма: {amount:,} сўм", reply_markup=main_menu())
    except:
        bot.send_message(message.chat.id, "❌ Хато! Суммани рақамда ёзинг. Масалан: '44000' ёки 'Ойлик 3000000'", reply_markup=main_menu())

# --- ТЕЗКОР ЁЗИШ (Тугмани босмасдан) ---
@bot.message_handler(func=lambda m: True)
def quick_entry(message):
    text = message.text.strip()
    if text == "📊 Статистика":
        show_stats(message)
        return

    try:
        if text.isdigit():
            save_to_db(message.chat.id, "💸 Харажат", "Boshqa", int(text))
            bot.reply_to(message, f"✅ Харажатга сақланди: {int(text):,} сўм")
        elif len(message.text.split()) >= 2 and message.text.split()[-1].isdigit():
            parts = message.text.split()
            category = " ".join(parts[:-1])
            amount = int(parts[-1])
            save_to_db(message.chat.id, "💸 Харажат", category, amount)
            bot.reply_to(message, f"✅ Харажатга сақланди!\n{category}: {amount:,} сўм")
    except:
        pass

def save_to_db(uid, t_type, category, amount):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO finance (uid, type, category, amount, date) VALUES (?, ?, ?, ?, ?)",
                   (uid, t_type, category, amount, datetime.now().strftime("%Y-%m-%d")))
    conn.commit()
    conn.close()

# --- СТАТИСТИКА ---
@bot.message_handler(func=lambda m: m.text == "📊 Статистика")
def show_stats(message):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute("SELECT type, category, SUM(amount) FROM finance WHERE uid = ? GROUP BY type, category", (message.chat.id,))
    rows = cursor.fetchall()
    cursor.execute("SELECT type, SUM(amount) FROM finance WHERE uid = ? GROUP BY type", (message.chat.id,))
    totals = dict(cursor.fetchall())
    conn.close()

    if not rows:
        bot.send_message(message.chat.id, "Ҳали маълумот йўқ.")
        return

    res = "📊 **Муфассал ҳисобот:**\n"
    for t_type, cat, amt in rows:
        icon = "💰" if "Даромад" in t_type else "💸"
        res += f"\n{icon} {t_type} ({cat}): {amt:,} сўм"
    
    res += "\n\n" + "—" * 15 + "\n"
    d_sum = totals.get("💰 Даромад", 0)
    x_sum = totals.get("💸 Харажат", 0)
    res += f"📈 Жами Даромад: {d_sum:,} сўм\n📉 Жами Харажат: {x_sum:,} сўм\n⚖️ **Соф фойда: {d_sum - x_sum:,} сўм**"
    bot.send_message(message.chat.id, res, parse_mode="Markdown")

@app.route('/')
def home(): return "OK"

# --- ЭНГ МУҲИМ ҚИСМ: АВТО-РЕСТАРТ ВА polling ---
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    # Веб-серверни алоҳида оқимда юргизиш (Render учун)
    Thread(target=lambda: app.run(host='0.0.0.0', port=port)).start()
    
    print("Бот ишга тушди...")
    
    # Хато юз берса, ботни қайта тирилтирувчи цикл
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f"Polling хатоси: {e}. 5 сониядан кейин қайта уланиш...")
            time.sleep(5)
