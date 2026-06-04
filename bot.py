import os
import random
import string
import sqlite3
import telebot
from telebot import types
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DB_PATH = os.getenv("DB_PATH", "bot.db")
ADMIN_KHQR_PATH = os.getenv("ADMIN_KHQR_PATH", "adminkhqr.png")

# Verify token
if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
    print("Error: TELEGRAM_BOT_TOKEN is not configured in .env file!")
    print("Please set your token and restart the bot.")
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

# Check if User is Logged In
def get_logged_in_user(chat_id):
    user_id = USER_SESSIONS.get(chat_id)
    if user_id:
        return db_query_one("SELECT * FROM users WHERE id = ?", (user_id,))
    return None

# ==========================================
# Telegram Keyboard Markup Creators
# ==========================================
def get_main_menu_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_login = types.InlineKeyboardButton("🔓 ចូលគណនី (Log In)", callback_data="menu_login")
    btn_register = types.InlineKeyboardButton("📝 បង្កើតគណនី (Register)", callback_data="menu_register")
    markup.add(btn_login, btn_register)
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
    btn_logout = types.InlineKeyboardButton("🚪 ចាកចេញ (Log Out)", callback_data="dash_logout")
    markup.add(btn_dep, btn_wd)
    markup.add(btn_logout)
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

    # Dashboard Logout
    elif data == "dash_logout":
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

    # Admin Callback Actions
    elif data.startswith("admin_dep_approve:") or data.startswith("admin_dep_reject:"):
        handle_admin_deposit_decision(call)
        
    elif data.startswith("admin_wd_approve:") or data.startswith("admin_wd_reject:"):
        handle_admin_withdraw_decision(call)

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
        (account_number, name, phone, ref_code, referred_by, password, customer_type, chat_id)
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
        USER_SESSIONS[chat_id] = user['id']
        bot.send_message(chat_id, "✅ **ចូលគណនីបានជោគជ័យ!**", parse_mode="Markdown")
        send_dashboard(chat_id, user)
        # Update telegram_id if it changed
        if user['telegram_id'] != chat_id:
            db_execute("UPDATE users SET telegram_id = ? WHERE id = ?", (chat_id, user['id']))
    else:
        fail_markup = types.InlineKeyboardMarkup()
        btn_retry = types.InlineKeyboardButton("🔓 ព្យាយាមម្ដងទៀត", callback_data="login_start")
        btn_home = types.InlineKeyboardButton("🏠 ត្រឡប់ទៅទំព័រដើម", callback_data="go_home")
        fail_markup.add(btn_retry, btn_home)
        bot.send_message(chat_id, "❌ **លេខកូដអាខោន ឬលេខសម្ងាត់មិនត្រឹមត្រូវទេ!**", parse_mode="Markdown", reply_markup=fail_markup)

    LOGIN_SESSIONS.pop(chat_id, None)

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

        # Update Admin Message
        approved_caption = (
            "✅ **សំណើដកលុយត្រូវបានយល់ព្រម និងផ្ទេររួចរាល់!**\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"👤 ឈ្មោះ៖ **{user['name']}** (ID: `{user['id']}`)\n"
            f"💳 លេខគណនី៖ `{user['account_number']}`\n"
            f"💸 ចំនួនទឹកប្រាក់ដក៖ **${withdraw['amount']:.2f}**\n"
            f"📉 សមតុល្យគណនីនៅសល់៖ **${new_balance:.2f}**\n"
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
        
    print("Telegram Bot is running...")
    # Start polling
    bot.infinity_polling()
