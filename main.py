import os, telebot, sqlite3
from flask import Flask
from threading import Thread
from telebot import types
from datetime import datetime
import time

TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)
app = Flask('')

MONTH_NAMES = {
    "01": "Январь", "02": "Февраль", "03": "Март", "04": "Апрель",
    "05": "Май", "06": "Июнь", "07": "Июль", "08": "Август",
    "09": "Сентябрь", "10": "Октябрь", "11": "Ноябрь", "12": "Декабрь"
}

def init_db():
    conn = sqlite3.connect('finance.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS finance 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                       uid INTEGER, type TEXT, category TEXT, amount INTEGER, date TEXT)''')
    conn.commit()
    conn.close()

def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False, row_width=2)
    markup.add("💸 Харажат", "💰 Даромад")
    markup.add("📊 Статистика", "📅 Архив")
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    init_db()
    bot.send_message(message.chat.id, "Салом! Мен тайёрман.\n\nПул киритиш учун олдин тугмани танланг.", reply_markup=main_menu())

# --- ТУГМАЛАР УЧУН ЛОГИКА (Фақат шу орқали сақланади) ---
@bot.message_handler(func=lambda m: m.text in ["💸 Харажат", "💰 Даромад"])
def handle_button(message):
    t_type = message.text
    msg = bot.send_message(message.chat.id, f"{t_type} суммасини ёзинг (Масалан: 'Обед 20000' ёки шунчаки '20000'):")
    bot.register_next_step_handler(msg, process_manual_entry, t_type)

def process_manual_entry(message, t_type):
    try:
        text = message.text.strip()
        parts = text.split()
        if text.isdigit():
            category, amount = "Boshqa", int(text)
        elif len(parts) >= 2 and parts[-1].isdigit():
            category, amount = " ".join(parts[:-1]), int(parts[-1])
        else: raise ValueError
        
        save_to_db(message.chat.id, t_type, category, amount)
        bot.send_message(message.chat.id, f"✅ Сақланди!\n{t_type}: {category}\nСумма: {amount:,} сўм", reply_markup=main_menu())
    except:
        bot.send_message(message.chat.id, "❌ Хато! Суммани рақамда ёзинг. Олдин тугмани босинг.", reply_markup=main_menu())

# --- АРХИВ ВА СТАТИСТИКА (Ўзгаришсиз) ---
@bot.message_handler(func=lambda m: m.text == "📅 Архив")
def show_archive(message):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT strftime('%Y-%m', date) FROM finance WHERE uid = ?", (message.chat.id,))
    months = cursor.fetchall()
    conn.close()
    if not months:
        bot.send_message(message.chat.id, "Ҳали базада маълумот йўқ.")
        return
    markup = types.InlineKeyboardMarkup()
    for m in months:
        month_key = m[0]
        year, month_num = month_key.split('-')
        month_name = MONTH_NAMES.get(month_num, month_num)
        markup.add(types.InlineKeyboardButton(text=f"📅 {month_name} {year}", callback_data=f"month_{month_key}"))
    bot.send_message(message.chat.id, "Қайси ой бўйича ҳисобот керак?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('month_'))
def callback_month(call):
    month_key = call.data.split('_')[1]
    year, month_num = month_key.split('-')
    month_name = MONTH_NAMES.get(month_num, month_num)
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute("SELECT type, SUM(amount) FROM finance WHERE uid = ? AND date LIKE ? GROUP BY type", (call.message.chat.id, f"{month_key}%"))
    data = dict(cursor.fetchall())
    conn.close()
    d_sum, x_sum = data.get("💰 Даромад", 0), data.get("💸 Харажат", 0)
    report = f"📊 **{month_name} {year} ҳисоботи:**\n\n💰 Даромад: {d_sum:,} сўм\n💸 Харажат: {x_sum:,} сўм\n⚖️ Соф фойда: {d_sum - x_sum:,} сўм"
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=report, parse_mode="Markdown")

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
    res = "📊 **Умумий ҳисобот:**\n"
    for t_type, cat, amt in rows:
        res += f"\n{'💰' if 'Даромад' in t_type else '💸'} {t_type} ({cat}): {amt:,} сўм"
    d, x = totals.get("💰 Даромад", 0), totals.get("💸 Харажат", 0)
    res += f"\n\n📈 Жами Даромад: {d:,} сўм\n📉 Жами Харажат: {x:,} сўм\n⚖️ Соф фойда: {d - x:,} сўм"
    bot.send_message(message.chat.id, res, parse_mode="Markdown")

# --- ОРТИҚЧА ХАБАРЛАРНИ ЭЪТИБОРСИЗ ҚОЛДИРИШ ---
@bot.message_handler(func=lambda m: True)
def ignore_random_messages(message):
    bot.reply_to(message, "⚠️ Илтимос, олдин тугмалардан бирини танланг (Харажат ёки Даромад).", reply_markup=main_menu())

def save_to_db(uid, t_type, category, amount):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO finance (uid, type, category, amount, date) VALUES (?, ?, ?, ?, ?)",
                   (uid, t_type, category, amount, datetime.now().strftime("%Y-%m-%d")))
    conn.commit()
    conn.close()

@app.route('/')
def home(): return "OK"

if __name__ == "__main__":
    init_db()
    Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))).start()
    while True:
        try: bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e: time.sleep(5)
