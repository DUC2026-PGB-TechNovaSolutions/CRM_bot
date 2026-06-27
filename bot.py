import os
import random
import string
import sqlite3
import telebot
from telebot import types
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

import re

# Sanitize environment inputs to fall back to defaults if placeholders are present
raw_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
BOT_TOKEN = None if not raw_token or "your bot token" in raw_token.lower() or "your_bot_token" in raw_token.lower() else raw_token

raw_db_path = os.getenv("DB_PATH", "bot.db").strip()
DB_PATH = "bot.db" if not raw_db_path or "your bot db" in raw_db_path.lower() or "your_bot_db" in raw_db_path.lower() else raw_db_path

raw_khqr_path = os.getenv("ADMIN_KHQR_PATH", "adminkhqr.png").strip()
ADMIN_KHQR_PATH = "adminkhqr.png" if not raw_khqr_path or "your admin qr" in raw_khqr_path.lower() or "your_admin_qr" in raw_khqr_path.lower() else raw_khqr_path

# Verify token format
token_pattern = re.compile(r'^\d+:[a-zA-Z0-9_-]+$')
if not BOT_TOKEN or not token_pattern.match(BOT_TOKEN):
    print("Error: TELEGRAM_BOT_TOKEN is not configured or is invalid in .env file!")
    print("Please set your valid Telegram Bot Token and restart the bot.")
    import sys
    sys.exit(1)

# Initialize bot
bot = telebot.TeleBot(BOT_TOKEN)

# Temporary session storages
REG_SESSIONS = {}      # chat_id -> {...}
LOGIN_SESSIONS = {}    # chat_id -> {...}
USER_SESSIONS = {}     # chat_id -> user_id (logged in)
DEP_SESSIONS = {}      # chat_id -> {...}
WITHDRAW_SESSIONS = {} # chat_id -> {...}
BUY_SESSIONS = {}      # chat_id -> {...}
FORGOT_SESSIONS = {}   # chat_id -> {...}

# Product Details with Khmer description, usage duration and local image path
PRODUCTS_DETAILS = {
    "skincare": {
        "name": "Skincare (🧴 ផលិតផលថែរក្សាស្បែក)",
        "price": 15.00,
        "description": "ជួយផ្តល់សំណើមដល់ស្បែកមុខ ការពារភាពជ្រួញ និងជួយឱ្យផ្ទៃមុខស្រស់ថ្លា។",
        "duration_days": 30,
        "image_path": "products/skincare.png"
    },
    "face_foam": {
        "name": "Face Foam (🧼 ហ្វូមលាងមុខ)",
        "price": 8.00,
        "description": "ហ្វូមលាងមុខកម្ចាត់ធូលីដី និងជាតិខ្លាញ់នៅលើស្បែកមុខយ៉ាងជ្រៅ ការពារមុន។",
        "duration_days": 45,
        "image_path": "products/face_foam.png"
    },
    "face_care_shampoo": {
        "name": "Face Care Shampoo (🚿 សាប៊ូកក់សក់ថែរក្សាស្បែកមុខ)",
        "price": 12.00,
        "description": "សាប៊ូកក់សក់កម្ចាត់ជាតិប្រេង ថែរក្សាស្បែកក្បាល និងសក់ឱ្យមានសុខភាពល្អ។",
        "duration_days": 60,
        "image_path": "products/face_care_shampoo.png"
    },
    "scrub_skin": {
        "name": "Scrub Skin (🧽 ស្ក្រាប់ខាត់ស្បែក)",
        "price": 10.00,
        "description": "ស្ក្រាប់ជម្រុះកោសិកាចាស់ៗ និងជួយឱ្យស្បែកទន់ម៉ដ្ឋរលោង។",
        "duration_days": 90,
        "image_path": "products/scrub_skin.png"
    },
    "face_mask": {
        "name": "Face Mask (🎭 ម៉ាសបិទមុខ)",
        "price": 5.00,
        "description": "ម៉ាសបិទមុខជួយផ្តល់សារធាតុចិញ្ចឹម និងកាត់បន្ថយភាពហត់នឿយរបស់ស្បែកមុខ។",
        "duration_days": 15,
        "image_path": "products/face_mask.png"
    },
    "lip_mouth_care": {
        "name": "Lip/Mouth Care (💋 ផលិតផលថែរក្សាបបូរមាត់)",
        "price": 6.00,
        "description": "ផលិតផលថែរក្សាបបូរមាត់ឱ្យមានសំណើម ការពារស្ងួត និងប្រេះ។",
        "duration_days": 30,
        "image_path": "products/lip_mouth_care.png"
    },
    "uv_protect": {
        "name": "UV Protect (☀️ ឡេការពារកម្តៅថ្ងៃ)",
        "price": 18.00,
        "description": "ឡេការពារកម្តៅថ្ងៃ ការពារស្បែកពីកាំរស្មី UV យ៉ាងមានប្រសិទ្ធភាព។",
        "duration_days": 60,
        "image_path": "products/uv_protect.png"
    }
}

# Helper: Get Admin Chat ID
def get_admin_chat_id():
    admin_id_str = os.getenv("ADMIN_CHAT_ID", "")
    if admin_id_str.strip() and admin_id_str.strip().replace('-', '').isdigit():
        return int(admin_id_str.strip())
    return None

# ==========================================
# Database Helper Functions (Thread-Safe)
# ==========================================
def db_execute(query, params=()):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def db_query(query, params=()):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def db_query_one(query, params=()):
    rows = db_query(query, params)
    return rows[0] if rows else None

# Initialize Database Schema
def init_db():
    # Create Users table
    db_execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_number TEXT UNIQUE,
        name TEXT,
        phone TEXT,
        ref_code TEXT UNIQUE,
        referred_by TEXT,
        password TEXT,
        customer_type TEXT,
        balance REAL DEFAULT 0.0,
        telegram_id INTEGER
    )
    """)
    # Create Deposits table
    db_execute("""
    CREATE TABLE IF NOT EXISTS deposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        bonus_amount REAL,
        status TEXT,
        screenshot_file_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    # Create Withdrawals table
    db_execute("""
    CREATE TABLE IF NOT EXISTS withdrawals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        status TEXT,
        khqr_file_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    # Create Purchases table
    db_execute("""
    CREATE TABLE IF NOT EXISTS purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        product_name TEXT,
        price REAL,
        status TEXT,
        approved_at TIMESTAMP,
        duration_days INTEGER,
        alert_sent INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Purchases table migrations (add columns if table already exists)
    try:
        db_execute("ALTER TABLE purchases ADD COLUMN approved_at TIMESTAMP")
    except Exception:
        pass
    try:
        db_execute("ALTER TABLE purchases ADD COLUMN duration_days INTEGER")
    except Exception:
        pass
    try:
        db_execute("ALTER TABLE purchases ADD COLUMN alert_sent INTEGER DEFAULT 0")
    except Exception:
        pass

    # Seed Admin User if not exists
    admin_exists = db_query_one("SELECT id FROM users WHERE account_number = '123456'")
    if not admin_exists:
        # Free up ID 1 if it is taken
        id_1_taken = db_query_one("SELECT id FROM users WHERE id = 1")
        if id_1_taken:
            new_id = db_query_one("SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM users")['next_id']
            db_execute("UPDATE users SET id = ? WHERE id = 1", (new_id,))
            db_execute("UPDATE deposits SET user_id = ? WHERE user_id = 1", (new_id,))
            db_execute("UPDATE withdrawals SET user_id = ? WHERE user_id = 1", (new_id,))
            db_execute("UPDATE purchases SET user_id = ? WHERE user_id = 1", (new_id,))
        
        # Insert admin user
        db_execute(
            """INSERT INTO users (id, account_number, name, phone, ref_code, referred_by, password, customer_type, balance)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (1, '123456', 'Netz (Admin)', '12345678', 'REF88888', None, '782005', 'admin', 10000.00)
        )
    else:
        # If admin exists, ensure details are correct and ID is 1
        current_admin = db_query_one("SELECT id FROM users WHERE account_number = '123456'")
        if current_admin['id'] != 1:
            # Free up ID 1 if it is taken
            id_1_taken = db_query_one("SELECT id FROM users WHERE id = 1")
            if id_1_taken:
                new_id = db_query_one("SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM users")['next_id']
                db_execute("UPDATE users SET id = ? WHERE id = 1", (new_id,))
                db_execute("UPDATE deposits SET user_id = ? WHERE user_id = 1", (new_id,))
                db_execute("UPDATE withdrawals SET user_id = ? WHERE user_id = 1", (new_id,))
                db_execute("UPDATE purchases SET user_id = ? WHERE user_id = 1", (new_id,))
            
            # Update admin's ID to 1
            old_admin_id = current_admin['id']
            db_execute("UPDATE users SET id = 1 WHERE id = ?", (old_admin_id,))
            db_execute("UPDATE deposits SET user_id = 1 WHERE user_id = ?", (old_admin_id,))
            db_execute("UPDATE withdrawals SET user_id = 1 WHERE user_id = ?", (old_admin_id,))
            db_execute("UPDATE purchases SET user_id = 1 WHERE user_id = ?", (old_admin_id,))
            
        # Update admin account properties
        db_execute(
            "UPDATE users SET name = ?, phone = ?, password = ?, customer_type = ? WHERE id = 1",
            ('Netz (Admin)', '12345678', '782005', 'admin')
        )

# Generate Unique 6-Digit Account Number
def generate_account_number():
    while True:
        acc_num = "".join(random.choices(string.digits, k=6))
        # Ensure uniqueness
        if not db_query_one("SELECT id FROM users WHERE account_number = ?", (acc_num,)):
            return acc_num

# Generate Unique Referral Code
def generate_ref_code():
    while True:
        ref = "REF" + "".join(random.choices(string.digits, k=5))
        # Ensure uniqueness
        if not db_query_one("SELECT id FROM users WHERE ref_code = ?", (ref,)):
            return ref

# Generate Simple Password
def generate_password():
    return "".join(random.choices(string.digits, k=6))

# Check if User is Logged In (check memory, then check DB)
def get_logged_in_user(chat_id):
    user_id = USER_SESSIONS.get(chat_id)
    if user_id:
        return db_query_one("SELECT * FROM users WHERE id = ?", (user_id,))
    
    # Check database for telegram_id
    user = db_query_one("SELECT * FROM users WHERE telegram_id = ?", (chat_id,))
    if user:
        USER_SESSIONS[chat_id] = user['id']
        return user
    return None

# ==========================================
# Telegram Keyboard Markup Creators
# ==========================================
def get_main_menu_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_login = types.InlineKeyboardButton("🔓 ចូលគណនី (Log In)", callback_data="menu_login")
    btn_register = types.InlineKeyboardButton("📝 បង្កើតគណនី (Register)", callback_data="menu_register")
    btn_forgot = types.InlineKeyboardButton("🔑 ភ្លេចលេខសម្ងាត់ (Forgot Password)", callback_data="menu_forgot_pass")
    markup.add(btn_login, btn_register)
    markup.add(btn_forgot)
    return markup

def get_register_type_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_new = types.InlineKeyboardButton("🆕 អតិថិជនថ្មី (+20% bonus)", callback_data="reg_type_new")
    btn_old = types.InlineKeyboardButton("👥 អតិថិជនចាស់ (+13% bonus)", callback_data="reg_type_old")
    btn_back = types.InlineKeyboardButton("🏠 ទំព័រដើម", callback_data="go_home")
    markup.add(btn_new, btn_old)
    markup.add(btn_back)
    return markup

def get_skip_markup():
    markup = types.InlineKeyboardMarkup()
    btn_skip = types.InlineKeyboardButton("⏭️ គ្មានទេ / រំលង (Skip)", callback_data="reg_ref_skip")
    markup.add(btn_skip)
    return markup

def get_dashboard_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_dep = types.InlineKeyboardButton("💵 ស្នើដាក់លុយ (Deposit)", callback_data="dash_deposit")
    btn_wd = types.InlineKeyboardButton("💸 ស្នើដកលុយ (Withdraw)", callback_data="dash_withdraw")
    btn_shop = types.InlineKeyboardButton("🛍️ ទិញទំនិញ (Buy Products)", callback_data="dash_shop")
    btn_logout = types.InlineKeyboardButton("🚪 ចាកចេញ (Log Out)", callback_data="dash_logout")
    markup.add(btn_dep, btn_wd)
    markup.add(btn_shop)
    markup.add(btn_logout)
    return markup

def get_shop_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_skincare = types.InlineKeyboardButton("🧴 Skincare - $15.00", callback_data="buy_prod:skincare")
    btn_foam = types.InlineKeyboardButton("🧼 Face Foam - $8.00", callback_data="buy_prod:face_foam")
    btn_shampoo = types.InlineKeyboardButton("🚿 Face Care Shampoo - $12.00", callback_data="buy_prod:face_care_shampoo")
    btn_scrub = types.InlineKeyboardButton("🧽 Scrub Skin - $10.00", callback_data="buy_prod:scrub_skin")
    btn_mask = types.InlineKeyboardButton("🎭 Face Mask - $5.00", callback_data="buy_prod:face_mask")
    btn_lip = types.InlineKeyboardButton("💋 Lip/Mouth Care - $6.00", callback_data="buy_prod:lip_mouth_care")
    btn_uv = types.InlineKeyboardButton("☀️ UV Protect - $18.00", callback_data="buy_prod:uv_protect")
    btn_back = types.InlineKeyboardButton("🔙 ត្រឡប់ក្រោយ (Back)", callback_data="shop_back")
    markup.add(btn_skincare, btn_foam, btn_shampoo, btn_scrub, btn_mask, btn_lip, btn_uv, btn_back)
    return markup

def get_cancel_markup():
    markup = types.InlineKeyboardMarkup()
    btn_cancel = types.InlineKeyboardButton("❌ លុបចោល (Cancel)", callback_data="action_cancel")
    markup.add(btn_cancel)
    return markup

# ==========================================
# Bot Main Handlers
# ==========================================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    # Clean sessions
    REG_SESSIONS.pop(chat_id, None)
    LOGIN_SESSIONS.pop(chat_id, None)
    DEP_SESSIONS.pop(chat_id, None)
    WITHDRAW_SESSIONS.pop(chat_id, None)
    BUY_SESSIONS.pop(chat_id, None)
    FORGOT_SESSIONS.pop(chat_id, None)
    
    # Check login session
    user = get_logged_in_user(chat_id)
    if user:
        send_dashboard(chat_id, user)
    else:
        welcome_text = (
            "👋 **សូមស្វាគមន៍មកកាន់ Telegram Bot ផ្លូវការរបស់យើង!**\n\n"
            "សូមជ្រើសរើសជម្រើសខាងក្រោមដើម្បីបន្ត៖\n"
            "👉 **បង្កើតគណនី** ដើម្បីទទួលបានប្រាក់បន្ថែម\n"
            "👉 **ចូលគណនី** ប្រសិនបើអ្នកមានគណនីរួចហើយ"
        )
        bot.send_message(chat_id, welcome_text, parse_mode="Markdown", reply_markup=get_main_menu_markup())

@bot.message_handler(commands=['cancel'])
def handle_cancel_command(message):
    chat_id = message.chat.id
    REG_SESSIONS.pop(chat_id, None)
    LOGIN_SESSIONS.pop(chat_id, None)
    DEP_SESSIONS.pop(chat_id, None)
    WITHDRAW_SESSIONS.pop(chat_id, None)
    BUY_SESSIONS.pop(chat_id, None)
    FORGOT_SESSIONS.pop(chat_id, None)
    bot.send_message(chat_id, "🔄 ប្រតិបត្តិការត្រូវបានលុបចោល។", reply_markup=get_main_menu_markup())

# ==========================================
# Callback Query Handler
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    chat_id = call.message.chat.id
    data = call.data

    # Always answer callback to remove loading state
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    # Navigation home
    if data == "go_home":
        REG_SESSIONS.pop(chat_id, None)
        welcome_text = (
            "👋 **សូមជ្រើសរើសជម្រើសខាងក្រោមដើម្បីបន្ត៖**"
        )
        bot.edit_message_text(welcome_text, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=get_main_menu_markup())

    # Cancel action
    elif data == "action_cancel":
        REG_SESSIONS.pop(chat_id, None)
        LOGIN_SESSIONS.pop(chat_id, None)
        DEP_SESSIONS.pop(chat_id, None)
        WITHDRAW_SESSIONS.pop(chat_id, None)
        BUY_SESSIONS.pop(chat_id, None)
        FORGOT_SESSIONS.pop(chat_id, None)
        
        user = get_logged_in_user(chat_id)
        if user:
            send_dashboard(chat_id, user)
        else:
            bot.send_message(chat_id, "🔄 ប្រតិបត្តិការត្រូវបានលុបចោល។", reply_markup=get_main_menu_markup())

    # Register start
    elif data == "menu_register":
        REG_SESSIONS[chat_id] = {}
        reg_text = (
            "📝 **ការបង្កើតគណនីថ្មី**\n\n"
            "តើអ្នកជាអតិថិជនថ្មី ឬចាស់?\n"
            "• 🆕 **អតិថិជនថ្មី**៖ ទទួលបានប្រាក់បន្ថែម **២០%** លើការដាក់លុយ (ថែម **១០%** ទៀតបើមានកូដណែនាំ)\n"
            "• 👥 **អតិថិជនចាស់**៖ ទទួលបានប្រាក់បន្ថែម **១៣%** លើការដាក់លុយ"
        )
        bot.edit_message_text(reg_text, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=get_register_type_markup())

    # Register Type: New
    elif data == "reg_type_new":
        if chat_id in REG_SESSIONS:
            REG_SESSIONS[chat_id]['customer_type'] = 'new'
            msg = bot.send_message(chat_id, "👤 សូមបញ្ចូល **ឈ្មោះ** របស់អ្នក៖", parse_mode="Markdown", reply_markup=get_cancel_markup())
            bot.register_next_step_handler(msg, process_reg_name)

    # Register Type: Old
    elif data == "reg_type_old":
        if chat_id in REG_SESSIONS:
            REG_SESSIONS[chat_id]['customer_type'] = 'old'
            msg = bot.send_message(chat_id, "👤 សូមបញ្ចូល **ឈ្មោះ** របស់អ្នក៖", parse_mode="Markdown", reply_markup=get_cancel_markup())
            bot.register_next_step_handler(msg, process_reg_name)

    # Register Referral Code Skip
    elif data == "reg_ref_skip":
        if chat_id in REG_SESSIONS and REG_SESSIONS[chat_id].get('customer_type') == 'new':
            REG_SESSIONS[chat_id]['referred_by'] = None
            complete_registration(chat_id)

    # Login Start
    elif data == "menu_login" or data == "login_start":
        LOGIN_SESSIONS[chat_id] = {}
        msg = bot.send_message(chat_id, "💳 សូមបញ្ចូល **លេខកូដអាខោន** (Account Number) របស់អ្នក៖", parse_mode="Markdown", reply_markup=get_cancel_markup())
        bot.register_next_step_handler(msg, process_login_acc)

    # Forgot Password Start
    elif data == "menu_forgot_pass" or data == "forgot_pass_start":
        FORGOT_SESSIONS[chat_id] = {}
        msg = bot.send_message(chat_id, "📱 សូមបញ្ចូល **លេខទូរស័ព្ទ** (Phone Number) ដែលបានចុះឈ្មោះ៖", parse_mode="Markdown", reply_markup=get_cancel_markup())
        bot.register_next_step_handler(msg, process_forgot_phone)

    # Dashboard Logout
    elif data == "dash_logout":
        user = get_logged_in_user(chat_id)
        if user:
            db_execute("UPDATE users SET telegram_id = NULL WHERE id = ?", (user['id'],))
        USER_SESSIONS.pop(chat_id, None)
        bot.send_message(chat_id, "🚪 អ្នកបានចាកចេញពីគណនីដោយជោគជ័យ។", reply_markup=get_main_menu_markup())

    # Dashboard Deposit Request
    elif data == "dash_deposit":
        user = get_logged_in_user(chat_id)
        if user:
            DEP_SESSIONS[chat_id] = {}
            msg = bot.send_message(chat_id, "🔐 ដើម្បីសុវត្ថិភាព សូមបញ្ចូល **លេខកូដសម្ងាត់** (Password) របស់អ្នក៖", parse_mode="Markdown", reply_markup=get_cancel_markup())
            bot.register_next_step_handler(msg, process_deposit_pass_confirm)

    # Dashboard Withdraw Request
    elif data == "dash_withdraw":
        user = get_logged_in_user(chat_id)
        if user:
            WITHDRAW_SESSIONS[chat_id] = {}
            msg = bot.send_message(chat_id, "🔐 ដើម្បីសុវត្ថិភាព សូមបញ្ចូល **លេខកូដសម្ងាត់** (Password) របស់អ្នក៖", parse_mode="Markdown", reply_markup=get_cancel_markup())
            bot.register_next_step_handler(msg, process_withdraw_pass_confirm)

    # Dashboard Shop
    elif data == "dash_shop":
        user = get_logged_in_user(chat_id)
        if user:
            shop_text = (
                "🛍️ **ហាងទំនិញ (Products Shop)**\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"👤 គណនី៖ **{user['name']}**\n"
                f"💰 សមតុល្យទឹកប្រាក់៖ `${user['balance']:.2f}`\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "សូមជ្រើសរើសផលិតផលខាងក្រោមដើម្បីទិញ៖"
            )
            try:
                bot.edit_message_text(shop_text, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=get_shop_markup())
            except Exception:
                bot.send_message(chat_id, shop_text, parse_mode="Markdown", reply_markup=get_shop_markup())
        else:
            bot.send_message(chat_id, "❌ សូមចូលគណនីជាមុនសិន!", reply_markup=get_main_menu_markup())

    # Shop Back to Dashboard
    elif data == "shop_back":
        user = get_logged_in_user(chat_id)
        if user:
            try:
                bot.delete_message(chat_id, call.message.message_id)
            except Exception:
                pass
            send_dashboard(chat_id, user)
        else:
            bot.send_message(chat_id, "👋 សូមចូលគណនីជាមុនសិន។", reply_markup=get_main_menu_markup())

    # Buy Product trigger
    elif data.startswith("buy_prod:"):
        parts = data.split(":")
        prod_key = parts[1]
        user = get_logged_in_user(chat_id)
        if not user:
            bot.send_message(chat_id, "❌ សូមចូលគណនីជាមុនសិន!", reply_markup=get_main_menu_markup())
            return
            
        prod_info = PRODUCTS_DETAILS.get(prod_key)
        if not prod_info:
            bot.send_message(chat_id, "❌ ផលិតផលរកមិនឃើញឡើយ។")
            return
            
        prod_name = prod_info["name"]
        prod_price = prod_info["price"]
            
        if user['balance'] < prod_price:
            fail_markup = types.InlineKeyboardMarkup()
            btn_dep = types.InlineKeyboardButton("💵 ស្នើដាក់លុយ (Deposit)", callback_data="dash_deposit")
            btn_back = types.InlineKeyboardButton("🔙 ត្រឡប់ក្រោយ", callback_data="dash_shop")
            fail_markup.add(btn_dep, btn_back)
            bot.send_message(
                chat_id, 
                f"❌ **សមតុល្យមិនគ្រប់គ្រាន់ទេ!**\n"
                f"• សមតុល្យបច្ចុប្បន្ន៖ `${user['balance']:.2f}`\n"
                f"• តម្លៃផលិតផល៖ `${prod_price:.2f}`\n"
                f"⚠️ សូមធ្វើការដាក់លុយជាមុនសិន។", 
                parse_mode="Markdown", 
                reply_markup=fail_markup
            )
            return
            
        BUY_SESSIONS[chat_id] = {
            "product_name": prod_name,
            "price": prod_price,
            "product_key": prod_key
        }
        msg = bot.send_message(
            chat_id, 
            f"🔐 ដើម្បីសុវត្ថិភាព សូមបញ្ចូល **លេខកូដសម្ងាត់** (Password) របស់អ្នក ដើម្បីបញ្ជាក់ការទិញ **{prod_name}** (${prod_price:.2f})៖", 
            parse_mode="Markdown", 
            reply_markup=get_cancel_markup()
        )
        bot.register_next_step_handler(msg, process_purchase_pass_confirm)

    # Admin Callback Actions
    elif data.startswith("admin_dep_approve:") or data.startswith("admin_dep_reject:"):
        handle_admin_deposit_decision(call)
        
    elif data.startswith("admin_wd_approve:") or data.startswith("admin_wd_reject:"):
        handle_admin_withdraw_decision(call)

    elif data.startswith("admin_pur_approve:") or data.startswith("admin_pur_reject:"):
        handle_admin_purchase_decision(call)

# ==========================================
# Registration Step Handlers
# ==========================================
def process_reg_name(message):
    chat_id = message.chat.id
    if message.text and (message.text.startswith('/') or message.text == "❌ លុបចោល (Cancel)"):
        return # Handled by command or button
    if chat_id not in REG_SESSIONS:
        return
    
    REG_SESSIONS[chat_id]['name'] = message.text.strip()
    msg = bot.send_message(chat_id, "📱 សូមបញ្ចូល **លេខទូរស័ព្ទ** របស់អ្នក៖", parse_mode="Markdown", reply_markup=get_cancel_markup())
    bot.register_next_step_handler(msg, process_reg_phone)

def process_reg_phone(message):
    chat_id = message.chat.id
    if message.text and (message.text.startswith('/') or message.text == "❌ លុបចោល (Cancel)"):
        return
    if chat_id not in REG_SESSIONS:
        return

    REG_SESSIONS[chat_id]['phone'] = message.text.strip()
    
    # If New Customer, ask for referral code. If Old, complete immediately.
    if REG_SESSIONS[chat_id].get('customer_type') == 'new':
        msg = bot.send_message(
            chat_id, 
            "🔗 សូមបញ្ចូល **លេខកូដណែនាំ** (Referral Code) ប្រសិនបើមាន៖\n*(ប្រសិនបើគ្មានទេ សូមចុចប៊ូតុងរំលង ឬវាយពាក្យ 'skip' / 'គ្មាន')*", 
            parse_mode="Markdown", 
            reply_markup=get_skip_markup()
        )
        bot.register_next_step_handler(msg, process_reg_ref)
    else:
        REG_SESSIONS[chat_id]['referred_by'] = None
        complete_registration(chat_id)

def process_reg_ref(message):
    chat_id = message.chat.id
    if message.text and (message.text.startswith('/') or message.text == "❌ លុបចោល (Cancel)"):
        return
    if chat_id not in REG_SESSIONS:
        return

    input_text = message.text.strip()
    if input_text.lower() in ['skip', 'no', 'none', 'គ្មាន', 'រំលង']:
        REG_SESSIONS[chat_id]['referred_by'] = None
        complete_registration(chat_id)
        return

    # Check if referral code exists in DB
    referrer = db_query_one("SELECT * FROM users WHERE ref_code = ?", (input_text,))
    if referrer:
        REG_SESSIONS[chat_id]['referred_by'] = referrer['ref_code']
        complete_registration(chat_id)
    else:
        msg = bot.send_message(
            chat_id, 
            "⚠️ **លេខកូដណែនាំមិនត្រឹមត្រូវទេ!** សូមបញ្ចូលម្ដងទៀត ឬចុចប៊ូតុងរំលងខាងក្រោម៖", 
            parse_mode="Markdown", 
            reply_markup=get_skip_markup()
        )
        bot.register_next_step_handler(msg, process_reg_ref)

def complete_registration(chat_id):
    if chat_id not in REG_SESSIONS:
        return
    
    session = REG_SESSIONS[chat_id]
    name = session.get('name')
    phone = session.get('phone')
    customer_type = session.get('customer_type')
    referred_by = session.get('referred_by')

    # Generate credentials
    account_number = generate_account_number()
    ref_code = generate_ref_code()
    password = generate_password()

    # Save User
    user_id = db_execute(
        """INSERT INTO users (account_number, name, phone, ref_code, referred_by, password, customer_type, telegram_id) 
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (account_number, name, phone, ref_code, referred_by, password, customer_type, None)
    )

    # Process Referral Bonus ($1.00 for referrer)
    referrer_notified = False
    if referred_by:
        referrer = db_query_one("SELECT * FROM users WHERE ref_code = ?", (referred_by,))
        if referrer:
            db_execute("UPDATE users SET balance = balance + 1.00 WHERE id = ?", (referrer['id'],))
            
            # Notify Referrer
            if referrer['telegram_id']:
                try:
                    ref_notif_text = (
                        "🎉 **ទទួលបានប្រាក់រង្វាន់ណែនាំ!**\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        f"👤 គណនី៖ **{name}** បានចុះឈ្មោះដោយប្រើប្រាស់កូដរបស់អ្នក។\n"
                        "💰 គណនីរបស់អ្នកទទួលបានបន្ថែម៖ **$1.00** 🎁\n"
                        "━━━━━━━━━━━━━━━━━━"
                    )
                    bot.send_message(referrer['telegram_id'], ref_notif_text, parse_mode="Markdown")
                    referrer_notified = True
                except Exception:
                    pass

    # Display Registration Success
    bonus_rate = 20
    if customer_type == 'new':
        if referred_by:
            bonus_rate = 30 # 20% default + 10% referral
        else:
            bonus_rate = 20
    else:
        bonus_rate = 13

    success_text = (
        "🎉 **ការចុះឈ្មោះត្រូវបានជោគជ័យ!**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💳 **លេខកូដអាខោន៖** `{account_number}`\n"
        f"🆔 **ID គណនី៖** `{user_id}`\n"
        f"🔑 **លេខកូដសម្ងាត់៖** `{password}`\n"
        f"🔗 **លេខកូដណែនាំរបស់អ្នក៖** `{ref_code}`\n"
        f"🎁 **ប្រាក់បន្ថែមលើការដាក់លុយ៖** `{bonus_rate}%`\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "⚠️ *សូមរក្សាទុកព័ត៌មានខាងលើនេះឱ្យបានល្អសម្រាប់ចូលប្រើប្រាស់។*"
    )
    
    markup = types.InlineKeyboardMarkup()
    btn_login = types.InlineKeyboardButton("🔓 ចូលគណនី (Log In)", callback_data="login_start")
    markup.add(btn_login)

    bot.send_message(chat_id, success_text, parse_mode="Markdown", reply_markup=markup)
    REG_SESSIONS.pop(chat_id, None)

# ==========================================
# Login Step Handlers
# ==========================================
def process_login_acc(message):
    chat_id = message.chat.id
    if message.text and (message.text.startswith('/') or message.text == "❌ លុបចោល (Cancel)"):
        return
    if chat_id not in LOGIN_SESSIONS:
        return

    LOGIN_SESSIONS[chat_id]['account_number'] = message.text.strip()
    msg = bot.send_message(chat_id, "🔑 សូមបញ្ចូល **លេខកូដសម្ងាត់** (Password) របស់អ្នក៖", parse_mode="Markdown", reply_markup=get_cancel_markup())
    bot.register_next_step_handler(msg, process_login_pass)

def process_login_pass(message):
    chat_id = message.chat.id
    if message.text and (message.text.startswith('/') or message.text == "❌ លុបចោល (Cancel)"):
        return
    if chat_id not in LOGIN_SESSIONS:
        return

    password = message.text.strip()
    acc_num = LOGIN_SESSIONS[chat_id].get('account_number')

    user = db_query_one("SELECT * FROM users WHERE account_number = ? AND password = ?", (acc_num, password))
    
    if user:
        # Clear this telegram_id from any other accounts to maintain uniqueness
        db_execute("UPDATE users SET telegram_id = NULL WHERE telegram_id = ? AND id != ?", (chat_id, user['id']))
        # Update telegram_id if it changed
        if user['telegram_id'] != chat_id:
            db_execute("UPDATE users SET telegram_id = ? WHERE id = ?", (chat_id, user['id']))
            
        USER_SESSIONS[chat_id] = user['id']
        bot.send_message(chat_id, "✅ **ចូលគណនីបានជោគជ័យ!**", parse_mode="Markdown")
        
        # Refresh user dict to get updated telegram_id
        user = db_query_one("SELECT * FROM users WHERE id = ?", (user['id'],))
        send_dashboard(chat_id, user)
    else:
        fail_markup = types.InlineKeyboardMarkup()
        btn_retry = types.InlineKeyboardButton("🔓 ព្យាយាមម្ដងទៀត", callback_data="login_start")
        btn_home = types.InlineKeyboardButton("🏠 ត្រឡប់ទៅទំព័រដើម", callback_data="go_home")
        fail_markup.add(btn_retry, btn_home)
        bot.send_message(chat_id, "❌ **លេខកូដអាខោន ឬលេខសម្ងាត់មិនត្រឹមត្រូវទេ!**", parse_mode="Markdown", reply_markup=fail_markup)

    LOGIN_SESSIONS.pop(chat_id, None)

def process_forgot_phone(message):
    chat_id = message.chat.id
    if message.text and (message.text.startswith('/') or message.text == "❌ លុបចោល (Cancel)"):
        return
    if chat_id not in FORGOT_SESSIONS:
        return

    phone = message.text.strip()
    user = db_query_one("SELECT * FROM users WHERE phone = ?", (phone,))
    
    if user:
        new_password = generate_password()
        db_execute("UPDATE users SET password = ? WHERE id = ?", (new_password, user['id']))
        
        success_text = (
            "🔑 **ការផ្លាស់ប្តូរលេខសម្ងាត់ថ្មីបានជោគជ័យ!**\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"👤 ឈ្មោះ៖ **{user['name']}**\n"
            f"💳 **លេខកូដអាខោន៖** `{user['account_number']}`\n"
            f"🔑 **លេខកូដសម្ងាត់ថ្មី៖** `{new_password}`\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "⚠️ *សូមរក្សាទុកលេខសម្ងាត់ថ្មីនេះឱ្យបានល្អសម្រាប់ចូលប្រើប្រាស់។*"
        )
        
        markup = types.InlineKeyboardMarkup()
        btn_login = types.InlineKeyboardButton("🔓 ចូលគណនី (Log In)", callback_data="login_start")
        markup.add(btn_login)
        
        bot.send_message(chat_id, success_text, parse_mode="Markdown", reply_markup=markup)
    else:
        fail_markup = types.InlineKeyboardMarkup()
        btn_retry = types.InlineKeyboardButton("🔄 ព្យាយាមម្ដងទៀត", callback_data="forgot_pass_start")
        btn_home = types.InlineKeyboardButton("🏠 ត្រឡប់ទៅទំព័រដើម", callback_data="go_home")
        fail_markup.add(btn_retry, btn_home)
        bot.send_message(chat_id, "❌ **រកមិនឃើញលេខទូរស័ព្ទនេះក្នុងប្រព័ន្ធឡើយ!**", parse_mode="Markdown", reply_markup=fail_markup)

    FORGOT_SESSIONS.pop(chat_id, None)

# ==========================================
# Dashboard View Generator
# ==========================================
def send_dashboard(chat_id, user):
    # Calculate bonus rate
    bonus_rate = 20
    if user['customer_type'] == 'new':
        if user['referred_by']:
            bonus_rate = 30
        else:
            bonus_rate = 20
    else:
        bonus_rate = 13

    dash_text = (
        "🏦 **បន្ទះគ្រប់គ្រងគណនីផ្ទាល់ខ្លួន (Dashboard)**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👤 **ឈ្មោះ៖** {user['name']}\n"
        f"📱 **លេខទូរស័ព្ទ៖** {user['phone']}\n"
        f"💳 **លេខកូដអាខោន៖** `{user['account_number']}`\n"
        f"🆔 **ID គណនី៖** `{user['id']}`\n"
        f"🔑 **លេខកូដសម្ងាត់៖** `{user['password']}`\n"
        f"🔗 **លេខកូដណែនាំ៖** `{user['ref_code']}`\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💰 **សមតុល្យទឹកប្រាក់៖** `${user['balance']:.2f}`\n"
        f"🎁 **ភាគរយប្រាក់បន្ថែម៖** `{bonus_rate}%`\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(chat_id, dash_text, parse_mode="Markdown", reply_markup=get_dashboard_markup())

# ==========================================
# Deposit Request Step Handlers
# ==========================================
def process_deposit_pass_confirm(message):
    chat_id = message.chat.id
    if message.text and (message.text.startswith('/') or message.text == "❌ លុបចោល (Cancel)"):
        return
    user = get_logged_in_user(chat_id)
    if not user or chat_id not in DEP_SESSIONS:
        return

    password = message.text.strip()
    if password == user['password']:
        msg = bot.send_message(chat_id, "💰 សូមបញ្ចូល **ចំនួនទឹកប្រាក់** ដែលចង់ដាក់ ($)៖", parse_mode="Markdown", reply_markup=get_cancel_markup())
        bot.register_next_step_handler(msg, process_deposit_amount)
    else:
        bot.send_message(chat_id, "❌ **លេខសម្ងាត់មិនត្រឹមត្រូវទេ!** ការស្នើដាក់លុយត្រូវបានលុបចោល។", parse_mode="Markdown")
        DEP_SESSIONS.pop(chat_id, None)
        send_dashboard(chat_id, user)

def process_deposit_amount(message):
    chat_id = message.chat.id
    if message.text and (message.text.startswith('/') or message.text == "❌ លុបចោល (Cancel)"):
        return
    user = get_logged_in_user(chat_id)
    if not user or chat_id not in DEP_SESSIONS:
        return

    try:
        amount = float(message.text.strip())
        if amount <= 0:
            raise ValueError
        
        DEP_SESSIONS[chat_id]['amount'] = amount

        # Send KHQR to user
        instructions = (
            f"💵 **សូមបាញ់ប្រាក់ចំនួន៖** `${amount:.2f}`\n\n"
            "👉 សូមស្កេនរូបភាព KHQR របស់ Admin ខាងក្រោម រួចធ្វើការបាញ់ប្រាក់។\n"
            "📸 *បន្ទាប់ពីផ្ទេររួចរាល់ សូមផ្ញើរូបភាពវិក្កយបត្រ (Screenshot) មកកាន់ទីនេះ ដើម្បីឱ្យ Admin ផ្ទៀងផ្ទាត់។*"
        )
        
        # Try to send image, if not found, send text instructions
        if os.path.exists(ADMIN_KHQR_PATH):
            with open(ADMIN_KHQR_PATH, 'rb') as photo:
                bot.send_photo(chat_id, photo, caption=instructions, parse_mode="Markdown", reply_markup=get_cancel_markup())
        else:
            bot.send_message(chat_id, instructions + "\n\n*(រូបភាព KHQR មិនទាន់បានដាក់បញ្ចូលដោយ Admin ឡើយ)*", parse_mode="Markdown", reply_markup=get_cancel_markup())
            
        bot.register_next_step_handler(message, process_deposit_screenshot)
    except ValueError:
        msg = bot.send_message(chat_id, "⚠️ **ចំនួនទឹកប្រាក់មិនត្រឹមត្រូវទេ!** សូមបញ្ចូលចំនួនទឹកប្រាក់ជាលេខ (ឧទាហរណ៍៖ 10)៖", parse_mode="Markdown", reply_markup=get_cancel_markup())
        bot.register_next_step_handler(msg, process_deposit_amount)

def process_deposit_screenshot(message):
    chat_id = message.chat.id
    if message.text and (message.text.startswith('/') or message.text == "❌ លុបចោល (Cancel)"):
        return
    user = get_logged_in_user(chat_id)
    if not user or chat_id not in DEP_SESSIONS:
        return

    if message.photo:
        file_id = message.photo[-1].file_id
        amount = DEP_SESSIONS[chat_id]['amount']

        # Calculate Bonus
        bonus_rate = 20
        if user['customer_type'] == 'new':
            if user['referred_by']:
                bonus_rate = 30
            else:
                bonus_rate = 20
        else:
            bonus_rate = 13
        
        bonus_amount = amount * (bonus_rate / 100.0)

        # Insert Pending Deposit
        dep_id = db_execute(
            "INSERT INTO deposits (user_id, amount, bonus_amount, status, screenshot_file_id) VALUES (?, ?, ?, 'pending', ?)",
            (user['id'], amount, bonus_amount, file_id)
        )

        bot.send_message(chat_id, "📥 **ការស្នើដាក់លុយទទួលបានជោគជ័យ!**\nសំណើរបស់អ្នកកំពុងស្ថិតក្នុងការត្រួតពិនិត្យពី Admin។", parse_mode="Markdown")
        
        # Notify Admin
        admin_chat_id = get_admin_chat_id()
        if admin_chat_id:
            try:
                admin_text = (
                    "🚨 **សំណើដាក់លុយថ្មី! (New Deposit Request)**\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    f"👤 ឈ្មោះ៖ **{user['name']}** (ID: `{user['id']}`)\n"
                    f"💳 លេខគណនី៖ `{user['account_number']}`\n"
                    f"💰 ចំនួនទឹកប្រាក់៖ **${amount:.2f}**\n"
                    f"🎁 ប្រាក់បន្ថែម៖ `{bonus_rate}%` (**+${bonus_amount:.2f}**)\n"
                    f"💵 ទឹកប្រាក់ត្រូវបញ្ចូលសរុប៖ **${(amount + bonus_amount):.2f}**\n"
                    "━━━━━━━━━━━━━━━━━━"
                )
                
                admin_markup = types.InlineKeyboardMarkup(row_width=2)
                btn_approve = types.InlineKeyboardButton("យល់ព្រម Approve ✅", callback_data=f"admin_dep_approve:{dep_id}")
                btn_reject = types.InlineKeyboardButton("បដិសេធ Reject ❌", callback_data=f"admin_dep_reject:{dep_id}")
                admin_markup.add(btn_approve, btn_reject)

                bot.send_photo(admin_chat_id, file_id, caption=admin_text, parse_mode="Markdown", reply_markup=admin_markup)
            except Exception as e:
                print(f"Error notifying admin: {e}")
        else:
            print("Warning: ADMIN_CHAT_ID is not configured or invalid.")

        DEP_SESSIONS.pop(chat_id, None)
        send_dashboard(chat_id, user)
    else:
        msg = bot.send_message(chat_id, "⚠️ **មិនមែនជារូបភាពទេ!** សូមផ្ញើរូបភាពវិក្កយបត្រ (Screenshot) នៃការផ្ទេរប្រាក់របស់អ្នក៖", parse_mode="Markdown", reply_markup=get_cancel_markup())
        bot.register_next_step_handler(msg, process_deposit_screenshot)

# ==========================================
# Withdraw Request Step Handlers
# ==========================================
def process_withdraw_pass_confirm(message):
    chat_id = message.chat.id
    if message.text and (message.text.startswith('/') or message.text == "❌ លុបចោល (Cancel)"):
        return
    user = get_logged_in_user(chat_id)
    if not user or chat_id not in WITHDRAW_SESSIONS:
        return

    password = message.text.strip()
    if password == user['password']:
        msg = bot.send_message(
            chat_id, 
            f"💰 សូមបញ្ចូល **ចំនួនទឹកប្រាក់** ដែលចង់ដក ($)\n*(សមតុល្យបច្ចុប្បន្ន៖ `${user['balance']:.2f}`)*៖", 
            parse_mode="Markdown", 
            reply_markup=get_cancel_markup()
        )
        bot.register_next_step_handler(msg, process_withdraw_amount)
    else:
        bot.send_message(chat_id, "❌ **លេខសម្ងាត់មិនត្រឹមត្រូវទេ!** ការស្នើដកលុយត្រូវបានលុបចោល។", parse_mode="Markdown")
        WITHDRAW_SESSIONS.pop(chat_id, None)
        send_dashboard(chat_id, user)

def process_withdraw_amount(message):
    chat_id = message.chat.id
    if message.text and (message.text.startswith('/') or message.text == "❌ លុបចោល (Cancel)"):
        return
    user = get_logged_in_user(chat_id)
    if not user or chat_id not in WITHDRAW_SESSIONS:
        return

    try:
        amount = float(message.text.strip())
        if amount <= 0:
            raise ValueError
        
        if amount > user['balance']:
            msg = bot.send_message(
                chat_id, 
                f"⚠️ **សមតុល្យមិនគ្រប់គ្រាន់ទេ!** សូមបញ្ចូលទឹកប្រាក់ស្នើសុំម្ដងទៀត (មិនលើសពី `${user['balance']:.2f}`)៖", 
                parse_mode="Markdown", 
                reply_markup=get_cancel_markup()
            )
            bot.register_next_step_handler(msg, process_withdraw_amount)
            return

        WITHDRAW_SESSIONS[chat_id]['amount'] = amount

        msg = bot.send_message(
            chat_id, 
            "📷 សូមផ្ញើ **រូបភាព KHQR របស់លោកអ្នក** (User KHQR) ដើម្បីឱ្យ Admin ផ្ទេរប្រាក់ជូន៖", 
            parse_mode="Markdown", 
            reply_markup=get_cancel_markup()
        )
        bot.register_next_step_handler(msg, process_withdraw_khqr)
    except ValueError:
        msg = bot.send_message(chat_id, "⚠️ **ចំនួនទឹកប្រាក់មិនត្រឹមត្រូវទេ!** សូមបញ្ចូលចំនួនទឹកប្រាក់ជាលេខ (ឧទាហរណ៍៖ 10)៖", parse_mode="Markdown", reply_markup=get_cancel_markup())
        bot.register_next_step_handler(msg, process_withdraw_amount)

def process_withdraw_khqr(message):
    chat_id = message.chat.id
    if message.text and (message.text.startswith('/') or message.text == "❌ លុបចោល (Cancel)"):
        return
    user = get_logged_in_user(chat_id)
    if not user or chat_id not in WITHDRAW_SESSIONS:
        return

    if message.photo:
        file_id = message.photo[-1].file_id
        amount = WITHDRAW_SESSIONS[chat_id]['amount']

        # Insert Pending Withdrawal
        wd_id = db_execute(
            "INSERT INTO withdrawals (user_id, amount, status, khqr_file_id) VALUES (?, ?, 'pending', ?)",
            (user['id'], amount, file_id)
        )

        bot.send_message(chat_id, "📥 **ការស្នើដកលុយទទួលបានជោគជ័យ!**\nសំណើរបស់អ្នកកំពុងស្ថិតក្នុងការត្រួតពិនិត្យពី Admin។", parse_mode="Markdown")
        
        # Notify Admin
        admin_chat_id = get_admin_chat_id()
        if admin_chat_id:
            try:
                admin_text = (
                    "🚨 **សំណើដកលុយថ្មី! (New Withdrawal Request)**\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    f"👤 ឈ្មោះ៖ **{user['name']}** (ID: `{user['id']}`)\n"
                    f"💳 លេខគណនី៖ `{user['account_number']}`\n"
                    f"💸 ចំនួនទឹកប្រាក់ចង់ដក៖ **${amount:.2f}**\n"
                    "━━━━━━━━━━━━━━━━━━"
                )
                
                admin_markup = types.InlineKeyboardMarkup(row_width=2)
                btn_approve = types.InlineKeyboardButton("យល់ព្រម Approve ✅", callback_data=f"admin_wd_approve:{wd_id}")
                btn_reject = types.InlineKeyboardButton("បដិសេធ Reject ❌", callback_data=f"admin_wd_reject:{wd_id}")
                admin_markup.add(btn_approve, btn_reject)

                bot.send_photo(admin_chat_id, file_id, caption=admin_text, parse_mode="Markdown", reply_markup=admin_markup)
            except Exception as e:
                print(f"Error notifying admin: {e}")
        else:
            print("Warning: ADMIN_CHAT_ID is not configured or invalid.")

        WITHDRAW_SESSIONS.pop(chat_id, None)
        send_dashboard(chat_id, user)
    else:
        msg = bot.send_message(chat_id, "⚠️ **មិនមែនជារូបភាពទេ!** សូមផ្ញើរូបភាព KHQR របស់អ្នក៖", parse_mode="Markdown", reply_markup=get_cancel_markup())
        bot.register_next_step_handler(msg, process_withdraw_khqr)

def process_purchase_pass_confirm(message):
    chat_id = message.chat.id
    if message.text and (message.text.startswith('/') or message.text == "❌ លុបចោល (Cancel)"):
        return
    user = get_logged_in_user(chat_id)
    if not user or chat_id not in BUY_SESSIONS:
        return

    password = message.text.strip()
    if password == user['password']:
        session = BUY_SESSIONS[chat_id]
        prod_name = session['product_name']
        price = session['price']
        
        # Check balance again
        user = db_query_one("SELECT * FROM users WHERE id = ?", (user['id'],))
        if user['balance'] < price:
            bot.send_message(chat_id, "❌ **សមតុល្យមិនគ្រប់គ្រាន់ទេ!**", parse_mode="Markdown")
            BUY_SESSIONS.pop(chat_id, None)
            send_dashboard(chat_id, user)
            return

        # Deduct balance
        new_balance = user['balance'] - price
        db_execute("UPDATE users SET balance = ? WHERE id = ?", (new_balance, user['id']))
        
        # Insert Purchase
        purchase_id = db_execute(
            "INSERT INTO purchases (user_id, product_name, price, status) VALUES (?, ?, ?, 'pending')",
            (user['id'], prod_name, price)
        )

        bot.send_message(chat_id, f"📥 **ការបញ្ជាទិញ {prod_name} ទទួលបានជោគជ័យ!**\nសំណើរបស់អ្នកកំពុងស្ថិតក្នុងការត្រួតពិនិត្យពី Admin។", parse_mode="Markdown")
        
        # Notify Admin
        admin_chat_id = get_admin_chat_id()
        if admin_chat_id:
            try:
                admin_text = (
                    "🚨 **សំណើទិញទំនិញថ្មី! (New Purchase Request)**\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    f"👤 ឈ្មោះ៖ **{user['name']}** (ID: `{user['id']}`)\n"
                    f"💳 លេខគណនី៖ `{user['account_number']}`\n"
                    f"🛍️ ផលិតផល៖ **{prod_name}**\n"
                    f"💰 តម្លៃ៖ **${price:.2f}**\n"
                    "━━━━━━━━━━━━━━━━━━"
                )
                
                admin_markup = types.InlineKeyboardMarkup(row_width=2)
                btn_approve = types.InlineKeyboardButton("យល់ព្រម Approve ✅", callback_data=f"admin_pur_approve:{purchase_id}")
                btn_reject = types.InlineKeyboardButton("បដិសេធ Reject ❌", callback_data=f"admin_pur_reject:{purchase_id}")
                admin_markup.add(btn_approve, btn_reject)

                bot.send_message(admin_chat_id, admin_text, parse_mode="Markdown", reply_markup=admin_markup)
            except Exception as e:
                print(f"Error notifying admin of purchase: {e}")
        else:
            print("Warning: ADMIN_CHAT_ID is not configured or invalid.")

        BUY_SESSIONS.pop(chat_id, None)
        # Refresh user data for dashboard
        user = db_query_one("SELECT * FROM users WHERE id = ?", (user['id'],))
        send_dashboard(chat_id, user)
    else:
        bot.send_message(chat_id, "❌ **លេខសម្ងាត់មិនត្រឹមត្រូវទេ!** ការបញ្ជាទិញត្រូវបានលុបចោល។", parse_mode="Markdown")
        BUY_SESSIONS.pop(chat_id, None)
        send_dashboard(chat_id, user)

# ==========================================
# Admin Decision Handler (Deposits)
# ==========================================
def handle_admin_deposit_decision(call):
    chat_id = call.message.chat.id
    data = call.data
    
    # Check if admin
    admin_chat_id = get_admin_chat_id()
    if chat_id != admin_chat_id:
        return
        
    parts = data.split(":")
    action = parts[0]
    dep_id = int(parts[1])

    deposit = db_query_one("SELECT * FROM deposits WHERE id = ?", (dep_id,))
    if not deposit:
        bot.edit_message_caption("❌ រកមិនឃើញសំណើនេះឡើយ។", chat_id, call.message.message_id)
        return

    if deposit['status'] != 'pending':
        bot.edit_message_caption(f"⚠️ សំណើនេះត្រូវបានដោះស្រាយរួចរាល់ហើយ! (Status: {deposit['status']})", chat_id, call.message.message_id)
        return

    user = db_query_one("SELECT * FROM users WHERE id = ?", (deposit['user_id'],))
    if not user:
        bot.edit_message_caption("❌ រកមិនឃើញគណនីអ្នកប្រើប្រាស់ឡើយ។", chat_id, call.message.message_id)
        return

    if action == "admin_dep_approve":
        # Calculate new balance
        added_amount = deposit['amount'] + deposit['bonus_amount']
        new_balance = user['balance'] + added_amount
        
        # Update User Balance and Deposit Status
        db_execute("UPDATE users SET balance = ? WHERE id = ?", (new_balance, user['id']))
        db_execute("UPDATE deposits SET status = 'approved' WHERE id = ?", (dep_id,))

        # Update Admin's balance (double-entry addition of physical deposit cash if client is not the Admin)
        admin_info_str = ""
        if user['id'] != 1:
            admin_user = db_query_one("SELECT * FROM users WHERE id = 1")
            if admin_user:
                new_admin_balance = admin_user['balance'] + deposit['amount']
                db_execute("UPDATE users SET balance = ? WHERE id = 1", (new_admin_balance,))
                admin_info_str = f"👑 **សមតុល្យ Admin ៖** `${new_admin_balance:.2f}`\n"

        # Update Admin Message
        approved_caption = (
            "✅ **សំណើដាក់លុយត្រូវបានយល់ព្រម!**\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"👤 ឈ្មោះ៖ **{user['name']}** (ID: `{user['id']}`)\n"
            f"💳 លេខគណនី៖ `{user['account_number']}`\n"
            f"💰 ចំនួនទឹកប្រាក់៖ **${deposit['amount']:.2f}**\n"
            f"🎁 ប្រាក់បន្ថែម៖ **+${deposit['bonus_amount']:.2f}**\n"
            f"💵 ទឹកប្រាក់សរុបបញ្ចូល៖ **${added_amount:.2f}**\n"
            f"📈 សមតុល្យគណនីថ្មី៖ **${new_balance:.2f}**\n"
            f"{admin_info_str}"
            "━━━━━━━━━━━━━━━━━━"
        )
        bot.edit_message_caption(approved_caption, chat_id, call.message.message_id)

        # Notify User
        if user['telegram_id']:
            try:
                user_notif = (
                    "🔔 **ការដាក់លុយរបស់អ្នកត្រូវបានយល់ព្រម!**\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    f"💵 ទឹកប្រាក់ដែលបានដាក់៖ **${deposit['amount']:.2f}**\n"
                    f"🎁 ប្រាក់បន្ថែមទទួលបាន៖ **${deposit['bonus_amount']:.2f}**\n"
                    f"💰 សមតុល្យសរុបបច្ចុប្បន្ន៖ **${new_balance:.2f}**\n"
                    "━━━━━━━━━━━━━━━━━━"
                )
                bot.send_message(user['telegram_id'], user_notif, parse_mode="Markdown")
            except Exception:
                pass

    elif action == "admin_dep_reject":
        # Update Deposit Status
        db_execute("UPDATE deposits SET status = 'rejected' WHERE id = ?", (dep_id,))

        # Update Admin Message
        rejected_caption = (
            "❌ **សំណើដាក់លុយត្រូវបានបដិសេធ!**\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"👤 ឈ្មោះ៖ **{user['name']}** (ID: `{user['id']}`)\n"
            f"💳 លេខគណនី៖ `{user['account_number']}`\n"
            f"💰 ចំនួនទឹកប្រាក់ស្នើ៖ **${deposit['amount']:.2f}**\n"
            "━━━━━━━━━━━━━━━━━━"
        )
        bot.edit_message_caption(rejected_caption, chat_id, call.message.message_id)

        # Notify User
        if user['telegram_id']:
            try:
                user_notif = (
                    "❌ **ការស្នើដាក់លុយរបស់អ្នកត្រូវបានបដិសេធ!**\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    f"💵 ទឹកប្រាក់៖ **${deposit['amount']:.2f}**\n"
                    "⚠️ សូមទំនាក់ទំនងទៅកាន់ Admin សម្រាប់ព័ត៌មានលម្អិត។\n"
                    "━━━━━━━━━━━━━━━━━━"
                )
                bot.send_message(user['telegram_id'], user_notif, parse_mode="Markdown")
            except Exception:
                pass

# ==========================================
# Admin Decision Handler (Withdrawals)
# ==========================================
def handle_admin_withdraw_decision(call):
    chat_id = call.message.chat.id
    data = call.data
    
    # Check if admin
    admin_chat_id = get_admin_chat_id()
    if chat_id != admin_chat_id:
        return
        
    parts = data.split(":")
    action = parts[0]
    wd_id = int(parts[1])

    withdraw = db_query_one("SELECT * FROM withdrawals WHERE id = ?", (wd_id,))
    if not withdraw:
        bot.edit_message_caption("❌ រកមិនឃើញសំណើនេះឡើយ។", chat_id, call.message.message_id)
        return

    if withdraw['status'] != 'pending':
        bot.edit_message_caption(f"⚠️ សំណើនេះត្រូវបានដោះស្រាយរួចរាល់ហើយ! (Status: {withdraw['status']})", chat_id, call.message.message_id)
        return

    user = db_query_one("SELECT * FROM users WHERE id = ?", (withdraw['user_id'],))
    if not user:
        bot.edit_message_caption("❌ រកមិនឃើញគណនីអ្នកប្រើប្រាស់ឡើយ។", chat_id, call.message.message_id)
        return

    if action == "admin_wd_approve":
        # Check if balance is sufficient
        if user['balance'] < withdraw['amount']:
            bot.edit_message_caption(
                f"⚠️ **សមតុល្យគណនីមិនគ្រប់គ្រាន់សម្រាប់កាត់ទេ!**\n"
                f"គណនីមាន៖ `${user['balance']:.2f}` | ស្នើដក៖ `${withdraw['amount']:.2f}`", 
                chat_id, 
                call.message.message_id
            )
            return

        new_balance = user['balance'] - withdraw['amount']
        
        # Update User Balance and Withdrawal Status
        db_execute("UPDATE users SET balance = ? WHERE id = ?", (new_balance, user['id']))
        db_execute("UPDATE withdrawals SET status = 'approved' WHERE id = ?", (wd_id,))

        # Deduct from Admin's balance (if client is not the Admin)
        admin_info_str = ""
        if user['id'] != 1:
            admin_user = db_query_one("SELECT * FROM users WHERE id = 1")
            if admin_user:
                new_admin_balance = admin_user['balance'] - withdraw['amount']
                db_execute("UPDATE users SET balance = ? WHERE id = 1", (new_admin_balance,))
                admin_info_str = f"👑 **សមតុល្យ Admin ៖** `${new_admin_balance:.2f}`\n"

        # Update Admin Message
        approved_caption = (
            "✅ **សំណើដកលុយត្រូវបានយល់ព្រម និងផ្ទេររួចរាល់!**\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"👤 ឈ្មោះ៖ **{user['name']}** (ID: `{user['id']}`)\n"
            f"💳 លេខគណនី៖ `{user['account_number']}`\n"
            f"💸 ចំនួនទឹកប្រាក់ដក៖ **${withdraw['amount']:.2f}**\n"
            f"📉 សមតុល្យគណនីនៅសល់៖ **${new_balance:.2f}**\n"
            f"{admin_info_str}"
            "━━━━━━━━━━━━━━━━━━"
        )
        bot.edit_message_caption(approved_caption, chat_id, call.message.message_id)

        # Notify User
        if user['telegram_id']:
            try:
                user_notif = (
                    "🔔 **ការស្នើដកលុយរបស់អ្នកត្រូវបានយល់ព្រម និងផ្ទេររួចរាល់!**\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    f"💸 ចំនួនទឹកប្រាក់ដក៖ **${withdraw['amount']:.2f}**\n"
                    f"💰 សមតុល្យគណនីនៅសល់៖ **${new_balance:.2f}**\n"
                    "━━━━━━━━━━━━━━━━━━"
                )
                bot.send_message(user['telegram_id'], user_notif, parse_mode="Markdown")
            except Exception:
                pass

    elif action == "admin_wd_reject":
        # Update Withdrawal Status
        db_execute("UPDATE withdrawals SET status = 'rejected' WHERE id = ?", (wd_id,))

        # Update Admin Message
        rejected_caption = (
            "❌ **សំណើដកលុយត្រូវបានបដិសេធ!**\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"👤 ឈ្មោះ៖ **{user['name']}** (ID: `{user['id']}`)\n"
            f"💳 លេខគណនី៖ `{user['account_number']}`\n"
            f"💸 ចំនួនទឹកប្រាក់ស្នើដក៖ **${withdraw['amount']:.2f}**\n"
            "━━━━━━━━━━━━━━━━━━"
        )
        bot.edit_message_caption(rejected_caption, chat_id, call.message.message_id)

        # Notify User
        if user['telegram_id']:
            try:
                user_notif = (
                    "❌ **ការស្នើដកលុយរបស់អ្នកត្រូវបានបដិសេធ!**\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    f"💸 ចំនួនទឹកប្រាក់ស្នើដក៖ **${withdraw['amount']:.2f}**\n"
                    "⚠️ សូមទំនាក់ទំនងទៅកាន់ Admin សម្រាប់ព័ត៌មានលម្អិត។\n"
                    "━━━━━━━━━━━━━━━━━━"
                )
                bot.send_message(user['telegram_id'], user_notif, parse_mode="Markdown")
            except Exception:
                pass

# ==========================================
# Admin Decision Handler (Purchases)
# ==========================================
def handle_admin_purchase_decision(call):
    chat_id = call.message.chat.id
    data = call.data
    
    # Check if admin
    admin_chat_id = get_admin_chat_id()
    if chat_id != admin_chat_id:
        return
        
    parts = data.split(":")
    action = parts[0]
    purchase_id = int(parts[1])

    purchase = db_query_one("SELECT * FROM purchases WHERE id = ?", (purchase_id,))
    if not purchase:
        bot.edit_message_text("❌ រកមិនឃើញសំណើទិញនេះឡើយ។", chat_id, call.message.message_id)
        return

    if purchase['status'] != 'pending':
        bot.edit_message_text(f"⚠️ សំណើទិញនេះត្រូវបានដោះស្រាយរួចរាល់ហើយ! (Status: {purchase['status']})", chat_id, call.message.message_id)
        return

    user = db_query_one("SELECT * FROM users WHERE id = ?", (purchase['user_id'],))
    if not user:
        bot.edit_message_text("❌ រកមិនឃើញគណនីអ្នកប្រើប្រាស់ឡើយ។", chat_id, call.message.message_id)
        return

    if action == "admin_pur_approve":
        # Get duration and details
        prod_key = None
        for key, details in PRODUCTS_DETAILS.items():
            if details['name'] == purchase['product_name']:
                prod_key = key
                break
                
        duration = 30
        desc = "ផលិតផលនឹងត្រូវប្រគល់ជូនលោកអ្នកក្នុងពេលឆាប់ៗនេះ។"
        img_path = None
        if prod_key:
            duration = PRODUCTS_DETAILS[prod_key]['duration_days']
            desc = PRODUCTS_DETAILS[prod_key]['description']
            img_path = PRODUCTS_DETAILS[prod_key]['image_path']

        # Update Purchase Status in DB
        import datetime
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db_execute(
            "UPDATE purchases SET status = 'approved', approved_at = ?, duration_days = ? WHERE id = ?",
            (now_str, duration, purchase_id)
        )

        # Update Admin's balance (double-entry addition of product price if client is not the Admin)
        admin_info_str = ""
        if user['id'] != 1:
            admin_user = db_query_one("SELECT * FROM users WHERE id = 1")
            if admin_user:
                new_admin_balance = admin_user['balance'] + purchase['price']
                db_execute("UPDATE users SET balance = ? WHERE id = 1", (new_admin_balance,))
                admin_info_str = f"👑 **សមតុល្យ Admin ៖** `${new_admin_balance:.2f}`\n"

        # Update Admin Message
        approved_text = (
            "✅ **សំណើទិញទំនិញត្រូវបានយល់ព្រម!**\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"👤 ឈ្មោះ៖ **{user['name']}** (ID: `{user['id']}`)\n"
            f"💳 លេខគណនី៖ `{user['account_number']}`\n"
            f"🛍️ ផលិតផល៖ **{purchase['product_name']}**\n"
            f"💰 តម្លៃ៖ **${purchase['price']:.2f}**\n"
            f"{admin_info_str}"
            "━━━━━━━━━━━━━━━━━━"
        )
        bot.edit_message_text(approved_text, chat_id, call.message.message_id, parse_mode="Markdown")

        # Notify User
        if user['telegram_id']:
            user_notif = (
                "🔔 **ការបញ្ជាទិញរបស់អ្នកត្រូវបានយល់ព្រម!**\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"🛍️ **ផលិតផល៖** {purchase['product_name']}\n"
                f"💰 **តម្លៃ៖** ${purchase['price']:.2f}\n"
                f"⏳ **រយៈពេលប្រើប្រាស់៖** ប្រើប្រាស់បានប្រហែល **{duration} ថ្ងៃ**\n"
                f"📝 **ព័ត៌មានលម្អិត៖** {desc}\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "📦 *ផលិតផលនឹងត្រូវប្រគល់ជូនលោកអ្នកក្នុងពេលឆាប់ៗនេះ។*"
            )
            try:
                import os
                if img_path and os.path.exists(img_path):
                    with open(img_path, 'rb') as photo:
                        bot.send_photo(user['telegram_id'], photo, caption=user_notif, parse_mode="Markdown")
                else:
                    bot.send_message(user['telegram_id'], user_notif, parse_mode="Markdown")
            except Exception as e:
                print(f"Error sending purchase approval message: {e}")

    elif action == "admin_pur_reject":
        # Refund user's balance
        new_balance = user['balance'] + purchase['price']
        db_execute("UPDATE users SET balance = ? WHERE id = ?", (new_balance, user['id']))
        db_execute("UPDATE purchases SET status = 'rejected' WHERE id = ?", (purchase_id,))

        # Update Admin Message
        rejected_text = (
            "❌ **សំណើទិញទំនិញត្រូវបានបដិសេធ (ប្រាក់ត្រូវបានបង្វិលសង)!**\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"👤 ឈ្មោះ៖ **{user['name']}** (ID: `{user['id']}`)\n"
            f"💳 លេខគណនី៖ `{user['account_number']}`\n"
            f"🛍️ ផលិតផល៖ **{purchase['product_name']}**\n"
            f"💰 តម្លៃ៖ **${purchase['price']:.2f}**\n"
            "━━━━━━━━━━━━━━━━━━"
        )
        bot.edit_message_text(rejected_text, chat_id, call.message.message_id, parse_mode="Markdown")

        # Notify User
        if user['telegram_id']:
            try:
                user_notif = (
                    "❌ **ការបញ្ជាទិញរបស់អ្នកត្រូវបានបដិសេធ!**\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    f"🛍️ ផលិតផល៖ **{purchase['product_name']}**\n"
                    f"💰 តម្លៃ៖ **${purchase['price']:.2f}**\n"
                    f"🔄 ទឹកប្រាក់ត្រូវបានបង្វិលចូលសមតុល្យគណនីរបស់អ្នកវិញរួចរាល់។\n"
                    "⚠️ សូមទំនាក់ទំនងទៅកាន់ Admin សម្រាប់ព័ត៌មានលម្អិត។\n"
                    "━━━━━━━━━━━━━━━━━━"
                )
                bot.send_message(user['telegram_id'], user_notif, parse_mode="Markdown")
            except Exception:
                pass

# ==========================================
# Background Product Expiry Alert Scheduler
# ==========================================
import threading
import time
import datetime

def check_product_alerts():
    # Wait 10 seconds before first run
    time.sleep(10)
    while True:
        try:
            # Query approved purchases that haven't received an alert
            purchases = db_query(
                """SELECT p.*, u.telegram_id, u.name as user_name 
                   FROM purchases p 
                   JOIN users u ON p.user_id = u.id 
                   WHERE p.status = 'approved' AND p.alert_sent = 0 AND p.approved_at IS NOT NULL"""
            )
            
            for p in purchases:
                try:
                    approved_time = datetime.datetime.strptime(p['approved_at'], "%Y-%m-%d %H:%M:%S")
                    duration = p['duration_days']
                    if not duration:
                        duration = 30
                    expiry_time = approved_time + datetime.timedelta(days=duration)
                    
                    now = datetime.datetime.now()
                    time_remaining = expiry_time - now
                    days_remaining = time_remaining.total_seconds() / 86400.0
                    
                    threshold = 3.0 if duration > 7 else 1.0
                    
                    if days_remaining <= threshold and days_remaining >= 0:
                        if p['telegram_id']:
                            alert_text = (
                                f"⚠️ **ការជូនដំណឹងអំពីផលិតផលជិតអស់! (Product Expiry Alert)**\n"
                                f"━━━━━━━━━━━━━━━━━━\n"
                                f"👤 ជម្រាបសួរលោកអ្នក៖ **{p['user_name']}**\n"
                                f"🧴 ផលិតផលរបស់អ្នក៖ **{p['product_name']}**\n"
                                f"📅 បានជាវកាលពី៖ `{p['approved_at']}`\n"
                                f"⏳ រយៈពេលប្រើប្រាស់៖ `{duration} ថ្ងៃ`\n"
                                f"⏰ ផលិតផលនេះ **ជិតដល់ថ្ងៃអស់ ឬផុតកំណត់** ក្នុងរយៈពេលប្រហែល៖ **{int(days_remaining) if days_remaining >= 1 else 0} ថ្ងៃទៀត**។\n"
                                f"🛍️ សូមធ្វើការជាវថ្មីម្តងទៀត ដើម្បីកុំឱ្យអាក់ខានការប្រើប្រាស់! 🥰\n"
                                f"━━━━━━━━━━━━━━━━━━"
                            )
                            bot.send_message(p['telegram_id'], alert_text, parse_mode="Markdown")
                        
                        db_execute("UPDATE purchases SET alert_sent = 1 WHERE id = ?", (p['id'],))
                except Exception as e:
                    print(f"Error processing alert for purchase {p['id']}: {e}")
        except Exception as e:
            print(f"Error in product alert scheduler: {e}")
        
        # Check every 10 minutes (600 seconds)
        time.sleep(600)

# Start alert checker thread
alert_thread = threading.Thread(target=check_product_alerts, daemon=True)
alert_thread.start()

# ==========================================
# Flask Web Server for Render Deployment (keep_alive)
# ==========================================
from flask import Flask
import logging

flask_app = Flask(__name__)

# Suppress Flask default request logging to keep console logs clean
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

@flask_app.route('/')
def home():
    return "Bot is healthy and running!"

def keep_alive():
    try:
        port = int(os.getenv("PORT", "8080"))
        print(f"Flask keep_alive server starting on port {port}...")
        flask_app.run(host='0.0.0.0', port=port)
    except Exception as e:
        print(f"Warning: Failed to start keep_alive server: {e}")

# ==========================================
# Application Startup
# ==========================================
if __name__ == '__main__':
    print("Initializing Database...")
    init_db()
    print("Database initialized successfully.")
    
    admin_id = get_admin_chat_id()
    if admin_id:
        print(f"Loaded Admin Chat ID: {admin_id}")
    else:
        print("Warning: ADMIN_CHAT_ID is not configured in .env yet.")
        
    # Start Flask keep_alive server on a background thread for Render
    health_thread = threading.Thread(target=keep_alive, daemon=True)
    health_thread.start()

    print("Telegram Bot is running...")
    # Start polling
    bot.infinity_polling()
