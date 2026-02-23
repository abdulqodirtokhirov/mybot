import os, telebot, sqlite3, requests, time
from flask import Flask
from threading import Thread
from telebot import types
from datetime import datetime

# Бот Тoken ва Flask созламалари
TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)
app = Flask('')

# --- 1. МАЪЛУМОТЛАР БАЗАСИНИ СОЗЛАШ ---
def init_db():
    conn = sqlite3.connect('finance.db', check_same_thread=False)
    cursor = conn.cursor()
    # Молиявий амалиётлар жадвали
    cursor.execute('''CREATE TABLE IF NOT EXISTS finance 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, type TEXT, 
         category TEXT, amount REAL, currency TEXT, date TEXT)''')
    # Қарзлар жадвали
    cursor.execute('''CREATE TABLE IF NOT EXISTS debts 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, d_type TEXT, 
         name TEXT, amount REAL, currency TEXT, status TEXT)''')
    conn.commit(); conn.close()

# --- 2. МАРКАЗИЙ БАНК КУРСЛАРИНИ ОЛИШ ---
def get_rates():
    rates = {'UZS': 1.0, 'USD': 12850.0, 'RUB': 145.0, 'CNY': 1800.0, 'EUR': 13800.0}
    try:
        res = requests.get("https://nbu.uz/uz/exchange-rates/json/", timeout=5).json()
        for i in res:
            if i['code'] in rates: rates[i['code']] = float(i['cb_price'])
    except: pass
    return rates

# --- 3. 1-9 РАҚАМЛИ КЛАВИАТУРА (СИЗ АЙТГАНДЕК) ---
def num_pad(action, info, val=""):
    markup = types.InlineKeyboardMarkup(row_width=3)
    btns = [types.InlineKeyboardButton(str(i), callback_data=f"n_{action}_{info}_{val}{i}") for i in range(1, 10)]
    markup.add(*btns)
    markup.add(types.InlineKeyboardButton("0", callback_data=f"n_{action}_{info}_{val}0"),
               types.InlineKeyboardButton("⬅️", callback_data=f"n_{action}_{info}_{val[:-1]}"),
               types.InlineKeyboardButton("🗑", callback_data=f"n_{action}_{info}_"))
    markup.add(types.InlineKeyboardButton(f"✅ Тасдиқлаш: {val}", callback_data=f"d_{action}_{info}_{val}"))
    return markup

# --- 4. АСОСИЙ МЕНЮ (10 ТА ТУГМА ТАРТИБИ) ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.row("💸 Харажат") # 1
    markup.row("💰 Даромад") # 2
    markup.add("📊 Статистика", "📅 Ойлик харажат") # 3 ва 4
    markup.row("🔍 Кунлик ҳисобот") # 5
    markup.row("🤝 Олди-берди") # 6
    markup.row("🏠 Коммунал") # 7
    markup.row("📊 Коммунал Ҳисобот") # 8
    markup.row("⚙️ Валюта танлаш") # 9
    markup.row("📈 Жонли Валюта ва Конвертер") # 10
    return markup

# Глобал ўзгарувчи (Валюта кўриниши учун)
user_currency = {}

@bot.message_handler(commands=['start'])
def start(message):
    init_db()
    user_currency[message.chat.id] = "UZS"
    bot.send_message(message.chat.id, "💰 SmartHisob PRO: Хуш келибсиз!", reply_markup=main_menu())

# --- 5. ХАРАЖАТ, ДАРОМАД ВА КОММУНАЛ КИРИТИШ ---
@bot.message_handler(func=lambda m: m.text in ["💸 Харажат", "💰 Даромад", "🏠 Коммунал"])
def handle_entries(message):
    act = message.text
    msg = bot.send_message(message.chat.id, f"{act}: Категория ёзинг (масалан: 🍎 Овқат):")
    bot.register_next_step_handler(msg, lambda m: bot.send_message(m.chat.id, f"💰 {m.text} суммаси:", reply_markup=num_pad(act, m.text)))

# --- 6. 🤝 ОЛДИ-БЕРДИ ИЧКИ МЕНЮСИ ---
@bot.message_handler(func=lambda m: m.text == "🤝 Олди-берди")
def debts_menu(message):
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("➕ Ҳаққим бор", callback_data="db_plus"),
          types.InlineKeyboardButton("➖ Қарздорман", callback_data="db_minus"),
          types.InlineKeyboardButton("💰 Қайтариш", callback_data="db_pay"),
          types.InlineKeyboardButton("📜 Кимда нима бор?", callback_data="db_list"))
    bot.send_message(message.chat.id, "🤝 Олди-берди бўлими:", reply_markup=m)

# --- 7. 📊 СТАТИСТИКА ВА АРХИВЛАР (9-ТУГМАГА БОҒЛИҚ) ---
@bot.message_handler(func=lambda m: m.text in ["📊 Статистика", "📅 Ойлик харажат", "🔍 Кунлик ҳисобот", "📊 Коммунал Ҳисобот"])
def handle_reports(message):
    conn = sqlite3.connect('finance.db'); cursor = conn.cursor()
    v_cur = user_currency.get(message.chat.id, "UZS")
    r = get_rates()

    if message.text == "📊 Статистика":
        cursor.execute("SELECT type, amount, currency FROM finance WHERE uid=?", (message.chat.id,))
        data = cursor.fetchall(); conn.close()
        total = 0
        for t, a, c in data:
            val = (a * r.get(c, 1)) / r.get(v_cur, 1)
            total += val if "Даромад" in t else -val
        bot.send_message(message.chat.id, f"⚖️ Умумий қолдиқ: {total:,.2f} {v_cur}")

    elif message.text == "📅 Ойлик харажат":
        cursor.execute("SELECT DISTINCT strftime('%Y-%m', date) FROM finance WHERE uid=? ORDER BY date DESC", (message.chat.id,))
        months = cursor.fetchall(); conn.close()
        m = types.InlineKeyboardMarkup()
        for mon in months: m.add(types.InlineKeyboardButton(f"📅 {mon[0]}", callback_data=f"amonth_{mon[0]}"))
        bot.send_message(message.chat.id, "Ойни танланг (умумий ҳисобот учун):", reply_markup=m)

    elif message.text == "🔍 Кунлик ҳисобот" or message.text == "📊 Коммунал Ҳисобот":
        cursor.execute("SELECT DISTINCT strftime('%Y-%m', date) FROM finance WHERE uid=? ORDER BY date DESC", (message.chat.id,))
        months = cursor.fetchall(); conn.close()
        m = types.InlineKeyboardMarkup()
        prefix = "daymonth" if "Кунлик" in message.text else "commmonth"
        for mon in months: m.add(types.InlineKeyboardButton(f"📅 {mon[0]}", callback_data=f"{prefix}_{mon[0]}"))
        bot.send_message(message.chat.id, "Ҳисобот учун ойни танланг:", reply_markup=m)

# --- 8. ⚙️ ВАЛЮТА ТАНЛАШ (9-ТУГМА) ---
@bot.message_handler(func=lambda m: m.text == "⚙️ Валюта танлаш")
def change_vcur(message):
    m = types.InlineKeyboardMarkup()
    for c in ["UZS", "USD", "RUB", "CNY"]: m.add(types.InlineKeyboardButton(c, callback_data=f"setvcur_{c}"))
    bot.send_message(message.chat.id, "Ҳисоботлар қайси валютада кўрсатилсин?", reply_markup=m)

# --- 9. 📈 ЖОНЛИ ВАЛЮТА ВА КОНВЕРТЕР (10-ТУГМА) ---
@bot.message_handler(func=lambda m: m.text == "📈 Жонли Валюта ва Конвертер")
def live_rates(message):
    r = get_rates()
    text = f"🏦 МБ Курслари:\n🇺🇿 1 USD = {r['USD']} UZS\n🇷🇺 1 RUB = {r['RUB']} UZS\n\nҲисоблаш учун валютани танланг:"
    m = types.InlineKeyboardMarkup(row_width=2)
    for c in ["USD", "RUB", "CNY", "EUR"]: m.add(types.InlineKeyboardButton(f"🔄 {c}", callback_data=f"calc_{c}"))
    m.add(types.InlineKeyboardButton("⬅️ Ортга", callback_data="back_main"))
    bot.send_message(message.chat.id, text, reply_markup=m)

# --- 10. CALLBACKS (ҲАММА ИЧКИ ТУГМАЛАРНИ БОШҚАРИШ) ---
@bot.callback_query_handler(func=lambda call: True)
def global_callback(call):
    d = call.data.split('_')
    r = get_rates()

    if d[0] == 'n': # Рақамларни териш
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=num_pad(d[1], d[2], d[3]))
    
    elif d[0] == 'd': # Тасдиқлаш ва Валюта танлаш
        m = types.InlineKeyboardMarkup()
        for c in ["UZS", "USD", "RUB", "CNY"]: m.add(types.InlineKeyboardButton(c, callback_data=f"save_{d[1]}_{d[2]}_{d[3]}_{c}"))
        bot.send_message(call.message.chat.id, f"💰 Сумма: {d[3]}. Валюта:", reply_markup=m)

    elif d[0] == 'save': # Базага сақлаш
        conn = sqlite3.connect('finance.db'); cursor = conn.cursor()
        cursor.execute("INSERT INTO finance (uid, type, category, amount, currency, date) VALUES (?,?,?,?,?,?)",
                       (call.message.chat.id, d[1], d[2], float(d[3]), d[4], datetime.now().strftime("%Y-%m-%d")))
        conn.commit(); conn.close()
        bot.edit_message_text(f"✅ Сақланди: {d[1]} | {d[2]} | {d[3]} {d[4]}", call.message.chat.id, call.message.message_id)

    elif d[0] == 'setvcur': # 9-тугма: Валютани ўзгартириш
        user_currency[call.message.chat.id] = d[1]
        bot.edit_message_text(f"⚙️ Энди ҳамма ҳисоботлар {d[1]}да кўрсатилади.", call.message.chat.id, call.message.message_id)

    elif d[0] == 'calc': # Конвертер суммасини сўраш
        bot.send_message(call.message.chat.id, f"{d[1]} суммасини киритинг:", reply_markup=num_pad("convert", d[1]))

    elif d[1] == 'convert' and d[0] == 'd': # Конвертер ҳисоблаш
        res = float(d[3]) * r.get(d[2], 1)
        bot.send_message(call.message.chat.id, f"🔄 {d[3]} {d[2]} = {res:,.0f} UZS")

    elif d[0] == 'back' and d[1] == 'main': # Ортга тугмаси
        bot.send_message(call.message.chat.id, "Асосий меню:", reply_markup=main_menu())

# --- KEEP ALIVE ---
@app.route('/')
def h(): return "OK"
def run_app(): app.run(host='0.0.0.0', port=10000)

if __name__ == "__main__":
    init_db()
    Thread(target=run_app).start()
    bot.polling(none_stop=True)
