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
    # one_time_keyboard=False қўшилди, тугмалар йўқолмайди
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False, row_width=2)
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
    # Бу ердан ReplyKeyboardRemove олиб ташланди, тугмалар ўчмайди
    msg = bot.send_message(message.chat.id, f"{t_type} суммасини ёзинг (ёки 'Nom Summa'):")
    bot.register_next_step_handler(msg, process_manual_entry, t_type)

def process_manual_entry(message, t_type):
    try:
        text = message.text.strip()
        parts = text.split()
        
        # Агар фақат рақам бўлса
        if text.isdigit():
            category = "Boshqa"
            amount = int(text)
        # Агар 'Ойлик 3000000' кўринишида бўлса
        elif len(parts) >= 2 and parts[-1].isdigit():
            category = " ".join(parts[:-1])
            amount = int(parts[-1])
        else:
            raise ValueError

        save_to_db(message.chat.id, t_type, category, amount)
        bot.send_message(message.chat.id, f"✅ Сақланди!\n{t_type}: {category}\nСумма: {amount:,} сўм", reply_markup=main_menu())
    except:
        bot.send_message(message.chat.id, "❌ Хато! Суммани рақамда ёзинг. Масалан: '44000' ёки 'Ойлик 3000000'", reply_markup=main_menu())

# --- ОЙЛИК ҲИСОБОТ (Янги қўшилган қисм) ---
@bot.message_handler(func=lambda m: m.text == "📅 Ойлик ҳисобот")
def monthly_report(message):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    current_month = datetime.now().strftime("%Y-%m")
    
    cursor.execute("SELECT type, SUM(amount) FROM finance WHERE uid = ? AND date LIKE ? GROUP BY type", 
                   (message.chat.id, f"{current_month}%"))
    data = dict(cursor.fetchall())
    conn.close()

    if not data:
        bot.send_message(message.chat.id, "📅 Бу ой учун ҳали маълумот йўқ.")
        return

    d_sum = data.get("💰 Даромад", 0)
    x_sum = data.get("💸 Харажат", 0)
    
    report = f"📅 **{current_month} ойи учун ҳисобот:**\n\n"
    report += f"💰 Жами Даромад: {d_sum:,} сўм\n"
    report += f"💸 Жами Харажат: {x_sum:,} сўм\n"
    report += f"⚖️ Ойлик соф фойда: {d_sum - x_sum:,} сўм"
    
    bot.send_message(message.chat.id, report, parse_mode="Markdown")

# --- ТЕЗКОР ЁЗИШ (Тугмани босмасдан) ---
@bot.message_handler(func=lambda m: True)
def quick_entry(message):
    text = message.text.strip()
    
    # Статистика ва Ойлик ҳисоботни ўтказиб юборамиз
    if text == "📊 Статистика":
        show_stats(message)
        return
    if text == "📅 Ойлик ҳисобот":
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
    
    res += f"📈 Жами Даромад: {d_sum:,} сўм\n"
    res += f"📉 Жами Харажат: {x_sum:,} сўм\n"
    res += f"⚖️ **Соф фойда: {d_sum - x_sum:,} сўм**"
    
    bot.send_message(message.chat.id, res, parse_mode="Markdown")

@app.route('/')
def home(): return "OK"

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    Thread(target=lambda: app.run(host='0.0.0.0', port=port)).start()
    
    print("Бот ишга тушди...")
    
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f"Хато: {e}")
            time.sleep(5)
