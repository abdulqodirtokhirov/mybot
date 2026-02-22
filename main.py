import os, telebot, sqlite3, requests, time, logging
from flask import Flask
from threading import Thread
from telebot import types
from datetime import datetime

# Назорат учун логлар
logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)
app = Flask('')

# --- 🗄 БАЗА ---
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

@bot.message_handler(commands=['start'])
def start(message):
    init_db()
    bot.send_message(message.chat.id, "💰 **SmartHisob** тизими фаол!", reply_markup=main_menu(), parse_mode="Markdown")

# --- 💸 КИРИМ / ЧИҚИМ ---
@bot.message_handler(func=lambda m: m.text in ["💸 Харажат", "💰 Даромад"])
def money_in(message):
    t_type = message.text
    msg = bot.send_message(message.chat.id, f"{t_type}ни киритинг (Мас: Обед 20000 ёки 20000):")
    bot.register_next_step_handler(msg, money_save, t_type)

def money_save(message, t_type):
    try:
        parts = message.text.split()
        amt = float(parts[-1]); cat = " ".join(parts[:-1]) if len(parts) > 1 else "Бошқа"
        markup = types.InlineKeyboardMarkup()
        for c in ["UZS", "USD", "RUB", "CNY"]:
            markup.add(types.InlineKeyboardButton(c, callback_data=f"msv_{t_type}_{amt}_{cat}_{c}"))
        bot.send_message(message.chat.id, "Валютани танланг:", reply_markup=markup)
    except: bot.send_message(message.chat.id, "❌ Хато! Суммани тўғри ёзинг.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('msv_'))
def m_final(call):
    _, t_t, amt, cat, cur = call.data.split('_')
    conn = sqlite3.connect('finance.db'); cursor = conn.cursor()
    cursor.execute("INSERT INTO finance (uid, type, category, amount, currency, date) VALUES (?,?,?,?,?,?)",
                   (call.message.chat.id, t_t, cat, float(amt), cur, datetime.now().strftime("%Y-%m-%d")))
    conn.commit(); conn.close()
    bot.edit_message_text(f"✅ Сақланди: {cat} {amt} {cur}", call.message.chat.id, call.message.message_id)

# --- 📊 ОЙЛИК СТАТИСТИКА (100% ИШЧИ) ---
@bot.message_handler(func=lambda m: m.text == "📅 Ойлик харажат")
def monthly_archive(message):
    conn = sqlite3.connect('finance.db'); cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT strftime('%Y-%m', date) FROM finance WHERE uid=? ORDER BY date DESC", (message.chat.id,))
    months = cursor.fetchall(); conn.close()
    if not months: bot.send_message(message.chat.id, "📭 Маълумот йўқ."); return
    markup = types.InlineKeyboardMarkup()
    for m in months: markup.add(types.InlineKeyboardButton(f"📊 {m[0]}", callback_data=f"mstat_{m[0]}"))
    bot.send_message(message.chat.id, "Қайси ой статистикасини кўрмоқчисиз?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('mstat_'))
def monthly_stat_final(call):
    month = call.data.split('_')[1]
    u_cur = get_user_currency(call.message.chat.id); rates = get_rates(); u_rate = rates.get(u_cur, 1.0)
    conn = sqlite3.connect('finance.db'); cursor = conn.cursor()
    cursor.execute("SELECT type, category, amount, currency FROM finance WHERE uid=? AND date LIKE ?", (call.message.chat.id, f"{month}%"))
    items = cursor.fetchall(); conn.close()
    stats = {}; t_in, t_out = 0, 0
    for t_t, cat, amt, c_cur in items:
        uzs = amt * rates.get(c_cur, 1.0)
        if "Даромад" in t_t: t_in += uzs
        else:
            t_out += uzs
            stats[cat] = stats.get(cat, 0) + uzs
    res = f"📊 **{month} ойи ҳисоботи ({u_cur}):**\n"
    for c, v in stats.items():
        p = (v / t_out * 100) if t_out > 0 else 0
        res += f"\n🔸 {c}: {v/u_rate:,.0f} ({p:.1f}%)"
    res += f"\n\n💰 Кирим: {t_in/u_rate:,.0f}\n💸 Чиқим: {t_out/u_rate:,.0f}\n⚖️ Қолдиқ: {(t_in-t_out)/u_rate:,.0f}"
    bot.send_message(call.message.chat.id, res, parse_mode="Markdown")

# --- 🔍 КУНЛИК ҲИСОБОТ ---
@bot.message_handler(func=lambda m: "Кунлик ҳисобот" in m.text)
def daily_months(message):
    conn = sqlite3.connect('finance.db'); cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT strftime('%Y-%m', date) FROM finance WHERE uid=? ORDER BY date DESC", (message.chat.id,))
    months = cursor.fetchall(); conn.close()
    if not months: bot.send_message(message.chat.id, "📭 Маълумот йўқ."); return
    markup = types.InlineKeyboardMarkup()
    for m in months: markup.add(types.InlineKeyboardButton(f"📅 {m[0]}", callback_data=f"dmon_{m[0]}"))
    bot.send_message(message.chat.id, "Ойни танланг:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('dmon_'))
def daily_days(call):
    mon = call.data.split('_')[1]
    conn = sqlite3.connect('finance.db'); cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT date FROM finance WHERE uid=? AND date LIKE ?", (call.message.chat.id, f"{mon}%"))
    days = cursor.fetchall(); conn.close()
    markup = types.InlineKeyboardMarkup()
    for d in days: markup.add(types.InlineKeyboardButton(f"📆 {d[0]}", callback_data=f"dfin_{d[0]}"))
    bot.edit_message_text(f"{mon} ойи кунлари:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('dfin_'))
def daily_final_show(call):
    date = call.data.split('_')[1]
    conn = sqlite3.connect('finance.db'); cursor = conn.cursor()
    cursor.execute("SELECT type, category, amount, currency FROM finance WHERE uid=? AND date=?", (call.message.chat.id, date))
    items = cursor.fetchall(); conn.close()
    res = f"📆 **{date} ҳисоботи:**\n"
    for t, c, a, cur in items: res += f"\n{'💸' if 'Харажат' in t else '💰'} {c}: {a:,.0f} {cur}"
    bot.send_message(call.message.chat.id, res, parse_mode="Markdown")

# --- 🤝 ОЛДИ-БЕРДИ ВА ҚАРЗЛАР ---
@bot.message_handler(func=lambda m: "Олди-берди" in m.text)
def debt_home(message):
    bot.send_message(message.chat.id, "🤝 Қарзлар менюси:", reply_markup=debt_menu())

@bot.message_handler(func=lambda m: m.text in ["➕ Ҳаққим бор", "➖ Қарздорман"])
def debt_add_init(message):
    dt = message.text
    msg = bot.send_message(message.chat.id, f"{dt}. Исм ва сумма (Мас: Али 100):")
    bot.register_next_step_handler(msg, debt_save_step, dt)

def debt_save_step(message, dt):
    try:
        parts = message.text.split(); amt = float(parts[-1]); name = " ".join(parts[:-1])
        markup = types.InlineKeyboardMarkup()
        for c in ["UZS", "USD", "RUB", "CNY"]: markup.add(types.InlineKeyboardButton(c, callback_data=f"dsv_{dt}_{amt}_{name}_{c}"))
        bot.send_message(message.chat.id, "Валютани танланг:", reply_markup=markup)
    except: bot.send_message(message.chat.id, "❌ Хато! Исм ва суммани ёзинг.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('dsv_'))
def debt_save_final(call):
    _, dt, amt, name, cur = call.data.split('_')
    conn = sqlite3.connect('finance.db'); cursor = conn.cursor()
    cursor.execute("INSERT INTO debts (uid, d_type, name, amount, currency, date) VALUES (?,?,?,?,?,?)",
                   (call.message.chat.id, dt, name, float(amt), cur, datetime.now().strftime("%Y-%m-%d")))
    conn.commit(); conn.close()
    bot.edit_message_text(f"✅ Сақланди: {name} {amt} {cur}", call.message.chat.id, call.message.message_id)

@bot.message_handler(func=lambda m: m.text == "💰 Қарзни қайтариш")
def debt_repay_list(message):
    conn = sqlite3.connect('finance.db'); cursor = conn.cursor()
    cursor.execute("SELECT id, name, amount, currency FROM debts WHERE uid=?", (message.chat.id,))
    rows = cursor.fetchall(); conn.close()
    if not rows: bot.send_message(message.chat.id, "📭 Қарздорлар йўқ."); return
    markup = types.InlineKeyboardMarkup()
    for di, n, a, c in rows: markup.add(types.InlineKeyboardButton(f"{n} ({a} {c})", callback_data=f"prep_{di}"))
    bot.send_message(message.chat.id, "Ким қайтарди?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('prep_'))
def debt_repay_amt_input(call):
    di = call.data.split('_')[1]
    msg = bot.send_message(call.message.chat.id, "Қайтарилган суммани ёзинг:")
    bot.register_next_step_handler(msg, debt_repay_finalize, di)

def debt_repay_finalize(message, di):
    try:
        p_amt = float(message.text)
        conn = sqlite3.connect('finance.db'); cursor = conn.cursor()
        cursor.execute("SELECT name, amount, currency FROM debts WHERE id=?", (di,))
        r = cursor.fetchone()
        if r:
            new = r[1] - p_amt
            if new > 0.1: cursor.execute("UPDATE debts SET amount=? WHERE id=?", (new, di))
            else: cursor.execute("DELETE FROM debts WHERE id=?", (di,))
            conn.commit(); bot.send_message(message.chat.id, f"✅ Янгиланди! Қолдиқ: {max(0, new):,.2f}")
        conn.close()
    except: bot.send_message(message.chat.id, "❌ Фақат сон ёзинг!")

@bot.message_handler(func=lambda m: m.text == "📜 Кимда нима бор?")
def debt_full_list(message):
    conn = sqlite3.connect('finance.db'); cursor = conn.cursor()
    cursor.execute("SELECT d_type, name, amount, currency FROM debts WHERE uid=?", (message.chat.id,))
    rows = cursor.fetchall(); conn.close()
    if not rows: bot.send_message(message.chat.id, "✨ Ҳаммаси тоза! Қарзлар йўқ."); return
    res = "📜 **Қарзлар рўйхати:**\n"
    for t, n, a, c in rows: res += f"\n{'🟢' if 'Ҳаққим' in t else '🔴'} {n}: {a:,.2f} {c}"
    bot.send_message(message.chat.id, res, parse_mode="Markdown")

# --- 📊 СТАТИСТИКА ВА ВАЛЮТА ---
@bot.message_handler(func=lambda m: m.text == "📊 Статистика")
def stats_total(message):
    u_cur = get_user_currency(message.chat.id); rates = get_rates(); u_r = rates.get(u_cur, 1.0)
    conn = sqlite3.connect('finance.db'); cursor = conn.cursor()
    cursor.execute("SELECT type, amount, currency FROM finance WHERE uid=?", (message.chat.id,))
    rows = cursor.fetchall(); conn.close()
    ti, to = 0, 0
    for t, a, c in rows:
        uzs = a * rates.get(c, 1.0)
        if "Даромад" in t: ti += uzs
        else: to += uzs
    bot.send_message(message.chat.id, f"⚖️ **Умумий ҳолат ({u_cur}):**\n\n💰 Кирим: {ti/u_r:,.0f}\n💸 Чиқим: {to/u_r:,.0f}\nБаланс: {(ti-to)/u_r:,.0f}", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "💱 Валютани танлаш")
def currency_setup(message):
    markup = types.InlineKeyboardMarkup()
    for c in ["UZS", "USD", "RUB", "CNY"]: markup.add(types.InlineKeyboardButton(c, callback_data=f"setc_{c}"))
    bot.send_message(message.chat.id, "Асосий валютани танланг:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('setc_'))
def currency_final_save(call):
    c = call.data.split('_')[1]
    conn = sqlite3.connect('finance.db'); cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (uid, currency) VALUES (?,?)", (call.message.chat.id, c))
    conn.commit(); conn.close()
    bot.edit_message_text(f"✅ Асосий валюта: {c}", call.message.chat.id, call.message.message_id)

@bot.message_handler(func=lambda m: m.text == "⬅️ Ортга")
def back_home(message): bot.send_message(message.chat.id, "Асосий меню:", reply_markup=main_menu())

# --- ♾ ТЎХТАМАЙДИГАН СЕРВЕР ---
@app.route('/')
def health_check(): return "Active"
def run_web(): app.run(host='0.0.0.0', port=10000)

if __name__ == "__main__":
    init_db()
    Thread(target=run_web).start()
    while True:
        try: bot.polling(none_stop=True, interval=0, timeout=25)
        except: time.sleep(5)
