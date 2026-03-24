import sqlite3
import requests
import json
import io
import asyncio
import logging
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# --- CONFIGURATION ---
TOKEN = '8301368648:AAEm1cmRVBwXvo_-8w0shjc4OlGkB2pdYQs'
ADMIN_ID = 6328650912 
API_URL = "https://ffgestapisrc.vercel.app/gen"
CHANNELS = ["@tufan95aura"] 

# States
REGION, NAME, COUNT, REDEEM_INP, BCAST, ADD_ID, ADD_AMT, PROMO_CODE, PROMO_VAL, PROMO_LIMIT = range(10)

# Logging Setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- DATABASE FUNCTIONS ---
def get_db_connection():
    conn = sqlite3.connect('kamod_bot.db', timeout=30, check_same_thread=False)
    conn.execute('PRAGMA journal_mode=WAL;') 
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 20, referred_by INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS promo_codes 
                 (code TEXT PRIMARY KEY, value INTEGER, uses_left INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS redeemed_history 
                 (user_id INTEGER, code TEXT, PRIMARY KEY (user_id, code))''')
    conn.commit()
    conn.close()

def get_user_data(user_id):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        res = c.fetchone()
        conn.close()
        return res[0] if res else 0
    except Exception: return 0

def update_balance(user_id, amount):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        conn.close()
    except Exception: pass

# --- KEYBOARDS ---
def get_main_keyboard():
    return ReplyKeyboardMarkup([
        ["🔥 GENERATE ACCOUNTS"],
        ["💰 BALANCE", "🎁 REDEEM"],
        ["👤 OWNER", "👥 REFER"]
    ], resize_keyboard=True)

def get_admin_keyboard():
    return ReplyKeyboardMarkup([
        ["📊 STATS", "📢 BROADCAST"],
        ["➕ ADD COINS", "🎟 CREATE PROMO"],
        ["🏠 EXIT ADMIN"]
    ], resize_keyboard=True)

# --- UTILS ---
async def is_subscribed(bot, user_id):
    if user_id == ADMIN_ID: return True
    for channel in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in ['left', 'kicked']: return False
        except: return False
    return True

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        init_db()
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        if not c.fetchone():
            ref_id = int(context.args[0]) if context.args and context.args[0].isdigit() else None
            if ref_id and ref_id != user_id:
                update_balance(ref_id, 20)
                try: await context.bot.send_message(chat_id=ref_id, text="🎁 Referral Bonus! +20 coins.")
                except: pass
            c.execute("INSERT INTO users (user_id, balance, referred_by) VALUES (?, ?, ?)", (user_id, 20, ref_id))
            conn.commit()
        conn.close()

        if not await is_subscribed(context.bot, user_id):
            btn = [[InlineKeyboardButton("Join Channel", url=f"https://t.me/{CHANNELS[0][1:]}")],
                   [InlineKeyboardButton("✅ Verify", callback_data="verify")]]
            await update.message.reply_text("❌ Join our channel first!", reply_markup=InlineKeyboardMarkup(btn))
            return

        await update.message.reply_text(f"👋 Welcome! Balance: {get_user_data(user_id)}", reply_markup=get_main_keyboard())
    except Exception as e: logger.error(e)

# --- ADMIN PANEL FLOW ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("🛠 Admin Keyboard Activated.", reply_markup=get_admin_keyboard())

async def admin_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if update.effective_user.id != ADMIN_ID: return

    if text == "📊 STATS":
        conn = get_db_connection()
        total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        conn.close()
        await update.message.reply_text(f"📊 Total Users: {total}")
    elif text == "📢 BROADCAST":
        await update.message.reply_text("Enter text to broadcast:")
        return BCAST
    elif text == "➕ ADD COINS":
        await update.message.reply_text("Enter Target User ID:")
        return ADD_ID
    elif text == "🎟 CREATE PROMO":
        await update.message.reply_text("Enter Promo Code Name:")
        return PROMO_CODE
    elif text == "🏠 EXIT ADMIN":
        await update.message.reply_text("Exited Admin Mode.", reply_markup=get_main_keyboard())
        return ConversationHandler.END

# --- ADMIN SUB-HANDLERS ---
async def bcast_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    conn = get_db_connection()
    users = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    await update.message.reply_text("🚀 Sending...")
    for u in users:
        try: await context.bot.send_message(chat_id=u[0], text=f"📢 NEWS:\n\n{msg}")
        except: continue
    await update.message.reply_text("✅ Done.")
    return ConversationHandler.END

async def add_id_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['tmp_id'] = update.message.text
    await update.message.reply_text("Enter Amount:")
    return ADD_AMT

async def add_amt_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid, amt = int(context.user_data['tmp_id']), int(update.message.text)
        update_balance(uid, amt)
        await update.message.reply_text(f"✅ Added {amt} to {uid}")
    except: await update.message.reply_text("❌ Error.")
    return ConversationHandler.END

async def promo_name_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['p_name'] = update.message.text
    await update.message.reply_text("Enter Value:")
    return PROMO_VAL

async def promo_val_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['p_val'] = update.message.text
    await update.message.reply_text("Enter Limit:")
    return PROMO_LIMIT

async def promo_limit_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        code, val, lim = context.user_data['p_name'], int(context.user_data['p_val']), int(update.message.text)
        conn = get_db_connection()
        conn.execute("INSERT OR REPLACE INTO promo_codes VALUES (?, ?, ?)", (code, val, lim))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ Promo Created: {code}")
    except: await update.message.reply_text("❌ Error.")
    return ConversationHandler.END

# --- USER FLOW ---
async def user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, uid = update.message.text, update.effective_user.id
    if text == "🔥 GENERATE ACCOUNTS":
        if get_user_data(uid) <= 0:
            await update.message.reply_text("❌ Low Balance!")
            return ConversationHandler.END
        await update.message.reply_text("🌍 Enter Region (IND, BRA, ID):")
        return REGION
    elif text == "💰 BALANCE":
        await update.message.reply_text(f"💰 Balance: {get_user_data(uid)}")
    elif text == "🎁 REDEEM":
        await update.message.reply_text("🎁 Enter Code:")
        return REDEEM_INP
    elif text == "👤 OWNER":
        await update.message.reply_text("👤 Owner: @kamod90")
    elif text == "👥 REFER":
        bot = (await context.bot.get_me()).username
        await update.message.reply_text(f"🔗 Link: https://t.me/{bot}?start={uid}")

# --- GEN LOGIC ---
async def get_reg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['rg'] = update.message.text
    await update.message.reply_text("👤 Enter Name:")
    return NAME

async def get_nm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nm'] = update.message.text
    await update.message.reply_text("🔢 How many?")
    return COUNT

async def get_ct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        count = int(update.message.text)
        uid = update.effective_user.id
        if count > get_user_data(uid):
            await update.message.reply_text("❌ Low Balance!")
            return ConversationHandler.END
        
        msg = await update.message.reply_text("🚀 Working...")
        res = []
        for _ in range(count):
            try:
                r = requests.get(API_URL, params={'name': context.user_data['nm'], 'region': context.user_data['rg'], 'count': 1}, timeout=10)
                if r.status_code == 200: res.append(r.json())
            except: continue
        
        update_balance(uid, -count)
        f = io.BytesIO(json.dumps(res, indent=4).encode()); f.name = "accs.json"
        await update.message.reply_document(document=f, caption="✅ Success!")
    except: pass
    return ConversationHandler.END

async def redeemer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code, uid = update.message.text.strip(), update.effective_user.id
    conn = get_db_connection(); c = conn.cursor()
    c.execute("SELECT 1 FROM redeemed_history WHERE user_id = ? AND code = ?", (uid, code))
    if c.fetchone():
        await update.message.reply_text("❌ Already Claimed!")
    else:
        c.execute("SELECT value, uses_left FROM promo_codes WHERE code = ?", (code,))
        res = c.fetchone()
        if res and res[1] > 0:
            c.execute("UPDATE promo_codes SET uses_left = uses_left - 1 WHERE code = ?", (code,))
            c.execute("INSERT INTO redeemed_history VALUES (?, ?)", (uid, code))
            conn.commit(); update_balance(uid, res[0])
            await update.message.reply_text(f"✅ Added {res[0]} coins.")
        else: await update.message.reply_text("❌ Invalid.")
    conn.close()
    return ConversationHandler.END

# --- ERROR HANDLER ---
async def global_error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} error: {context.error}")

# --- MAIN ---
def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    
    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex('^(🔥 GENERATE ACCOUNTS|🎁 REDEEM)$'), user_handler),
            MessageHandler(filters.Regex('^(📢 BROADCAST|➕ ADD COINS|🎟 CREATE PROMO)$'), admin_input_handler)
        ],
        states={
            REGION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_reg)],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_nm)],
            COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_ct)],
            REDEEM_INP: [MessageHandler(filters.TEXT & ~filters.COMMAND, redeemer)],
            BCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, bcast_done)],
            ADD_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_id_done)],
            ADD_AMT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_amt_done)],
            PROMO_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, promo_name_done)],
            PROMO_VAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, promo_val_done)],
            PROMO_LIMIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, promo_limit_done)],
        },
        fallbacks=[CommandHandler('start', start), MessageHandler(filters.Regex('^🏠 EXIT ADMIN$'), admin_input_handler)],
        allow_reentry=True
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, user_handler))
    
    app.add_error_handler(global_error_handler)
    
    print("Bot Started...")
    app.run_polling()

if __name__ == '__main__':
    # Python 3.12+ loop fix
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    main()