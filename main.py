import os, telebot, sqlite3, requests, time
from flask import Flask
from threading import Thread
from telebot import types
from datetime import datetime

# Бот Токени
TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)
app = Flask('')

# Маълумотлар базасини созлаш
def init_db():
    conn = sqlite3.connect('finance.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS finance 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, type TEXT, 
                       category TEXT, amount REAL, date TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings 
                      (uid INTEGER PRIMARY KEY, currency TEXT DEFAULT 'UZS', remind_time TEXT DEFAULT 'OFF')''')
    conn.commit()
    conn.close()

# Валюта курсларини олиш (НБУ)
def get_rates():
    try:
        res = requests.get("https://nbu.uz/uz/exchange-rates/json/").json()
        rates = {'UZS': 1.0, 'USD': 12600.0, 'RUB': 140.0}
        for i in res:
            if i['code'] == 'USD': rates['USD'] = float(i['cb_price'])
            if i['code'] == 'RUB': rates['RUB'] = float(i['cb_price'])
        return rates
    except:
        return {'UZS': 1.0, 'USD': 12600.0, 'RUB': 140.0}

def get_user_settings(uid):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute("SELECT currency, remind_time FROM settings WHERE uid = ?", (uid,))
    res = cursor.fetchone()
    conn.close()
    return res if res else ('UZS', 'OFF')

# Асосий меню
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("💸 Харажат"), types.KeyboardButton("💰 Даромад"))
    markup.add(types.KeyboardButton("📊 Статистика"), types.KeyboardButton("🔍 Кунлик ҳисобот"))
    markup.add(types.KeyboardButton("💱 Валютани танлаш"), types.KeyboardButton("📅 Ойлик харажатлар (Архив)"))
    markup.add(types.KeyboardButton("🔔 Эслатма созламаси"))
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    init_db()
    bot.send_message(message.chat.id, "Ассалому алайкум! Молиявий бошқарув тизимига хуш келибсиз. Илтимос, бўлимни танланг:", reply_markup=main_menu())

# --- КИРИТИШ ТИЗИМИ ---
@bot.message_handler(func=lambda m: m.text in ["💸 Харажат", "💰 Даромад"])
def handle_entry(message):
    t_type = message.text
    msg = bot.send_message(message.chat.id, f"{t_type} миқдорини киритинг.\n(Масалан: 'Овқат 50000' ёки шунчаки '50000'):")
    bot.register_next_step_handler(msg, ask_currency_confirm, t_type)

def ask_currency_confirm(message, t_type):
    try:
        text = message.text.strip()
        parts = text.split()
        
        # Агар фақат сон бўлса ёки категория + сон бўлса
        if text.replace('.','',1).isdigit():
            category, amount = "Бошқа", float(text)
        else:
            category, amount = " ".join(parts[:-1]), float(parts[-1])
        
        cur_code, _ = get_user_settings(message.chat.id)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(f"✅ {cur_code}", callback_data=f"save_{t_type}_{amount}_{category}_{cur_code}"),
                   types.InlineKeyboardButton("🇺🇿 UZS", callback_data=f"save_{t_type}_{amount}_{category}_UZS"))
        
        bot.send_message(message.chat.id, f"Маблағни қайси валютада сақлаймиз?", reply_markup=markup)
    except:
        bot.send_message(message.chat.id, "❌ Хато! Илтимос, миқдорни рақамда киритинг (Намуна: Овқат 50000).")

@bot.callback_query_handler(func=lambda call: call.data.startswith('save_'))
def finalize_save(call):
    _, t_type, amt, cat, cur = call.data.split('_')
    rates = get_rates()
    # Базага доим UZS қийматида сақлаймиз (курсга қараб)
    uzs_val = float(amt) * rates.get(cur, 1.0) if cur != 'UZS' else float(amt)
    
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO finance (uid, type, category, amount, date) VALUES (?, ?, ?, ?, ?)",
                   (call.message.chat.id, t_type, cat, uzs_val, datetime.now().strftime("%Y-%m-%d")))
    conn.commit()
    conn.close()
    
    bot.edit_message_text(f"✅ Сақланди!\n{t_type}: {amt} {cur}\nКатегория: {cat}", call.message.chat.id, call.message.message_id)

# --- ВАЛЮТАНИ СОЗЛАШ ---
@bot.message_handler(func=lambda m: m.text == "💱 Валютани танлаш")
def change_currency(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🇺🇿 UZS", callback_data="setcur_UZS"),
               types.InlineKeyboardButton("🇺🇸 USD", callback_data="setcur_USD"),
               types.InlineKeyboardButton("🇷🇺 RUB", callback_data="setcur_RUB"))
    bot.send_message(message.chat.id, "Кўрсатиладиган асосий валютани танланг:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('setcur_'))
def set_currency(call):
    cur = call.data.split('_')[1]
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (uid, currency, remind_time) VALUES (?, ?, (SELECT remind_time FROM settings WHERE uid = ?))", (call.message.chat.id, cur, call.message.chat.id))
    conn.commit()
    conn.close()
    bot.edit_message_text(f"✅ Асосий валюта: {cur}. Барча ҳисоблар шу валютада кўрсатилади.", call.message.chat.id, call.message.message_id)

# --- СТАТИСТИКА ---
@bot.message_handler(func=lambda m: m.text == "📊 Статистика")
def show_stats(message):
    uid = message.chat.id
    cur, _ = get_user_settings(uid)
    rate = get_rates().get(cur, 1.0)
    
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    this_m = datetime.now().strftime("%Y-%m")
    
    cursor.execute("SELECT category, SUM(amount) FROM finance WHERE uid=? AND type='💸 Харажат' AND date LIKE ? GROUP BY category", (uid, f"{this_m}%"))
    rows = cursor.fetchall()
    
    cursor.execute("SELECT type, SUM(amount) FROM finance WHERE uid=? GROUP BY type", (uid,))
    totals = dict(cursor.fetchall())
    conn.close()
    
    res = f"📊 **Жорий ой статистикаси ({cur}):**\n"
    x_month = sum(r[1] for r in rows)
    
    for cat, amt in rows:
        p = (amt/x_month*100) if x_month > 0 else 0
        res += f"\n🔸 {cat}: {amt/rate:,.2f} ({p:.1f}%)"
    
    d_total = totals.get("💰 Даромад", 0)
    x_total = totals.get("💸 Харажат", 0)
    
    res += f"\n\n🌍 **Умумий итог:**\n💰 Даромад: {d_total/rate:,.2f}\n💸 Харажат: {x_total/rate:,.2f}\n⚖️ Қолдиқ: {(d_total-x_total)/rate:,.2f}"
    bot.send_message(uid, res, parse_mode="Markdown")

# --- КУНЛИК ҲИСОБОТ ---
@bot.message_handler(func=lambda m: m.text == "🔍 Кунлик ҳисобот")
def daily_rep(message):
    msg = bot.send_message(message.chat.id, "Қайси кунни кўрмоқчисиз? (Намуна: 21):")
    bot.register_next_step_handler(msg, process_daily)

def process_daily(message):
    day = message.text.strip().zfill(2)
    date_str = datetime.now().strftime("%Y-%m-") + day
    uid = message.chat.id
    cur, _ = get_user_settings(uid)
    rate = get_rates().get(cur, 1.0)
    
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute("SELECT type, SUM(amount) FROM finance WHERE uid=? AND date=? GROUP BY type", (uid, date_str))
    data = dict(cursor.fetchall())
    conn.close()
    
    d, x = data.get("💰 Даромад", 0), data.get("💸 Харажат", 0)
    bot.send_message(uid, f"📅 **{date_str} ҳисоботи ({cur}):**\n\n💰 Кирим: {d/rate:,.2f}\n💸 Чиқим: {x/rate:,.2f}\n⚖️ Фойда: {(d-x)/rate:,.2f}", parse_mode="Markdown")

# --- ЭСЛАТМА ---
@bot.message_handler(func=lambda m: m.text == "🔔 Эслатма созламаси")
def remind_menu(message):
    _, state = get_user_settings(message.chat.id)
    markup = types.InlineKeyboardMarkup()
    if state == 'OFF':
        markup.add(types.InlineKeyboardButton("🔔 Ёқиш", callback_data="rem_on"))
    else:
        markup.add(types.InlineKeyboardButton("🔕 Ўчириш", callback_data="rem_off"),
                   types.InlineKeyboardButton("🕒 Вақтни ўзгартириш", callback_data="rem_on"))
    bot.send_message(message.chat.id, f"Эслатма ҳолати: {state}.\nСозлашни хоҳлайсизми?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "rem_on")
def rem_on(call):
    msg = bot.send_message(call.message.chat.id, "Эслатма вақтини киритинг (Намуна: 21:00):")
    bot.register_next_step_handler(msg, save_rem_time)

@bot.callback_query_handler(func=lambda call: call.data == "rem_off")
def rem_off(call):
    update_rem_settings(call.message.chat.id, 'OFF')
    bot.edit_message_text("🔕 Эслатма ўчирилди.", call.message.chat.id, call.message.message_id)

def save_rem_time(message):
    t = message.text.strip()
    update_rem_settings(message.chat.id, t)
    bot.send_message(message.chat.id, f"✅ Эслатма ҳар куни соат {t} га созланди.")

def update_rem_settings(uid, val):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (uid, currency, remind_time) VALUES (?, (SELECT currency FROM settings WHERE uid=?), ?)", (uid, uid, val))
    conn.commit()
    conn.close()

# --- АРХИВ ВА БОШҚАЛАР ---
@bot.message_handler(func=lambda m: m.text == "📅 Ойлик харажатлар (Архив)")
def show_archive(message):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT strftime('%Y-%m', date) FROM finance WHERE uid = ?", (message.chat.id,))
    months = cursor.fetchall()
    conn.close()
    if not months:
        bot.send_message(message.chat.id, "Архивда маълумот йўқ.")
        return
    markup = types.InlineKeyboardMarkup()
    for m in months:
        markup.add(types.InlineKeyboardButton(f"📅 {m[0]}", callback_data=f"arch_{m[0]}"))
    bot.send_message(message.chat.id, "Кўрмоқчи бўлган ойни танланг:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('arch_'))
def arch_callback(call):
    m_key = call.data.split('_')[1]
    uid = call.message.chat.id
    cur, _ = get_user_settings(uid)
    rate = get_rates().get(cur, 1.0)
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute("SELECT type, SUM(amount) FROM finance WHERE uid=? AND date LIKE ? GROUP BY type", (uid, f"{m_key}%"))
    data = dict(cursor.fetchall())
    conn.close()
    d, x = data.get("💰 Даромад", 0), data.get("💸 Харажат", 0)
    bot.send_message(uid, f"📅 **{m_key} якуни ({cur}):**\n\nКирим: {d/rate:,.2f}\nЧиқим: {x/rate:,.2f}\nҚолдиқ: {(d-x)/rate:,.2f}")

@bot.message_handler(func=lambda m: True)
def auto_reply(message):
    bot.reply_to(message, "⚠️ Илтимос, аввал пастдаги тугмалардан бирини танланг.", reply_markup=main_menu())

# Эслатма юбориш функцияси
def send_reminders():
    while True:
        now = datetime.now().strftime("%H:%M")
        conn = sqlite3.connect('finance.db')
        cursor = conn.cursor()
        cursor.execute("SELECT uid FROM settings WHERE remind_time = ?", (now,))
        for u in cursor.fetchall():
            try: bot.send_message(u[0], "🔔 Салом! Бугунги кирим ва чиқимларни ёзиш ёддан чиқмадими?")
            except: pass
        conn.close()
        time.sleep(60)

# Flask (Ухлаб қолмаслик учун)
@app.route('/')
def home(): return "Бот фаол!"

if __name__ == "__main__":
    init_db()
    Thread(target=send_reminders).start()
    Thread(target=lambda: app.run(host='0.0.0.0', port=10000)).start()
    bot.polling(none_stop=True)
