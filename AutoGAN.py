import sqlite3
import requests
import json
import io
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# --- CONFIGURATION ---
TOKEN = '8773415926:AAF12AicJUIO2teHSB68bYgS0D4ZZpSp2Ks'
ADMIN_ID = 6328650912 
API_URL = "https://ffgestapisrc.vercel.app/gen"
CHANNELS = ["@tufan95aura"] 

# States
REGION, NAME, COUNT, REDEEM_INP, BCAST, ADD_ID, ADD_AMT, PROMO_CODE, PROMO_VAL, PROMO_LIMIT = range(10)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- DATABASE ---
def get_db_connection():
    conn = sqlite3.connect('kamod_bot.db', timeout=30, check_same_thread=False)
    conn.execute('PRAGMA journal_mode=WAL;') 
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 20)''')
    c.execute('''CREATE TABLE IF NOT EXISTS promo_codes (code TEXT PRIMARY KEY, value INTEGER, uses_left INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS redeemed_history (user_id INTEGER, code TEXT, PRIMARY KEY (user_id, code))''')
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
    except: return 0

def update_balance(user_id, amount):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        conn.close()
    except: pass

# --- KEYBOARDS ---
def get_keyboard(user_id):
    keyboard = [
        ["🔥 GENERATE ACCOUNTS"],
        ["💰 BALANCE", "🎁 REDEEM"],
        ["👤 OWNER", "👥 REFER"]
    ]
    if user_id == ADMIN_ID:
        keyboard.append(["📊 STATS", "📢 BROADCAST"])
        keyboard.append(["➕ ADD COINS", "🎟 CREATE PROMO"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- START & FORCE JOIN ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        init_db()
        conn = get_db_connection(); c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, ?)", (user_id, 20))
        conn.commit(); conn.close()

        # Simple check for join (can be expanded)
        await update.message.reply_text(f"👋 Welcome! Your Balance: {get_user_data(user_id)}", reply_markup=get_keyboard(user_id))
    except Exception as e: logger.error(e)

# --- BUTTON HANDLER ---
async def main_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if text == "🔥 GENERATE ACCOUNTS":
        if get_user_data(user_id) <= 0:
            await update.message.reply_text("❌ Low Balance!")
            return ConversationHandler.END
        await update.message.reply_text("🌍 Enter Region (IND, BRA, ID):")
        return REGION
    elif text == "💰 BALANCE":
        await update.message.reply_text(f"💰 Your Balance: {get_user_data(user_id)} Coins")
    elif text == "🎁 REDEEM":
        await update.message.reply_text("🎁 Enter Promo Code:")
        return REDEEM_INP
    elif text == "👤 OWNER":
        await update.message.reply_text("👤 Owner: @kamod90")
    elif text == "👥 REFER":
        bot = (await context.bot.get_me()).username
        await update.message.reply_text(f"🔗 Link: https://t.me/{bot}?start={user_id}")
    
    # Admin Buttons
    if user_id == ADMIN_ID:
        if text == "📊 STATS":
            conn = get_db_connection()
            count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            conn.close()
            await update.message.reply_text(f"📊 Total Users: {count}")
        elif text == "📢 BROADCAST":
            await update.message.reply_text("Enter message to broadcast:")
            return BCAST
        elif text == "➕ ADD COINS":
            await update.message.reply_text("Enter User ID:")
            return ADD_ID
        elif text == "🎟 CREATE PROMO":
            await update.message.reply_text("Enter Promo Name:")
            return PROMO_CODE

# --- GENERATION WITH PROGRESS (90/1000) ---
async def get_reg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['rg'] = update.message.text
    await update.message.reply_text("👤 Enter Name:")
    return NAME

async def get_nm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nm'] = update.message.text
    await update.message.reply_text("🔢 How many accounts?")
    return COUNT

async def get_ct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        count = int(update.message.text)
        user_id = update.effective_user.id
        if count > get_user_data(user_id):
            await update.message.reply_text("❌ Not enough coins!")
            return ConversationHandler.END
        
        # Start Progress Message
        msg = await update.message.reply_text(f"🚀 Initializing: 0/{count}...")
        results = []
        
        for i in range(1, count + 1):
            try:
                r = requests.get(API_URL, params={'name': context.user_data['nm'], 'region': context.user_data['rg'], 'count': 1}, timeout=10)
                if r.status_code == 200:
                    results.append(r.json())
                # Update Progress every step
                await msg.edit_text(f"🚀 Generating: {i}/{count} Accounts...")
                await asyncio.sleep(0.5)
            except: continue
        
        update_balance(user_id, -count)
        f = io.BytesIO(json.dumps(results, indent=4).encode()); f.name = "accounts.json"
        await update.message.reply_document(document=f, caption=f"✅ Finished! Generated {len(results)} accounts.")
    except: pass
    return ConversationHandler.END

# --- ADMIN PROCESSES ---
async def bcast_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    conn = get_db_connection(); users = conn.execute("SELECT user_id FROM users").fetchall(); conn.close()
    await update.message.reply_text("📢 Broadcasting...")
    for u in users:
        try: await context.bot.send_message(chat_id=u[0], text=f"📢 Notification:\n\n{msg}")
        except: continue
    return ConversationHandler.END

async def add_id_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['target'] = update.message.text
    await update.message.reply_text("Amount:")
    return ADD_AMT

async def add_amt_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        update_balance(int(context.user_data['target']), int(update.message.text))
        await update.message.reply_text("✅ Coins Added.")
    except: await update.message.reply_text("❌ Error.")
    return ConversationHandler.END

async def promo_name_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['p_nm'] = update.message.text
    await update.message.reply_text("Value:")
    return PROMO_VAL

async def promo_val_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['p_vl'] = update.message.text
    await update.message.reply_text("Limit:")
    return PROMO_LIMIT

async def promo_lim_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = get_db_connection()
        conn.execute("INSERT INTO promo_codes VALUES (?, ?, ?)", (context.user_data['p_nm'], int(context.user_data['p_vl']), int(update.message.text)))
        conn.commit(); conn.close()
        await update.message.reply_text("✅ Promo Created.")
    except: await update.message.reply_text("❌ Error.")
    return ConversationHandler.END

async def redeemer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code, uid = update.message.text.strip(), update.effective_user.id
    conn = get_db_connection(); c = conn.cursor()
    c.execute("SELECT value, uses_left FROM promo_codes WHERE code = ?", (code,))
    res = c.fetchone()
    if res and res[1] > 0:
        c.execute("UPDATE promo_codes SET uses_left = uses_left - 1 WHERE code = ?", (code,))
        conn.commit(); update_balance(uid, res[0])
        await update.message.reply_text(f"✅ Success! +{res[0]} coins.")
    else: await update.message.reply_text("❌ Invalid code.")
    conn.close(); return ConversationHandler.END

# --- ERROR HANDLER ---
async def global_error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")

def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    
    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, main_handler)],
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
            PROMO_LIMIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, promo_lim_done)],
        },
        fallbacks=[CommandHandler('start', start)],
        allow_reentry=True
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.add_error_handler(global_error)
    
    print("Bot is LIVE...")
    app.run_polling()

if __name__ == '__main__':
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    main()