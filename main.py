import os, telebot, sqlite3, requests, time, logging
from flask import Flask
from threading import Thread
from telebot import types
from datetime import datetime

# Логларни созлаш (Бот ички ҳолатини кузатиш учун)
logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)
app = Flask('')

# --- 🗄 БАЗА БИЛАН ИШЛАШ ---
def init_db():
    try:
        conn = sqlite3.connect('finance.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS finance 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, type TEXT, category TEXT, amount REAL, currency TEXT, date TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS settings 
            (uid INTEGER PRIMARY KEY, currency TEXT DEFAULT "UZS")''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS debts 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, d_type TEXT, name TEXT, amount REAL, currency TEXT, date TEXT)''')
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Базада хато: {e}")

def get_rates():
    """Валюта курсларини олиш (NBU)"""
    default_rates = {'UZS': 1.0, 'USD': 12850.0, 'RUB': 145.0, 'CNY': 1800.0}
    try:
        res = requests.get("https://nbu.uz/uz/exchange-rates/json/", timeout=5).json()
        for i in res:
            if i['code'] in default_rates: 
                default_rates[i['code']] = float(i['cb_price'])
        return default_rates
    except:
        return default_rates

def get_user_currency(uid):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute("SELECT currency FROM settings WHERE uid = ?", (uid,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else 'UZS'

# --- ⌨️ МЕНЮЛАР ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("💸 Харажат", "💰 Даромад")
    markup.add("📊 Статистика", "📅 Ойлик харажат")
    markup.add("🔍 Кунлик ҳисобот", "🤝 Олди-берди")
    markup.add("💱 Валютани танлаш")
    return markup

def debt_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("➕ Ҳаққим бор", "➖ Қарздорман")
    markup.add("💰 Қарзни қайтариш", "📜 Кимда нима бор?")
    markup.add("⬅️ Ортга")
    return markup

# --- 🚀 АСОСИЙ КОМАНДАЛАР ---
@bot.message_handler(commands=['start'])
def start(message):
    init_db()
    bot.send_message(message.chat.id, "💰 **SmartHisob** тизимига хуш келибсиз!\nПулларингизни тартибга солишни бошланг.", 
                     reply_markup=main_menu(), parse_mode="Markdown")

# --- 🔍 КУНЛИК ҲИСОБОТ (ОЙ ВА КУН) ---
@bot.message_handler(func=lambda m: "Кунлик ҳисобот" in m.text)
def daily_months(message):
    uid = message.chat.id
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT strftime('%Y-%m', date) FROM finance WHERE uid=? ORDER BY date DESC", (uid,))
    months = cursor.fetchall()
    conn.close()
    
    if not months:
        bot.send_message(uid, "📭 Ҳозирча маълумот йўқ.")
        return
    
    markup = types.InlineKeyboardMarkup()
    for m in months:
        markup.add(types.InlineKeyboardButton(f"📅 {m[0]}", callback_data=f"dmon_{m[0]}"))
    bot.send_message(uid, "Қайси ойни кўрмоқчисиз?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('dmon_'))
def daily_days(call):
    month = call.data.split('_')[1]
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT date FROM finance WHERE uid=? AND date LIKE ? ORDER BY date DESC", (call.message.chat.id, f"{month}%"))
    days = cursor.fetchall()
    conn.close()
    
    markup = types.InlineKeyboardMarkup()
    for d in days:
        day_val = d[0].split('-')[-1]
        markup.add(types.InlineKeyboardButton(f"📆 {day_val}-кун", callback_data=f"dday_{d[0]}"))
    bot.edit_message_text(f"📅 {month} ойидаги кунни танланг:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('dday_'))
def daily_final(call):
    date_str = call.data.split('_')[1]
    uid = call.message.chat.id
    u_cur = get_user_currency(uid)
    rates = get_rates()
    u_rate = rates.get(u_cur, 1.0)
    
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute("SELECT type, category, amount, currency FROM finance WHERE uid=? AND date=?", (uid, date_str))
    items = cursor.fetchall()
    conn.close()
    
    res = f"📆 **{date_str} бўйича батафсил:**\n"
    t_in, t_out = 0, 0
    for t_type, cat, amt, c_cur in items:
        uzs_val = amt * rates.get(c_cur, 1.0)
        if t_type == "💰 Даромад": t_in += uzs_val
        else: t_out += uzs_val
        res += f"\n{'🔹' if t_type == '💸 Харажат' else '🔸'} {cat}: {amt:,.0f} {c_cur}"
    
    res += f"\n\n💰 Кирим: {t_in/u_rate:,.2f} {u_cur}\n💸 Чиқим: {t_out/u_rate:,.2f} {u_cur}\n⚖️ Қолдиқ: {(t_in-t_out)/u_rate:,.2f} {u_cur}"
    bot.send_message(uid, res, parse_mode="Markdown")

# --- 🤝 ОЛДИ-БЕРДИ ТИЗИМИ (FULL) ---
@bot.message_handler(func=lambda m: "Олди-берди" in m.text)
def debt_section(message):
    bot.send_message(message.chat.id, "🤝 **Олди-берди бўлими**\nҚарзларни шу ерда бошқаринг:", reply_markup=debt_menu(), parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text in ["➕ Ҳаққим бор", "➖ Қарздорман"])
def debt_add(message):
    d_type = message.text
    msg = bot.send_message(message.chat.id, f"👤 {d_type}\nИсм ва суммани ёзинг (Мас: Али 100):")
    bot.register_next_step_handler(msg, debt_save, d_type)

def debt_save(message, d_type):
    try:
        parts = message.text.split()
        amt = float(parts[-1])
        name = " ".join(parts[:-1])
        markup = types.InlineKeyboardMarkup()
        for c in ["UZS", "USD", "RUB", "CNY"]:
            markup.add(types.InlineKeyboardButton(c, callback_data=f"ds_{d_type}_{amt}_{name}_{c}"))
        bot.send_message(message.chat.id, "Валютани танланг:", reply_markup=markup)
    except:
        bot.send_message(message.chat.id, "❌ Хато! 'Исм Сумма' кўринишида ёзинг.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('ds_'))
def debt_finalize(call):
    _, d_type, amt, name, cur = call.data.split('_')
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO debts (uid, d_type, name, amount, currency, date) VALUES (?,?,?,?,?,?)",
                   (call.message.chat.id, d_type, name, float(amt), cur, datetime.now().strftime("%Y-%m-%d")))
    conn.commit()
    conn.close()
    bot.edit_message_text(f"✅ Сақланди: {name} {amt} {cur}", call.message.chat.id, call.message.message_id)

@bot.message_handler(func=lambda m: m.text == "📜 Кимда нима бор?")
def debt_list(message):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute("SELECT d_type, name, amount, currency FROM debts WHERE uid=?", (message.chat.id,))
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        bot.send_message(message.chat.id, "📭 Рўйхат бўш.")
        return
    res = "📜 **Қарздорлар рўйхати:**\n"
    for t, n, a, c in rows:
        icon = "🟢" if "Ҳаққим" in t else "🔴"
        res += f"\n{icon} {n}: {a:,.2f} {c}"
    bot.send_message(message.chat.id, res, parse_mode="Markdown")

# --- 🛠 БОТНИ УЙҒОҚ САҚЛАШ ---
@app.route('/')
def home(): return "Бот тирик!"

def run_flask():
    app.run(host='0.0.0.0', port=10000)

if __name__ == "__main__":
    init_db()
    Thread(target=run_flask).start()
    
    # Ботни тўхтовсиз ишлатиш (Render учун)
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=40)
        except Exception as e:
            logging.error(f"Polling хатоси: {e}")
            time.sleep(10)
