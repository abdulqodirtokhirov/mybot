import os
import telebot
from flask import Flask
from threading import Thread

# Токенни "Secrets"дан оламиз
TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)

# Бот ухлаб қолмаслиги учун веб-сервер
app = Flask('')

@app.route('/')
def home():
    return "Бот ишлаяпти!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# Ботнинг асосий функциялари
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "Салом! Xisoblagichuzbot тайёр. Пулларни ҳисоблаймизми?")

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    # Ҳозирча шунчаки жавоб қайтаради, ишлаётганини текшириш учун
    bot.reply_to(message, f"Сиз ёздингиз: {message.text}")

if __name__ == "__main__":
    keep_alive() # "Тудим-сюдим" серверини ёқиш
    print("Бот ёқилди...")
    bot.polling(none_stop=True)
if __name__ == "__main__":
    # 1. Render берадиган портни тизимдан оламиз
    port = int(os.environ.get("PORT", 8080)) 
    
    # 2. Веб-серверни (Flask) алоҳида оқимда, тўғри порт билан юргизамиз
    t = Thread(target=lambda: app.run(host='0.0.0.0', port=port))
    t.start()
    
    # 3. Ботни асосий оқимда юргизамиз
    print("Бот ёқилди...")
    bot.polling(none_stop=True)
