import os
import logging
import time
import random
from random import randint, choice
from datetime import datetime, timedelta
import requests
import json
import google.generativeai as genai
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from pyrogram.enums import PollType



app = Client("my_bot")

# Завантажуємо змінні середовища
# Railway, Heroku та інші хмарні сервіси використовують системні змінні
if os.path.exists('B.env'):
    load_dotenv('B.env')
    print("📁 Локальна розробка: використовую B.env")
elif os.path.exists('.env'):
    load_dotenv('.env')
    print("📁 Локальна розробка: використовую .env")
else:
    # Railway автоматично надає змінні середовища
    print("☁️ Хмарне розгортання: використовую змінні Railway/Heroku")

# --- Логування ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- Налаштування ---
# Перевірка наявності обов'язкових змінних середовища
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
bot_token = os.getenv('BOT_TOKEN')


if not api_id or not api_hash or not bot_token:
    print("❌ Не знайдено змінні середовища!")
    print(f"API_ID: {'✅' if api_id else '❌'}")
    print(f"API_HASH: {'✅' if api_hash else '❌'}")
    print(f"BOT_TOKEN: {'✅' if bot_token else '❌'}")
    print("\n🚂 RAILWAY: Додайте змінні в Dashboard → Variables:")
    print("   API_ID, API_HASH, BOT_TOKEN, CHANNEL_ID, ADMIN_IDS, ADMIN_USERNAMES")
    print("\n📖 Детальні інструкції: https://github.com/your-repo/blob/main/QUICK_START.md")
    exit(1)

try:
    api_id = int(api_id)
except ValueError:
    print("❌ API_ID має бути числом!")
    exit(1)

bot_name = 'Кринжик'
channel_id = os.getenv('CHANNEL_ID', '@your_channel')
admin_ids = [int(x) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()]  # Telegram ID адмінів
admin_usernames = [x.strip() for x in os.getenv('ADMIN_USERNAMES', '').split(',') if x.strip()]  # Нікнейми адмінів

# Google Generative AI налаштування
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    AI_ENABLED = True
else:
    AI_ENABLED = False
    logger.warning("Google Generative AI API ключ не налаштований. Використовуються fallback опитування.")

emojis = list("🌟😢🧂🤑💃👏👋🤭🤪🤔😧🤦💻🍷🍺🍔🌮🍎🫑😛🤨👍🐍🥰😀😍🫐🇺🇦⌨😎🎩😳😕😱🏃😂🤓😭🙃😷🤤😉🤡🙂🫲✋🐨🐹🦊🐤🐛🦋🐝🐞🦅🦣🦛🐪🐩🍀🍃🪻🌸🌊🌫🥒🍕🥮🏀🎾🏑🎽🛹🎺🪗🎸🪕🎻🪈🧩🎮🎳🎯♟🎲🏍🚨🚘🪣🧽🧪💈🏺🪞🖼🩷🧡💛🖤💜💟❌💯🔞💤0🎏🪭")
karmadata_file = "karma_data.json"
active_polls = {}
character_data_file = "character_data.json"
funpoll_cache_file = "funpoll_cache.json"
poll_creation_locks = {}  # Для захисту від дублювання опитувань

try:
    with open(character_data_file, "r", encoding="utf-8") as f:
        character_data = json.load(f)
except FileNotFoundError:
    character_data = {}

# === ДОДАЙ НАВЕРХУ ===
cooldowns = {}  # { "chatid_userid_command": datetime }

# --- Функція перевірки адміністратора ---
def is_admin(user):
    if not user:
        return False
    return (user.id in admin_ids or 
            (user.username and user.username in admin_usernames))

# --- Завантаження / збереження карми ---
def load_json(file):
    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

karma_data = load_json(karmadata_file)
character_data = load_json(character_data_file)

# Відповіді для команди /yesno
yesno_answers = [
    "✅ Так!",
    "❌ Ні!",
    "🤔 Можливо...",
    "🎲 Точно так!",
    "⛔ Ні ні ні!",
    "🌟 Зірки кажуть так!",
    "🌧️ Краще ні",
    "🔮 Моя кулька каже так",
    "💫 Абсолютно!",
    "😴 Спитай пізніше"
]

# Функції для роботи з кармою (для сумісності)
def load_karma():
    return load_json(karmadata_file)

def save_karma(data):
    save_json(karmadata_file, data)
# --- Постійне ім'я сесії для бота ---
session_name = "KrinzhikBotSession"

app = Client(
    name=session_name,
    api_id=api_id,
    api_hash=api_hash,
    bot_token=bot_token
)


print(f"🤖 {bot_name} запускається...")
logger.info(f"{bot_name} успішно ініціалізовано. AI_ENABLED={AI_ENABLED}")
# --- Логіка команд (для повторного використання у команді та callback) ---

async def process_spin_wheel(chat_id, user_id, reply_func):
    today = datetime.now().date().isoformat()
    if chat_id not in karma_data:
        karma_data[chat_id] = {}
    user_karma = karma_data[chat_id].get(user_id, {"score": 0, "last_spin_date": None})

    if user_karma.get("last_spin_date") == today:
        await reply_func("🕐 Колесо доступне лише раз на день.")
        return

    reward = random.randint(1, 5)
    user_karma["score"] += reward
    user_karma["last_spin_date"] = today
    karma_data[chat_id][user_id] = user_karma
    save_json(karmadata_file, karma_data)

    await reply_func(f"🎡 Колесо обернулось!\n+{reward} очок!\nЗагальна карма: {user_karma['score']}")



async def process_show_top_users(chat_id: str, reply_func, client=None):
    try:
        if chat_id not in karma_data or not karma_data[chat_id]:
            await reply_func("У цьому чаті ще ніхто не має карми!")
            return

        sorted_users = sorted(karma_data[chat_id].items(), key=lambda x: x[1]['score'], reverse=True)
        text = "🏆 Топ 5 гравців цього чату:\n"

        for i, (uid, data) in enumerate(sorted_users[:5], 1):
            try:
                if client:
                    user = await client.get_users(int(uid))
                    if user.username:
                        display_name = f"@{user.username}"
                    elif user.first_name:
                        display_name = user.first_name
                        if user.last_name:
                            display_name += f" {user.last_name}"
                    else:
                        display_name = f"Користувач {uid}"
                else:
                    display_name = f"Користувач {uid}"
            except Exception:
                display_name = f"Користувач {uid}"

            text += f"{i}. {display_name} — {data['score']} очок\n"

        await reply_func(text)

    except Exception as e:
        await reply_func(f"Помилка при показі топу: {e}")


async def process_show_karma(chat_id: str, user_id: str, reply_func, client=None):
    try:
        if chat_id not in karma_data:
            karma_data[chat_id] = {}
        user_karma = karma_data[chat_id].get(user_id, {"score": 0, "last_vote_date": None, "streak": 0})
        display_name = f"Користувач {user_id}"
        if client:
            try:
                user = await client.get_users(int(user_id))
                username = user.username or user.first_name or f"Користувач {user_id}"
                display_name = f"@{username}" if user.username else username
            except Exception as e:
                pass
        await reply_func(
            f"🎯 Карма {display_name}:\n"
            f"Очки: {user_karma['score']}\n"
            f"Стрик: {user_karma.get('streak', 0)}"
        )
    except Exception as e:
        await reply_func(f"Помилка при показі карми: {e}")

async def process_luckypoll(client):
    options = [choice(emojis) for _ in range(randint(2, 10))]
    correct_option_id = randint(0, len(options) - 1)
    poll = await client.send_poll(
        chat_id=channel_id,
        question=f'На Удачу {datetime.now().strftime("%d.%m.%y")}',
        options=options,
        is_anonymous=True,
        type=PollType.QUIZ,
        correct_option_id=correct_option_id,
        explanation='Maybe next time...'
    )
    active_polls[poll.poll.id] = {
        "correct_option_id": correct_option_id,
        "created_at": datetime.now()
    }

    

async def generate_horoscope_gemini():
    # Використовуємо рандомні гороскопи замість AI
    horoscopes = [
        "Сьогодні твоя карма зросте на 0.0001%! Зірки кажуть, що варто з'їсти печиво.",
        "Меркурій у ретрограді, тому твої повідомлення можуть загубитися. Але не хвилюйся!",
        "Сонце в зеніті, а це означає, що сьогодні твоя удача буде на висоті!",
        "Луна в першій чверті, тому варто почати нову справу. Наприклад, з'їсти морозиво.",
        "Венера в аспекті з Юпітером - це означає, що сьогодні ти знайдеш щось приємне.",
        "Сатурн ретроградний, але це не означає, що твоя піца буде холодною.",
        "Марс активний, тому сьогодні варто зробити щось сміливе. Наприклад, з'їсти олівці.",
        "Уран несподіваний, тому сьогодні може статися щось дивне. Але це буде весело!",
        "Нептун містичний, тому сьогодні твої мрії можуть збутися. Особливо про морозиво.",
        "Плутон трансформує, тому сьогодні ти можеш стати кращою версією себе. Або просто з'їсти шоколадку."
    ]
    
    return random.choice(horoscopes)


# --- Обробники команд ---
@app.on_message(filters.command("start"))
async def start(client, message):
    commands = [
        BotCommand("start", "Привітання"),
        BotCommand("karma", "Твоя карма"),
        BotCommand("top", "Топ гравців"),
        BotCommand("wheel", "Колесо удачі (1 раз/день)"),
        BotCommand("setname", "Встановити своє ім'я"),
        BotCommand("setname_reply", "Встановити ім'я через reply"),
        BotCommand("myname", "Переглянути своє ім'я"),
        BotCommand("horoscope", "Міні-гороскоп"),
        BotCommand("yesno", "Гра Так чи Ні"),
        BotCommand("help", "Допомога"),
        BotCommand("character", "Отримати персонажа"),
        BotCommand("Ya", "Мій опис сьогодні"),
    ]
    await client.set_bot_commands(commands)
    await message.reply_text("Привіт! Я бот для рандомних опитувань 🎯")


# Завантажуємо дані
try:
    with open(karmadata_file, "r", encoding="utf-8") as f:
        karma_data = json.load(f)
except FileNotFoundError:
    karma_data = {}

# --- Функції допомоги ---
def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def ensure_warrior(chat_id, user_id, username):
    if chat_id not in karma_data:
        karma_data[chat_id] = {}
    if user_id not in karma_data[chat_id]:
        karma_data[chat_id][user_id] = {}

    user = karma_data[chat_id][user_id]

    # Ініціалізація всіх полів
    user.setdefault("username", username)
    user.setdefault("hp", 10)
    user.setdefault("score", 0)
    user.setdefault("wins", 0)
    user.setdefault("hits", 0)
    user.setdefault("last_kick", "1970-01-01T00:00:00")  # ISO формат дати
    return user





@app.on_message(filters.command("steal"))
async def steal_command(client, message):
    if not message.reply_to_message:
        await message.reply_text("❌ Відповідай на повідомлення суперника, щоб вкрасти!")
        return

    chat_id = str(message.chat.id)
    user_id = str(message.from_user.id)
    target_id = str(message.reply_to_message.from_user.id)
    username = message.from_user.first_name
    target_name = message.reply_to_message.from_user.first_name

    user_data = ensure_warrior(chat_id, user_id, username)
    target_data = ensure_warrior(chat_id, target_id, target_name)

    steal_amount = random.randint(1, min(3, target_data["energy"]))
    user_data["energy"] += steal_amount
    target_data["energy"] -= steal_amount

    save_json(karmadata_file, karma_data)
    await message.reply_text(f"🌀 {username} вкрав {steal_amount} енергії у {target_name}!")




def can_use_command(chat_id, user_id, command):
    now = datetime.now()
    key = f"{chat_id}_{user_id}_{command}"
    if key in cooldowns:
        last_used = cooldowns[key]
        if now - last_used < timedelta(hours=6):
            return False, (timedelta(hours=6) - (now - last_used))
    cooldowns[key] = now
    return True, None


# === /random ===
@app.on_message(filters.command("random"))
async def random_command(client, message):
    chat_id = str(message.chat.id)
    user_id = str(message.from_user.id)
    username = message.from_user.first_name

    allowed, wait_time = can_use_command(chat_id, user_id, "random")
    if not allowed:
        hours, remainder = divmod(wait_time.seconds, 3600)
        minutes = remainder // 60
        await message.reply_text(f"⏳ Ти зможеш знову використати /random через {hours} год {minutes} хв.")
        return

    user_data = ensure_warrior(chat_id, user_id, username)
    effect = random.choice(["+hp", "-hp", "+energy", "-energy"])
    amount = random.randint(1, 3)

    if effect == "+hp":
        user_data["hp_current"] = min(user_data["hp_max"], user_data["hp_current"] + amount)
        text = f"🎲 Щастя! {username} отримав {amount} HP"
    elif effect == "-hp":
        user_data["hp_current"] = max(0, user_data["hp_current"] - amount)
        text = f"🎲 Невдача! {username} втратив {amount} HP"
    elif effect == "+energy":
        user_data["energy"] += amount
        text = f"🎲 Енергія +{amount} для {username}"
    else:
        user_data["energy"] -= amount
        text = f"🎲 Енергія -{amount} для {username}"

    save_json(karmadata_file, karma_data)
    await message.reply_text(text)


# === /freeze ===
@app.on_message(filters.command("freeze"))
async def freeze_command(client, message):
    if not message.reply_to_message:
        await message.reply_text("❌ Відповідай на повідомлення суперника командою /freeze")
        return

    chat_id = str(message.chat.id)
    user_id = str(message.from_user.id)
    target_id = str(message.reply_to_message.from_user.id)
    username = message.from_user.first_name
    target_name = message.reply_to_message.from_user.first_name

    allowed, wait_time = can_use_command(chat_id, user_id, "freeze")
    if not allowed:
        hours, remainder = divmod(wait_time.seconds, 3600)
        minutes = remainder // 60
        await message.reply_text(f"⏳ Ти зможеш знову використати /freeze через {hours} год {minutes} хв.")
        return

    user_data = ensure_warrior(chat_id, user_id, username)
    target_data = ensure_warrior(chat_id, target_id, target_name)

    target_data["frozen"] = True
    save_json(karmadata_file, karma_data)
    await message.reply_text(f"❄️ {username} заморозив {target_name} на один хід!")


# === /luck ===
@app.on_message(filters.command("luck"))
async def luck_command(client, message):
    chat_id = str(message.chat.id)
    user_id = str(message.from_user.id)
    username = message.from_user.first_name

    allowed, wait_time = can_use_command(chat_id, user_id, "luck")
    if not allowed:
        hours, remainder = divmod(wait_time.seconds, 3600)
        minutes = remainder // 60
        await message.reply_text(f"⏳ Ти зможеш знову використати /luck через {hours} год {minutes} хв.")
        return

    user_data = ensure_warrior(chat_id, user_id, username)

    roll = random.randint(1, 100)
    if roll <= 20:
        gain = random.randint(3, 7)
        user_data["score"] += gain
        text = f"💥 Мега-крит! Ви отримали +{gain} очок карми!"
    elif roll <= 40:
        loss = random.randint(1, 5)
        user_data["score"] = max(0, user_data["score"] - loss)
        text = f"⚠️ Фейл! Ви втратили {loss} очок карми!"
    else:
        text = "😎 Нічого не сталося, спробуйте ще раз."

    save_json(karmadata_file, karma_data)
    await message.reply_text(text)






# Таймери і активні атаки
last_kick_time = {}       # {chat_id: {user_id: datetime}}
active_attacks = {}       # {chat_id: {target_id: {"attacker": user_id, "time": datetime}}}

# === Нова RPG система воїнів ===
def ensure_warrior(chat_id, user_id, username):
    if chat_id not in karma_data:
        karma_data[chat_id] = {}
    if user_id not in karma_data[chat_id]:
        karma_data[chat_id][user_id] = {}

    user_data = karma_data[chat_id][user_id]

    # Основна інформація
    user_data.setdefault("id", user_id)
    user_data.setdefault("name", username)
    user_data.setdefault("username", username)
    
    # RPG характеристики
    user_data.setdefault("lvl", 1)
    user_data.setdefault("xp", 0)
    user_data.setdefault("hp_max", 100)
    user_data.setdefault("hp_current", 100)
    user_data.setdefault("atk", 10)
    user_data.setdefault("def", 5)
    user_data.setdefault("agi", 5)
    
    # Економіка
    user_data.setdefault("gold", 100)
    user_data.setdefault("coins", 0)  # Для сумісності
    
    # Інвентар
    user_data.setdefault("inventory", {"candies": 0, "weapon": None, "armor": None})
    
    # Щоденні активності
    user_data.setdefault("last_daily", None)
    
    # Кулдауни
    user_data.setdefault("cooldowns", {"kick": 0, "mirror": 0, "heal": 0})
    
    # Статус
    user_data.setdefault("status", "normal")  # normal, stunned, banned_from_pvp
    
    # Статистика (для сумісності)
    user_data.setdefault("score", 0)
    user_data.setdefault("wins", 0)
    user_data.setdefault("hits", 0)
    user_data.setdefault("energy", 5)
    user_data.setdefault("frozen", False)
    user_data.setdefault("last_money", None)
    user_data.setdefault("reflected", 0)

    return user_data


# === Бойові формули ===
def calculate_damage(attacker_data, target_data, weapon_modifier=0):
    """Розрахунок шкоди з урахуванням критів та захисту"""
    base_damage = attacker_data["atk"] * (1 + weapon_modifier)
    
    # Перевірка критичного удару
    crit_chance = min(50, attacker_data["agi"] * 0.5) / 100
    is_crit = random.random() < crit_chance
    crit_multiplier = 0.5 if is_crit else 0
    
    # Розрахунок ефективної шкоди
    defense_multiplier = 0.5
    effective_damage = max(1, round(base_damage * (1 + crit_multiplier) - target_data["def"] * defense_multiplier))
    
    return effective_damage, is_crit

def check_dodge(target_data):
    """Перевірка ухилення від атаки"""
    dodge_chance = min(40, target_data["agi"] * 0.7) / 100
    return random.random() < dodge_chance

def check_cooldown(user_data, action):
    """Перевірка кулдауну для дії"""
    now = time.time()
    cooldown_times = {"kick": 30, "mirror": 15, "heal": 60}  # секунди
    
    last_use = user_data["cooldowns"].get(action, 0)
    if now - last_use < cooldown_times[action]:
        remaining = cooldown_times[action] - (now - last_use)
        return False, remaining
    return True, 0

def set_cooldown(user_data, action):
    """Встановити кулдаун для дії"""
    user_data["cooldowns"][action] = time.time()

def calculate_mirror_success(target_data):
    """Розрахунок успішності відбиття"""
    base_chance = 40
    agi_bonus = target_data["agi"] * 0.2
    return (base_chance + agi_bonus) / 100

def apply_death(user_data):
    """Обробка смерті гравця"""
    # Втрата золота (10% або мінімум 10)
    gold_loss = max(10, int(user_data["gold"] * 0.1))
    user_data["gold"] = max(0, user_data["gold"] - gold_loss)
    
    # Відновлення HP до 30%
    user_data["hp_current"] = int(user_data["hp_max"] * 0.3)
    
    # Статус оглушення на 5 хвилин
    user_data["status"] = "stunned"
    user_data["stun_until"] = time.time() + 300  # 5 хвилин
    
    return gold_loss


# === /shop ===
@app.on_message(filters.command("shop"))
async def shop_command(client, message):
    text = (
        "🛒 **Магазин**\n\n"
        "1. 🍬 Цукерка здоров’я – 5 монет (використовується через /heal)\n"
        "2. ⚔️ Одноручний меч – 38 монет (додає +1 до сили удару)\n"
        "3. 🗡 Дворучний меч – 38 монет (додає +2 до сили удару)\n\n"
        "Купівля: `/buy <товар>`"
    )
    await message.reply_text(text)


# === /buy ===
@app.on_message(filters.command("buy"))
async def buy_command(client, message):
    chat_id = str(message.chat.id)
    user_id = str(message.from_user.id)
    username = message.from_user.first_name
    user_data = ensure_warrior(chat_id, user_id, username)

    if len(message.command) < 2:
        await message.reply_text("❌ Використання: /buy <товар>")
        return

    item = message.command[1].lower()

    # Ініціалізуємо інвентар
    if "inventory" not in user_data:
        user_data["inventory"] = {"candies": 0, "weapon": None}

    # === Покупка цукерки ===
    if item in ["цукерка", "candy"]:
        if user_data["coins"] < 5:
            await message.reply_text("❌ У вас недостатньо монет для покупки цукерки!")
            return
        user_data["coins"] -= 5
        user_data["inventory"]["candies"] += 1
        text = f"🍬 {username} купив цукерку здоров’я! Тепер у вас {user_data['inventory']['candies']}."

    # === Покупка меча ===
    elif item in ["меч", "sword"]:
        if user_data["coins"] < 38:
            await message.reply_text("❌ У вас недостатньо монет для покупки меча!")
            return

        # Запропонуємо вибір: одноручний або дворучний
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚔️ Одноручний (+1)", callback_data=f"buy_sword_1_{user_id}")],
            [InlineKeyboardButton("🗡 Дворучний (+2)", callback_data=f"buy_sword_2_{user_id}")]
        ])
        await message.reply_text("Виберіть тип меча:", reply_markup=keyboard)
        return

    else:
        text = "❌ Такого товару немає."

    save_json(karmadata_file, karma_data)
    await message.reply_text(text)


# === Обробка кнопок для покупки меча ===
@app.on_callback_query(filters.regex(r"^buy_sword_(\d)_(\d+)$"))
async def buy_sword_callback(client, callback_query):
    power, buyer_id = callback_query.data.split("_")[2], callback_query.data.split("_")[3]

    if str(callback_query.from_user.id) != buyer_id:
        await callback_query.answer("Ця покупка не для вас!", show_alert=True)
        return

    chat_id = str(callback_query.message.chat.id)
    user_data = ensure_warrior(chat_id, buyer_id, callback_query.from_user.first_name)

    if user_data["coins"] < 38:
        await callback_query.answer("Недостатньо монет!", show_alert=True)
        return

    user_data["coins"] -= 38
    user_data["inventory"]["weapon"] = int(power)

    save_json(karmadata_file, karma_data)
    await callback_query.message.edit_text(
        f"✅ Ви купили {'⚔️ Одноручний меч (+1)' if power=='1' else '🗡 Дворучний меч (+2)'}!"
    )






# === /money ===
@app.on_message(filters.command("money"))
async def money_command(client, message):
    chat_id = str(message.chat.id)
    user_id = str(message.from_user.id)
    username = message.from_user.first_name

    user_data = ensure_warrior(chat_id, user_id, username)

    today = datetime.now().strftime("%Y-%m-%d")

    # Перевіряємо, чи сьогодні вже отримували
    if user_data.get("last_daily") == today:
        await message.reply_text("❌ Ви вже отримали щоденну винагороду сьогодні. Спробуйте завтра!")
        return

    # Генеруємо щоденну винагороду
    gold_reward = random.randint(50, 150)
    xp_reward = random.randint(5, 15)
    
    user_data["gold"] += gold_reward
    user_data["xp"] += xp_reward
    user_data["coins"] += random.randint(5, 15)  # Для сумісності
    user_data["last_daily"] = today

    # Перевірка підвищення рівня
    level_up_text = ""
    xp_needed = user_data["lvl"] * 100  # 100 XP на рівень
    if user_data["xp"] >= xp_needed:
        user_data["lvl"] += 1
        user_data["xp"] -= xp_needed
        
        # Бонуси за рівень
        user_data["hp_max"] += 20
        user_data["hp_current"] = user_data["hp_max"]  # Повне відновлення при підвищенні
        user_data["atk"] += 2
        user_data["def"] += 1
        user_data["agi"] += 1
        
        level_up_text = f"\n🎉 ПІДВИЩЕННЯ РІВНЯ! Тепер ви {user_data['lvl']} рівня!"
        level_up_text += f"\n📈 +20 HP, +2 ATK, +1 DEF, +1 AGI"

    save_json(karmadata_file, karma_data)

    result_text = f"💰 {username} отримав щоденну винагороду!\n"
    result_text += f"🪙 +{gold_reward} золота\n"
    result_text += f"✨ +{xp_reward} XP\n"
    result_text += f"💰 Всього золота: {user_data['gold']}"
    result_text += level_up_text

    await message.reply_text(result_text)

# --- Зберегти дані ---
def save_data():
    with open(karmadata_file, "w", encoding="utf-8") as f:
        json.dump(karma_data, f, ensure_ascii=False, indent=2)

# --- /heal ---
@app.on_message(filters.command("heal"))
async def heal_command(client, message):
    chat_id = str(message.chat.id)
    user_id = str(message.from_user.id)
    username = message.from_user.first_name

    user_data = ensure_warrior(chat_id, user_id, username)

    # Перевірка кулдауну
    can_heal, remaining = check_cooldown(user_data, "heal")
    if not can_heal:
        await message.reply_text(f"⏳ Кулдаун лікування! Залишилось {int(remaining)} секунд.")
        return

    # Перевірка чи потрібне лікування
    if user_data["hp_current"] >= user_data["hp_max"]:
        await message.reply_text("❤️ Ваше здоров'я вже повне!")
        return

    # Встановлюємо кулдаун
    set_cooldown(user_data, "heal")

    # Розрахунок лікування
    base_heal = int(user_data["hp_max"] * 0.20)  # 20% від максимального HP
    heal_item_bonus = 0
    
    # Використання цукерки якщо є
    if user_data["inventory"]["candies"] > 0:
        user_data["inventory"]["candies"] -= 1
        heal_item_bonus = random.randint(10, 20)
        
    total_heal = base_heal + heal_item_bonus
    old_hp = user_data["hp_current"]
    user_data["hp_current"] = min(user_data["hp_max"], user_data["hp_current"] + total_heal)
    actual_heal = user_data["hp_current"] - old_hp

    result_text = f"💖 {username} відновив {actual_heal} HP!"
    if heal_item_bonus > 0:
        result_text += f"\n🍬 Цукерка додала +{heal_item_bonus} лікування!"
    
    result_text += f"\n❤️ HP: {user_data['hp_current']}/{user_data['hp_max']}"

    save_json(karmadata_file, karma_data)
    await message.reply_text(result_text)

# === Зміни: логіка /kick — шанс влучити та cooldown прив'язаний до конкретної пари attacker->target ===

# structure:
# last_kick_time = { chat_id: { attacker_id: { target_id: datetime } } }

@app.on_message(filters.command("kick"))
async def kick_command(client, message):
    if not message.reply_to_message:
        await message.reply_text("❌ Використовуйте /kick у відповідь на повідомлення суперника!")
        return

    chat_id = str(message.chat.id)
    attacker_id = str(message.from_user.id)
    target_id = str(message.reply_to_message.from_user.id)
    
    if attacker_id == target_id:
        await message.reply_text("❌ Не можна атакувати самого себе!")
        return

    # Створюємо записи воїнів
    attacker_data = ensure_warrior(chat_id, attacker_id, message.from_user.first_name)
    target_data = ensure_warrior(chat_id, target_id, message.reply_to_message.from_user.first_name)

    # Перевірка статусу атакуючого
    if attacker_data["status"] == "stunned":
        if time.time() < attacker_data.get("stun_until", 0):
            remaining = int(attacker_data["stun_until"] - time.time())
            await message.reply_text(f"😵 Ви оглушені! Залишилось {remaining} секунд.")
            return
        else:
            attacker_data["status"] = "normal"

    # Перевірка кулдауну
    can_attack, remaining = check_cooldown(attacker_data, "kick")
    if not can_attack:
        await message.reply_text(f"⏳ Кулдаун атаки! Залишилось {int(remaining)} секунд.")
        return

    # Встановлюємо кулдаун
    set_cooldown(attacker_data, "kick")

    # Перевірка ухилення
    if check_dodge(target_data):
        save_json(karmadata_file, karma_data)
        await message.reply_text(
            f"💨 {message.reply_to_message.from_user.first_name} ухилився від атаки {message.from_user.first_name}!"
        )
        return

    # Розрахунок шкоди
    weapon_modifier = 0
    if attacker_data["inventory"]["weapon"]:
        weapon_modifier = attacker_data["inventory"]["weapon"] * 0.1  # 10% за рівень зброї

    damage, is_crit = calculate_damage(attacker_data, target_data, weapon_modifier)
    
    # Застосування шкоди
    target_data["hp_current"] = max(0, target_data["hp_current"] - damage)
    
    # Формування повідомлення
    crit_text = " 💥 КРИТИЧНИЙ УДАР!" if is_crit else ""
    result_text = f"⚔️ {message.from_user.first_name} атакує {message.reply_to_message.from_user.first_name}!\n"
    result_text += f"💔 Завдано {damage} шкоди{crit_text}\n"
    result_text += f"❤️ HP цілі: {target_data['hp_current']}/{target_data['hp_max']}"

    # Перевірка смерті
    if target_data["hp_current"] <= 0:
        gold_loss = apply_death(target_data)
        attacker_data["wins"] += 1
        attacker_data["xp"] += 10
        
        result_text += f"\n💀 {message.reply_to_message.from_user.first_name} побитий!"
        result_text += f"\n💰 Втрачено {gold_loss} золота"
        result_text += f"\n🏆 {message.from_user.first_name} отримує 10 XP!"

    # Реєструємо атаку для можливого mirror
    active_attacks.setdefault(chat_id, {})
    active_attacks[chat_id][target_id] = {
        "attacker": attacker_id, 
        "damage": damage,
        "time": time.time()
    }

    save_json(karmadata_file, karma_data)
    await message.reply_text(result_text)


# --- /mirror ---
@app.on_message(filters.command("mirror"))
async def mirror_command(client, message):
    chat_id = str(message.chat.id)
    user_id = str(message.from_user.id)

    # Створюємо запис воїна
    user_data = ensure_warrior(chat_id, user_id, message.from_user.first_name)

    # Перевірка кулдауну
    can_mirror, remaining = check_cooldown(user_data, "mirror")
    if not can_mirror:
        await message.reply_text(f"⏳ Кулдаун mirror! Залишилось {int(remaining)} секунд.")
        return

    # Перевірка наявності атаки
    if chat_id not in active_attacks or user_id not in active_attacks[chat_id]:
        await message.reply_text("❌ Немає атаки для відбиття!")
        return

    attack_info = active_attacks[chat_id][user_id]
    attacker_id = attack_info["attacker"]
    original_damage = attack_info["damage"]

    # Перевірка часу (атаку можна відбити протягом 10 секунд)
    if time.time() - attack_info["time"] > 10:
        del active_attacks[chat_id][user_id]
        await message.reply_text("❌ Занадто пізно для відбиття атаки!")
        return

    # Встановлюємо кулдаун
    set_cooldown(user_data, "mirror")

    # Перевірка успішності відбиття
    mirror_chance = calculate_mirror_success(user_data)
    if random.random() > mirror_chance:
        del active_attacks[chat_id][user_id]
        await message.reply_text(f"💔 {message.from_user.first_name} не зміг відбити атаку!")
        return

    # Успішне відбиття
    attacker_data = ensure_warrior(chat_id, attacker_id, "Невідомий")
    
    # Відбита шкода (50-100% від оригінальної)
    reflected_damage = random.randint(int(original_damage * 0.5), original_damage)
    attacker_data["hp_current"] = max(0, attacker_data["hp_current"] - reflected_damage)
    
    # Статистика
    user_data.setdefault("reflected", 0)
    user_data["reflected"] += 1
    user_data["xp"] += 5  # Бонус XP за відбиття

    result_text = f"🪞 {message.from_user.first_name} відбив атаку!\n"
    result_text += f"💔 Відбито {reflected_damage} шкоди назад!\n"
    result_text += f"✨ +5 XP за майстерне відбиття!"

    # Перевірка смерті атакуючого
    if attacker_data["hp_current"] <= 0:
        gold_loss = apply_death(attacker_data)
        result_text += f"\n💀 Атакуючий побитий власною атакою!"
        result_text += f"\n💰 Втрачено {gold_loss} золота"

    # Видаляємо атаку після відбиття
    del active_attacks[chat_id][user_id]

    save_json(karmadata_file, karma_data)
    await message.reply_text(result_text)

# --- /warrior ---
@app.on_message(filters.command("warrior"))
async def warrior_command(client, message):
    chat_id = str(message.chat.id)
    user_id = str(message.from_user.id)
    user_data = ensure_warrior(chat_id, user_id, message.from_user.first_name)

    # Перевірка статусу
    status_text = ""
    if user_data["status"] == "stunned":
        if time.time() < user_data.get("stun_until", 0):
            remaining = int(user_data["stun_until"] - time.time())
            status_text = f"\n😵 Статус: Оглушений ({remaining}с)"
        else:
            user_data["status"] = "normal"

    # Формування інформації про воїна
    hp_bar = "█" * int(user_data["hp_current"] / user_data["hp_max"] * 10)
    hp_bar += "░" * (10 - len(hp_bar))
    
    weapon_text = ""
    if user_data["inventory"]["weapon"]:
        weapon_icons = {1: "⚔️", 2: "🗡️"}
        weapon_text = f"\n🗡️ Зброя: {weapon_icons.get(user_data['inventory']['weapon'], '⚔️')} Рівень {user_data['inventory']['weapon']}"

    text = f"""⚔️ **Воїн {user_data['name']}**

🏅 Рівень: {user_data['lvl']} (XP: {user_data['xp']})
❤️ HP: {user_data['hp_current']}/{user_data['hp_max']} [{hp_bar}]
⚔️ Атака: {user_data['atk']}
🛡️ Захист: {user_data['def']}
💨 Спритність: {user_data['agi']}
💰 Золото: {user_data['gold']}{weapon_text}{status_text}

🏆 Перемог: {user_data['wins']}
🪞 Відбито атак: {user_data.get('reflected', 0)}"""

    await message.reply_text(text)

# --- /stats ---
@app.on_message(filters.command("stats"))
async def stats_command(client, message):
    chat_id = str(message.chat.id)
    user_id = str(message.from_user.id)
    user_data = ensure_warrior(chat_id, user_id, message.from_user.first_name)

    await message.reply_text(
        f"📊 Статистика {user_data['username']}:\n"
        f"🏆 Виграні бої: {user_data['wins']}\n"
        f"💖 Очки моралі: {user_data['score']}\n"
        f"🛡 Відбито атак: {user_data['reflected']}"
    )

   










@app.on_message(filters.command("go"))
async def luckypoll_command(client, message):
    # Перевіряємо, чи користувач є адміністратором
    if not is_admin(message.from_user):
        await message.reply_text("⛔️ Команда доступна лише для адміністраторів")
        return
    
    await message.delete()
    try:
        await process_luckypoll(client)
    except Exception as err:
        await message.reply_text(f"Помилка: {err}")

@app.on_message(filters.command("karma"))
async def show_karma_command(client, message):
    try:
        if not message.from_user:
            await message.reply_text("❌ Помилка: не вдалося визначити користувача. Спробуйте написати боту в приватному повідомленні.")
            return
        chat_id = str(message.chat.id)
        user_id = str(message.from_user.id)
        await process_show_karma(chat_id, user_id, message.reply_text, client)
    except Exception as e:
        await message.reply_text(f"Виникла помилка: {e}")

@app.on_message(filters.command("top"))
async def show_top_users_command(client, message):
    chat_id = str(message.chat.id)
    await process_show_top_users(chat_id, message.reply_text, client)
@app.on_message(filters.command("wheel"))
async def spin_wheel_command(client, message):
    if not message.from_user:
        await message.reply_text("❌ Помилка: не вдалося визначити користувача. Спробуйте написати боту в приватному повідомленні.")
        return

    chat_id = str(message.chat.id)
    user_id = str(message.from_user.id)

    # Обгортаємо reply_func
    async def reply_func(text):
        await message.reply_text(text)

    await process_spin_wheel(chat_id, user_id, reply_func)

# --- /help ---
@app.on_message(filters.command("help"))
async def help_command(client, message):
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗓 Команди дня", callback_data="help_daily"),
            InlineKeyboardButton("⚔ Команди битв", callback_data="help_battle")
        ],
        [
            InlineKeyboardButton("🛒 Магазин", callback_data="help_shop"),
            InlineKeyboardButton("✍ Для текстів", callback_data="help_text")
        ]
    ])

    await message.reply_text(
        "📖 Привіт, Я Кринжик, бот який піднімає настрій :). Обери команду по душі:",
        reply_markup=keyboard
    )


# --- Допоміжні клавіатури для /help ---
def build_help_main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗓 Команди дня", callback_data="help_daily"),
            InlineKeyboardButton("⚔ Команди битв", callback_data="help_battle")
        ],
        [
            InlineKeyboardButton("🛒 Магазин", callback_data="help_shop"),
            InlineKeyboardButton("✍ Для текстів", callback_data="help_text")
        ]
    ])

def build_back_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Назад", callback_data="help_main")]
    ])


# --- Обробка кнопок ---
@app.on_callback_query()
async def help_buttons(client, callback_query):
    data = callback_query.data

    # Головне меню
    if data == "help_main":
        text = "📖 Привіт, Я Кринжик, бот який піднімає настрій :). Обери команду по душі:"
        await callback_query.message.edit_text(text, reply_markup=build_help_main_keyboard())
        await callback_query.answer()
        return

    # Категорії
    if data == "help_daily":
        text = (
            "🗓 Команди дня\n\n"
            "/karma – Твоя карма\n"
            "/top – Топ гравців\n"
            "/wheel – Колесо удачі\n"
            "/horoscope – Міні-гороскоп\n"
            "/ya – Мій опис сьогодні\n"
            "/coffee – Скільки чашок кави сьогодні"
            "/setname – Встановити ім’я\n"
            "/setname_reply – Встановити ім’я через reply\n"
            "/emoji – Мій настрій трьома емодзі\n"
            "/myname – Переглянути своє ім'я\n"
            "/character - Мій персонаж сьогодні"
        )
        await callback_query.message.edit_text(text, reply_markup=build_back_keyboard())
        await callback_query.answer()
        return

    if data == "help_battle":
        text = (
            "⚔ Команди битв\n\n"
            "/warrior – Воїн\n"
            "/stats – Переглянути статистику\n"
            "/kick – Атакувати суперника\n"
            "/mirror – Відбити атаку\n"
            "/heal – Використати цукерку здоров'я\n"
            "/steal - Вкрасти\n"
            "/random - випадковий хід\n"
            "/luck - шанс на мега-крит урон\n"
            "/freeze - зупинити суперника\n"
        )
        await callback_query.message.edit_text(text, reply_markup=build_back_keyboard())
        await callback_query.answer()
        return

    if data == "help_shop":
        text = (
            "🛒 Магазин\n\n"
            "/shop – Переглянути товари\n"
            "/buy <товар> <кількість> – Купити\n"
            "/inventory – Переглянути інвентар"
        )
        await callback_query.message.edit_text(text, reply_markup=build_back_keyboard())
        await callback_query.answer()
        return

    if data == "help_text":
        text = (
            "✍ Для текстів\n\n"
            "/shout – Повідомлення капсом\n"
            "/reverse – Повідомлення задом наперед\n"
            
        )
        await callback_query.message.edit_text(text, reply_markup=build_back_keyboard())
        await callback_query.answer()
        return

    # Невідома дія — просто відповідаємо, щоб кнопка не "висіла"
    await callback_query.answer("Невідома дія.", show_alert=False)

@app.on_message(filters.command("test"))
async def test_command(client, message):
    try:
        if not message.from_user:
            await message.reply_text("❌ Помилка: не вдалося визначити користувача. Спробуйте написати боту в приватному повідомленні.")
            return
            
        user_id = str(message.from_user.id)
        await message.reply_text(
            f"🧪 Тест бота:\n"
            f"Ваш ID: {user_id}\n"
            f"Кількість користувачів у базі: {len(karma_data)}\n"
            f"Ваші дані: {karma_data.get(user_id, 'Не знайдено')}\n"
            f"Бот працює: ✅"
        )
    except Exception as e:
        await message.reply_text(f"Помилка тесту: {e}")

@app.on_message(filters.command("reload"))
async def reload_karma_command(client, message):
    try:
        global karma_data
        karma_data = load_karma()
        await message.reply_text(f"✅ Дані карми перезавантажено! Користувачів: {len(karma_data)}")
    except Exception as e:
        await message.reply_text(f"Помилка перезавантаження: {e}")

@app.on_message(filters.command("myid"))
async def get_my_id(client, message):
    if not message.from_user:
        await message.reply_text("❌ Помилка: не вдалося визначити користувача. Спробуйте написати боту в приватному повідомленні.")
        return
        
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    await message.reply_text(f"🆔 Ваш Telegram ID: {user_id}\nІм'я: {username}")

@app.on_message(filters.command("setname"))
async def set_user_name(client, message):
    if not message.from_user:
        await message.reply_text("❌ Помилка: не вдалося визначити користувача. Спробуйте написати боту в приватному повідомленні.")
        return
        
    try:
        # Отримуємо ім'я з повідомлення
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply_text("❌ Використання: /setname <ваше ім'я>\nНаприклад: /setname Іван")
            return
            
        new_name = args[1].strip()
        if len(new_name) > 50:
            await message.reply_text("❌ Ім'я занадто довге. Максимум 50 символів.")
            return
            
        chat_id = str(message.chat.id)
        user_id = str(message.from_user.id)
        
        # Отримуємо або створюємо дані користувача
        if chat_id not in karma_data:
            karma_data[chat_id] = {}
        if user_id not in karma_data[chat_id]:
            karma_data[chat_id][user_id] = {"score": 0, "last_vote_date": None, "streak": 0}
        
        # Зберігаємо ім'я користувача
        karma_data[chat_id][user_id]["display_name"] = new_name
        save_karma(karma_data)
        
        await message.reply_text(f"✅ Ваше ім'я встановлено: {new_name}")
        
    except Exception as e:
        logger.error(f"Помилка в команді setname: {e}")
        await message.reply_text(f"Виникла помилка: {e}")@app.on_message(filters.command("setname_simple"))
async def set_user_name_simple(client, message):
    logger.info(f"Команда setname_simple викликана користувачем {message.from_user.id if message.from_user else 'None'}")
    
    if not message.from_user:
        await message.reply_text("❌ Помилка: не вдалося визначити користувача.")
        return
        
    try:
        # Отримуємо ім'я з повідомлення
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply_text("❌ Використання: /setname_simple <ваше ім'я>\nНаприклад: /setname_simple Іван")
            return
            
        new_name = args[1].strip()
        logger.info(f"Отримано ім'я: '{new_name}'")
        
        if len(new_name) > 50:
            await message.reply_text("❌ Ім'я занадто довге. Максимум 50 символів.")
            return
            
        chat_id = str(message.chat.id)
        user_id = str(message.from_user.id)
        logger.info(f"Встановлюю ім'я '{new_name}' для користувача {user_id}")
        
        # Отримуємо або створюємо дані користувача
        if chat_id not in karma_data:
            karma_data[chat_id] = {}
        if user_id not in karma_data[chat_id]:
            karma_data[chat_id][user_id] = {"score": 0, "last_vote_date": None, "streak": 0}
        
        # Зберігаємо ім'я користувача
        karma_data[chat_id][user_id]["display_name"] = new_name
        save_karma(karma_data)
        
        logger.info(f"Ім'я успішно збережено для користувача {user_id}")
        await message.reply_text(f"✅ Ваше ім'я встановлено: {new_name}")
        
    except Exception as e:
        logger.error(f"Помилка в команді setname_simple: {e}")
        await message.reply_text(f"Виникла помилка: {e}")

@app.on_message(filters.command("setname_reply"))
async def set_user_name_reply(client, message):
    logger.info(f"Команда setname_reply викликана користувачем {message.from_user.id if message.from_user else 'None'}")
    
    if not message.from_user:
        await message.reply_text("❌ Помилка: не вдалося визначити користувача.")
        return
        
    try:
        # Перевіряємо, чи є reply на повідомлення
        if not message.reply_to_message:
            logger.info("Немає reply повідомлення")
            await message.reply_text(
                "❌ Використання: /setname_reply\n"
                "1. Напишіть своє ім'я в повідомленні\n"
                "2. Відповідайте на це повідомлення командою /setname_reply\n"
                "Наприклад:\n"
                "Користувач: Іван\n"
                "Користувач: /setname_reply (відповідь на повідомлення 'Іван')"
            )
            return
            
        # Отримуємо ім'я з повідомлення, на яке відповідаємо
        new_name = message.reply_to_message.text.strip()
        logger.info(f"Отримано ім'я: '{new_name}'")
        
        if len(new_name) > 50:
            await message.reply_text("❌ Ім'я занадто довге. Максимум 50 символів.")
            return
            
        chat_id = str(message.chat.id)
        user_id = str(message.from_user.id)
        logger.info(f"Встановлюю ім'я '{new_name}' для користувача {user_id}")
        
        # Отримуємо або створюємо дані користувача
        if chat_id not in karma_data:
            karma_data[chat_id] = {}
        if user_id not in karma_data[chat_id]:
            karma_data[chat_id][user_id] = {"score": 0, "last_vote_date": None, "streak": 0}
        
        # Зберігаємо ім'я користувача
        karma_data[chat_id][user_id]["display_name"] = new_name
        save_karma(karma_data)
        
        logger.info(f"Ім'я успішно збережено для користувача {user_id}")
        await message.reply_text(f"✅ Ваше ім'я встановлено: {new_name}")
        
    except Exception as e:
        logger.error(f"Помилка в команді setname_reply: {e}")
        await message.reply_text(f"Виникла помилка: {e}")
@app.on_message(filters.command("update_users"))
async def update_users_info(client, message):
    if not is_admin(message.from_user):
        await message.reply_text("⛔️ Команда доступна лише для адміністраторів")
        return
        
    try:
        updated_count = 0
        for chat_id in karma_data.keys():
            for uid in karma_data[chat_id].keys():
                try:
                    user = await client.get_users(int(uid))
                    logger.info(f"Оновлено інформацію про користувача {uid}: {user.first_name} (@{user.username})")
                    updated_count += 1
                except Exception as e:
                    logger.warning(f"Не вдалося оновити інформацію про користувача {uid}: {e}")
        
        await message.reply_text(f"✅ Оновлено інформацію про {updated_count} користувачів")
    except Exception as e:
        await message.reply_text(f"Помилка оновлення: {e}")

# /reverse - через reply
@app.on_message(filters.command("reverse") & filters.text)
async def reverse_command(client, message):
    if not message.reply_to_message or not message.reply_to_message.text:
        await message.reply_text("❌ Використання: відповісти на повідомлення командою /reverse")
        return

    original_text = message.reply_to_message.text
    reversed_text = original_text[::-1]
    await message.reply_to_message.reply(f"🔄 {reversed_text}")


# /shout - через reply
@app.on_message(filters.command("shout"))
async def shout_command(client, message):
    # Перевірка, що користувач відповів на повідомлення
    if not message.reply_to_message or not message.reply_to_message.text:
        await message.reply_text("❌ Використання: відповісти на повідомлення командою /shout")
        return

    original_text = message.reply_to_message.text
    shouted_text = original_text.upper()
    await message.reply_to_message.reply(f"📢 {shouted_text}")






@app.on_message(filters.command("myname"))
async def show_user_name(client, message):
    if not message.from_user:
        await message.reply_text("❌ Помилка: не вдалося визначити користувача.")
        return
        
    try:
        chat_id = str(message.chat.id)
        user_id = str(message.from_user.id)
        user_data = karma_data.get(chat_id, {}).get(user_id, {})
        
        if "display_name" in user_data:
            await message.reply_text(f"👤 Ваше ім'я в топі: {user_data['display_name']}")
        else:
            # Показуємо Telegram ім'я
            username = message.from_user.username or message.from_user.first_name
            display_name = f"@{username}" if message.from_user.username else username
            await message.reply_text(
                f"👤 У вас не встановлено власне ім'я.\n"
                f"Telegram ім'я: {display_name}\n"
                f"Використай /setname_reply щоб встановити своє ім'я для топу."
            )
        
    except Exception as e:
        logger.error(f"Помилка в команді myname: {e}")
        await message.reply_text(f"Виникла помилка: {e}")

PIXABAY_API_KEY = os.getenv('PIXABAY_API_KEY')

# /character - показує нову картинку раз на день
@app.on_message(filters.command("character"))
async def character_command(client, message):
    if not message.from_user:
        await message.reply_text("❌ Не вдалося визначити користувача.")
        return

    chat_id = str(message.chat.id)
    user_id = str(message.from_user.id)
    today = datetime.now().date().isoformat()

    if chat_id not in character_data:
        character_data[chat_id] = {}

    user_info = character_data[chat_id].get(user_id, {})

    # Якщо персонаж на сьогодні вже створений
    if user_info.get("last_character_date") == today and "character_url" in user_info:
        await message.reply_text("❌ Ви вже отримали персонажа сьогодні. Спробуйте завтра!")
        return

    # Генеруємо нового персонажа
    try:
        url = f"https://pixabay.com/api/?key={PIXABAY_API_KEY}&q=cartoon+character&image_type=photo&orientation=horizontal&safesearch=true&per_page=50"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            hits = data.get("hits", [])
            if hits:
                img_url = random.choice(hits)["webformatURL"]
                # Зберігаємо URL та дату
                user_info["last_character_date"] = today
                user_info["character_url"] = img_url
                character_data[chat_id][user_id] = user_info
                save_json(character_data_file, character_data)

                await message.reply_photo(img_url)
            else:
                await message.reply_text("Не знайдено жодної картинки персонажа на Pixabay.")
        else:
            await message.reply_text(f"Pixabay API error: {resp.status_code}")
    except Exception as e:
        await message.reply_text(f"Помилка пошуку картинки: {e}")


# /emoji - генерує три випадкові емодзі на сьогодні
@app.on_message(filters.command("emoji"))
async def emoji_command(client, message):
    if not message.from_user:
        await message.reply_text("❌ Не вдалося визначити користувача.")
        return

    chat_id = str(message.chat.id)
    user_id = str(message.from_user.id)
    today = datetime.now().date().isoformat()

    if chat_id not in character_data:
        character_data[chat_id] = {}

    user_info = character_data[chat_id].get(user_id, {})

    # Якщо вже є емоції на сьогодні → показуємо їх
    if user_info.get("last_emoji_date") == today and "emojis" in user_info:
        await message.reply_text(f"Мій настрій сьогодні: {user_info['emojis']}")
        return

    # Генеруємо три нові емоції
    mood = "".join(random.sample(emojis, 3))
    user_info["last_emoji_date"] = today
    user_info["emojis"] = mood
    character_data[chat_id][user_id] = user_info
    save_json(character_data_file, character_data)

    await message.reply_text(f"Твій муд сьогодні: {mood}")


# /coffe - скільки чашок кави сьогодні пити
@app.on_message(filters.command("coffee"))
async def coffe_command(client, message):
    if not message.from_user:
        await message.reply_text("❌ Не вдалося визначити користувача.")
        return

    chat_id = str(message.chat.id)
    user_id = str(message.from_user.id)
    today = datetime.now().date().isoformat()

    if chat_id not in character_data:
        character_data[chat_id] = {}

    user_info = character_data[chat_id].get(user_id, {})

    # Якщо вже є дані на сьогодні → показуємо їх
    if user_info.get("last_coffee_date") == today and "coffee" in user_info:
        await message.reply_text(f"Сьогодні ти маєш випити {user_info['coffee']} чашок кави ☕")
        return

    # Генеруємо кількість кави
    cups = random.randint(1, 10)
    user_info["last_coffee_date"] = today
    user_info["coffee"] = cups
    character_data[chat_id][user_id] = user_info
    save_json(character_data_file, character_data)

    await message.reply_text(f"Сьогодні ти маєш випити {cups} чашок кави ☕")


# /ya - показує персонажа + карму + емодзі + каву
@app.on_message(filters.command("ya"))
async def ya_command(client, message):
    if not message.from_user:
        await message.reply_text("❌ Не вдалося визначити користувача.")
        return

    chat_id = str(message.chat.id)
    user_id = str(message.from_user.id)
    user_info = character_data.get(chat_id, {}).get(user_id, {})

    today = datetime.now().date().isoformat()

    # Перевірка персонажа
    if user_info.get("last_character_date") != today or "character_url" not in user_info:
        await message.reply_text("Спочатку отримайте персонажа командою /character")
        return

    # Підтягування даних
    mood = user_info.get("emojis", "🤔🤷🙂")
    coffe = user_info.get("coffee", "??")
    img_url = user_info["character_url"]
    score = karma_data.get(chat_id, {}).get(user_id, {}).get("score", 0)

    caption = (
        f"👤 {message.from_user.first_name}\n"
        f"✨ Карма: {score}\n"
        f"Сьогодні ви 🌟\n"
        f"Мій настрій сьогодні: {mood}\n"
        f"☕ Кількість кави на сьогодні: {coffe} чашок"
    )
    await message.reply_photo(img_url, caption=caption)




@app.on_message(filters.command("horoscope"))
async def horoscope_command(client, message):
    if not message.from_user:
        await message.reply_text("❌ Помилка: не вдалося визначити користувача.")
        return
    prediction = await generate_horoscope_gemini()
    await message.reply_text(f"🌟 Твій міні-гороскоп:\n{prediction}")

@app.on_message(filters.command("yesno"))
async def yesno_command(client, message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply_text("❓ Напиши питання після команди! Наприклад: /yesno Чи буде дощ?")
        return
    chat_id = str(message.chat.id)
    user_id = str(message.from_user.id)
    question = args[1].strip()
    answer = random.choice(yesno_answers)
    await message.reply_text(f"❓ {question}\n💡 {answer}")


# --- Обробники callback-кнопок ---

@app.on_callback_query()
async def handle_callbacks(client, callback_query):
    data = callback_query.data
    user_id = str(callback_query.from_user.id)
    msg = callback_query.message

    logger.info(f"CALLBACK: {data} від {user_id}")
    
    try:
        if data in ["top", "horoscope", "funpoll", "character", "randompoll"]:
            try:
                await msg.delete()
            except Exception as e:
                logger.warning(f"Не вдалося видалити повідомлення з кнопками: {e}")

        if data == "wheel":
            await process_spin_wheel(client, msg, user_id)
        elif data == "top":
            await process_show_top_users(client, msg)
        elif data == "karma":
            await process_show_karma(client, msg, user_id)
        elif data == "go":
            if not is_admin(msg.chat.id, callback_query.from_user.id):
                await msg.reply_text("⛔️ Команда доступна лише для адміністраторів")
                await callback_query.answer()
                return
            await msg.delete()
            await process_luckypoll(client)
        elif data == "character":
            await character_command(client, msg)
        elif data == "horoscope":
            await horoscope_command(client, msg)
        elif data == "yesno":
            await msg.reply_text("Використай /yesno та своє питання! Наприклад: /yesno Чи буде щастя?")
    finally:
        # відповідаємо callback-у, щоб кнопка не "висіла"
        await callback_query.answer()


            

@app.on_message(filters.command("admin"))
async def admin_panel(client, message):
    if not message.from_user:
        await message.reply_text("❌ Помилка: не вдалося визначити користувача. Спробуйте написати боту в приватному повідомленні.")
        return
        
    if not is_admin(message.from_user):
        await message.reply_text("⛔️ Доступ лише для адміністраторів")
        return
    await message.reply_text(f"👑 Панель адміністратора\nЗареєстровано користувачів: {len(karma_data)}")

# --- Обробник голосувань (PollAnswer) ---

from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

@app.on_raw_update()
async def handle_poll_answer_raw(client, update, users, chats):
    # Перевіряємо тип апдейту
    if update.__class__.__name__ != "UpdatePollAnswer":
        return

    user_id = str(update.user_id)
    poll_id = update.poll_id

    # Безпечний доступ до option_ids
    option_ids = getattr(update, "option_ids", None)
    if not option_ids:
        # Нема обраних варіантів — нічого не робимо
        return
    selected_option = option_ids[0]

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    correct_option = active_polls.get(poll_id, {}).get("correct_option_id")
    if correct_option is None:
        return

    # Безпечний доступ до чату в апдейті
    chat_obj = getattr(update, "chat", None)
    if not chat_obj or not getattr(chat_obj, "id", None):
        # Не можемо визначити чат — пропускаємо
        return
    chat_id = str(chat_obj.id)

    # Ініціалізація записів
    if chat_id not in karma_data:
        karma_data[chat_id] = {}
    user_karma = karma_data[chat_id].get(user_id, {"score": 0, "last_vote_date": None, "streak": 0})

    # Нарахування за участь
    user_karma["score"] = user_karma.get("score", 0) + 1

    # Обробка стрику — безпечний парсинг last_vote_date
    last_vote_str = user_karma.get("last_vote_date")
    if last_vote_str:
        last_vote_date = None
        try:
            last_vote_date = datetime.fromisoformat(last_vote_str).replace(hour=0, minute=0, second=0, microsecond=0)
        except Exception:
            try:
                last_vote_date = datetime.strptime(last_vote_str, '%Y-%m-%dT%H:%M:%S').replace(hour=0, minute=0, second=0, microsecond=0)
            except Exception:
                last_vote_date = None

        if last_vote_date:
            if last_vote_date == today - timedelta(days=1):
                user_karma["streak"] = user_karma.get("streak", 0) + 1
            elif last_vote_date < today - timedelta(days=1):
                user_karma["streak"] = 1
        else:
            user_karma["streak"] = 1
    else:
        user_karma["streak"] = 1

    # Бонуси за стрик
    if user_karma.get("streak", 0) >= 3:
        user_karma["score"] += 2 + (user_karma["streak"] - 3)

    # Бонус за правильну відповідь
    if selected_option == correct_option:
        user_karma["score"] += 2

    # Оновлюємо дату і зберігаємо
    user_karma["last_vote_date"] = today.isoformat()
    karma_data[chat_id][user_id] = user_karma
    save_karma(karma_data)

    # Повідомлення користувачу (не критично, але зручне)
    try:
        await client.send_message(int(user_id), f"🎉 Отримано очки!\nЗагальна карма: {user_karma['score']}")
    except Exception as e:
        logger.warning(f"Не можу написати користувачу {user_id}: {e}")

    try:
        await client.send_message(int(user_id), f"🎉 Отримано очки!\nЗагальна карма: {user_karma['score']}")
    except Exception as e:
        logger.warning(f"Не можу написати користувачу {user_id}: {e}")

        
        
# --- Запуск ---

if __name__ == "__main__":
    # Якщо файл з кармою не існує, створити пустий
    if not os.path.exists(karmadata_file):
        with open(karmadata_file, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=4)

    # Якщо файл з персонажами не існує, створити пустий
    if not os.path.exists(character_data_file):
        with open(character_data_file, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=4)

    print(f"{bot_name} запущено...")
    try:
        app.run()
    except Exception as e:
        if "FLOOD_WAIT" in str(e):
            print("⚠️ Telegram заблокував бота через занадто часті спроби.")
            print("⏳ Зачекайте 30-40 хвилин перед наступною спробою.")
            print(f"📝 Помилка: {e}")
        else:
            print(f"❌ Помилка запуску: {e}")
