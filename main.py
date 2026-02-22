import os, telebot, sqlite3, requests, time
from flask import Flask
from threading import Thread
from telebot import types
from datetime import datetime

TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)
app = Flask('')

def init_db():
    conn = sqlite3.connect('finance.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS finance (id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, type TEXT, category TEXT, amount REAL, currency TEXT, date TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS settings (uid INTEGER PRIMARY KEY, currency TEXT DEFAULT "UZS")')
    cursor.execute('CREATE TABLE IF NOT EXISTS debts (id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, d_type TEXT, name TEXT, amount REAL, currency TEXT, date TEXT)')
    conn.commit()
    conn.close()

def get_rates():
    rates = {'UZS': 1.0, 'USD': 12850.0, 'RUB': 145.0, 'CNY': 1800.0}
    try:
        res = requests.get("https://nbu.uz/uz/exchange-rates/json/", timeout=5).json()
        for i in res:
            if i['code'] in rates: rates[i['code']] = float(i['cb_price'])
    except: pass
    return rates

def get_user_currency(uid):
    conn = sqlite3.connect('finance.db'); cursor = conn.cursor()
    cursor.execute("SELECT currency FROM settings WHERE uid = ?", (uid,))
    res = cursor.fetchone(); conn.close()
    return res[0] if res else 'UZS'

# --- МЕНЮЛАР ---
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

@bot.message_handler(commands=['start'])
def start(message):
    init_db()
    bot.send_message(message.chat.id, "💰 SmartHisob тизими фаол!", reply_markup=main_menu())

# --- 🤝 ОЛДИ-БЕРДИ БЎЛИМИ ---
@bot.message_handler(func=lambda m: "Олди-берди" in m.text)
def debt_home(message):
    bot.send_message(message.chat.id, "🤝 Қарзлар менюси:", reply_markup=debt_menu())

@bot.message_handler(func=lambda m: m.text in ["➕ Ҳаққим бор", "➖ Қарздорман"])
def add_debt_init(message):
    d_type = message.text
    msg = bot.send_message(message.chat.id, f"{d_type}. Исм ва суммани ёзинг (Мас: Али 100):")
    bot.register_next_step_handler(msg, save_debt_step1, d_type)

def save_debt_step1(message, d_type):
    try:
        parts = message.text.split()
        amt = float(parts[-1]); name = " ".join(parts[:-1])
        markup = types.InlineKeyboardMarkup()
        for c in ["UZS", "USD", "RUB", "CNY"]:
            markup.add(types.InlineKeyboardButton(c, callback_data=f"dsave_{d_type}_{amt}_{name}_{c}"))
        bot.send_message(message.chat.id, "Валютани танланг:", reply_markup=markup)
    except:
        bot.send_message(message.chat.id, "❌ Хато! 'Исм Сумма' кўринишида ёзинг.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('dsave_'))
def save_debt_final(call):
    _, d_type, amt, name, cur = call.data.split('_')
    conn = sqlite3.connect('finance.db'); cursor = conn.cursor()
    cursor.execute("INSERT INTO debts (uid, d_type, name, amount, currency, date) VALUES (?,?,?,?,?,?)",
                   (call.message.chat.id, d_type, name, float(amt), cur, datetime.now().strftime("%Y-%m-%d")))
    conn.commit(); conn.close()
    bot.edit_message_text(f"✅ Сақланди: {name} {amt} {cur}", call.message.chat.id, call.message.message_id)

@bot.message_handler(func=lambda m: m.text == "📜 Кимда нима бор?")
def show_debts(message):
    conn = sqlite3.connect('finance.db'); cursor = conn.cursor()
    cursor.execute("SELECT d_type, name, amount, currency FROM debts WHERE uid=?", (message.chat.id,))
    rows = cursor.fetchall(); conn.close()
    if not rows:
        bot.send_message(message.chat.id, "📭 Рўйхат бўш. Ҳаммаси тоза! ✨")
        return
    res = "📜 **Қарзлар рўйхати:**\n"
    for t, n, a, c in rows:
        icon = "🟢" if "Ҳаққим" in t else "🔴"
        res += f"\n{icon} {n}: {a:,.2f} {c}"
    bot.send_message(message.chat.id, res, parse_mode="Markdown")

# --- 💰 ҚАРЗНИ ҚАЙТАРИШ (ТУЗАЛГАН ҚИСМИ) ---
@bot.message_handler(func=lambda m: m.text == "💰 Қарзни қайтариш")
def repay_list(message):
    conn = sqlite3.connect('finance.db'); cursor = conn.cursor()
    cursor.execute("SELECT id, name, amount, currency FROM debts WHERE uid=?", (message.chat.id,))
    rows = cursor.fetchall(); conn.close()
    if not rows:
        bot.send_message(message.chat.id, "📭 Қарздорлар йўқ.")
        return
    markup = types.InlineKeyboardMarkup()
    for d_id, name, amt, cur in rows:
        markup.add(types.InlineKeyboardButton(f"{name} ({amt} {cur})", callback_data=f"prepay_{d_id}"))
    bot.send_message(message.chat.id, "Ким қарзини қайтарди?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('prepay_'))
def repay_amt_input(call):
    d_id = call.data.split('_')[1]
    msg = bot.send_message(call.message.chat.id, "Қайтарилган суммани ёзинг:")
    bot.register_next_step_handler(msg, repay_final, d_id)

def repay_final(message, d_id):
    try:
        pay_amt = float(message.text)
        conn = sqlite3.connect('finance.db'); cursor = conn.cursor()
        cursor.execute("SELECT name, amount, currency FROM debts WHERE id=?", (d_id,))
        row = cursor.fetchone()
        if row:
            new_amt = row[1] - pay_amt
            if new_amt > 0.1:
                cursor.execute("UPDATE debts SET amount=? WHERE id=?", (new_amt, d_id))
                bot.send_message(message.chat.id, f"✅ {row[0]}дан {pay_amt} {row[2]} қабул қилинди. Қолдиқ: {new_amt:,.2f}")
            else:
                cursor.execute("DELETE FROM debts WHERE id=?", (d_id,))
                bot.send_message(message.chat.id, f"✅ {row[0]} билан ҳисоб тўлиқ ёпилди! 🎉")
            conn.commit()
        conn.close()
    except: bot.send_message(message.chat.id, "❌ Хато! Фақат сон ёзинг.")

@bot.message_handler(func=lambda m: "Ортга" in m.text)
def back_main(message):
    bot.send_message(message.chat.id, "Асосий меню:", reply_markup=main_menu())

# --- (ҚОЛГАН ФУНКЦИЯЛАР: ХАРАЖАТ, СТАТИСТИКА, КУНЛИК...) ---
# [Бу ерда олдинги коддаги харажат ва кунлик ҳисобот функциялари жойлашади]

@app.route('/')
def home(): return "Active"
def run_f(): app.run(host='0.0.0.0', port=10000)

if __name__ == "__main__":
    init_db()
    Thread(target=run_f).start()
    while True:
        try: bot.polling(none_stop=True, interval=0, timeout=20)
        except: time.sleep(5)
