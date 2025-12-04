# bot.py  (minimal, Koyeb-ready, bracket-safe)
import os
import logging
import time
from threading import Thread
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import ReplyKeyboardMarkup, KeyboardButton
from pymongo import MongoClient, errors

# Config
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
MONGO_URI = os.getenv("MONGO_URI", "")
DB_NAME = os.getenv("DB_NAME", "forwarder")
COLLECTION = os.getenv("COLLECTION", "links")

if not (API_ID and API_HASH and BOT_TOKEN):
    raise RuntimeError("API_ID / API_HASH / BOT_TOKEN missing.")

if not MONGO_URI:
    raise RuntimeError("MONGO_URI missing.")

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# Flask (health)
app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 8000))
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host="0.0.0.0", port=port)

# Mongo
try:
    mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    mongo.server_info()
    db = mongo[DB_NAME]
    links_col = db[COLLECTION]
    logger.info("Connected to MongoDB")
except errors.ServerSelectionTimeoutError as e:
    logger.exception("MongoDB connect failed: %s", e)
    raise

# Bot
bot = Client("forwarder-bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Helpers (sync pymongo)
def ensure_user_doc(user_id: int):
    if links_col.find_one({"user_id": user_id}) is None:
        links_col.insert_one({
            "user_id": user_id,
            "source_chat_id": None,
            "target_chat_id": None,
            "is_active": False,
            "state": None
        })

def get_link(user_id: int):
    ensure_user_doc(user_id)
    return links_col.find_one({"user_id": user_id})

def set_source(user_id: int, chat_id):
    ensure_user_doc(user_id)
    links_col.update_one({"user_id": user_id}, {"$set": {"source_chat_id": chat_id}})

def set_target(user_id: int, chat_id):
    ensure_user_doc(user_id)
    links_col.update_one({"user_id": user_id}, {"$set": {"target_chat_id": chat_id}})

def set_state(user_id: int, state):
    ensure_user_doc(user_id)
    links_col.update_one({"user_id": user_id}, {"$set": {"state": state}})

def get_state(user_id: int):
    ensure_user_doc(user_id)
    doc = links_col.find_one({"user_id": user_id})
    return doc.get("state")

def set_active(user_id: int, val: bool):
    ensure_user_doc(user_id)
    links_col.update_one({"user_id": user_id}, {"$set": {"is_active": bool(val)}})

# Keyboard (single-line list to avoid stray brackets)
def start_keyboard():
    buttons = [
        ["📥 Set Source Channel"],
        ["📤 Set Target Channel"],
        ["▶️ Start Forwarding", "⏸ Stop Forwarding"],
        ["ℹ️ Status"]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# Handlers
@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(_, message):
    user_id = message.from_user.id
    ensure_user_doc(user_id)
    link = get_link(user_id)
    text = (
        "Forward Bot Setup\n\n"
        f"Source: {link.get('source_chat_id')}\n"
        f"Target: {link.get('target_chat_id')}\n"
        f"Active: {link.get('is_active')}"
    )
    await message.reply_text(text, reply_markup=start_keyboard())

@bot.on_message(filters.private & filters.text & filters.regex(r"^📥 Set Source Channel$"))
async def kb_set_source(_, message):
    set_state(message.from_user.id, "await_source")
    await message.reply_text("Source channel ID ya @username bhejo. Example: -1001234567890 ya @source_channel")

@bot.on_message(filters.private & filters.text & filters.regex(r"^📤 Set Target Channel$"))
async def kb_set_target(_, message):
    set_state(message.from_user.id, "await_target")
    await message.reply_text("Target channel ID ya @username bhejo. Example: -1009876543210 ya @target_channel")

@bot.on_message(filters.private & filters.text & filters.regex(r"^▶️ Start Forwarding$"))
async def kb_start(_, message):
    user_id = message.from_user.id
    link = get_link(user_id)
    if not link.get("source_chat_id") or not link.get("target_chat_id"):
        await message.reply_text("Pehle source aur target set karein.")
        return
    set_active(user_id, True)
    await message.reply_text("Forwarding started.", reply_markup=start_keyboard())

@bot.on_message(filters.private & filters.text & filters.regex(r"^⏸ Stop Forwarding$"))
async def kb_stop(_, message):
    set_active(message.from_user.id, False)
    await message.reply_text("Forwarding stopped.", reply_markup=start_keyboard())

@bot.on_message(filters.private & filters.text & filters.regex(r"^ℹ️ Status$"))
async def kb_status(_, message):
    link = get_link(message.from_user.id)
    await message.reply_text(f"Source: {link.get('source_chat_id')}\nTarget: {link.get('target_chat_id')}\nActive: {link.get('is_active')}", reply_markup=start_keyboard())

@bot.on_message(filters.private & filters.text)
async def private_text_handler(_, message):
    user_id = message.from_user.id
    state = get_state(user_id)
    text = message.text.strip()
    if state == "await_source":
        if text.startswith("@"):
            chat_id = text
        else:
            try:
                chat_id = int(text)
            except ValueError:
                await message.reply_text("Galat ID. Dobara bheje.")
                return
        set_source(user_id, chat_id)
        set_state(user_id, None)
        await message.reply_text(f"Source set: {chat_id}", reply_markup=start_keyboard())
        return
    if state == "await_target":
        if text.startswith("@"):
            chat_id = text
        else:
            try:
                chat_id = int(text)
            except ValueError:
                await message.reply_text("Galat ID. Dobara bheje.")
                return
        set_target(user_id, chat_id)
        set_state(user_id, None)
        await message.reply_text(f"Target set: {chat_id}", reply_markup=start_keyboard())
        return
    # ignore other plain texts
    return

@bot.on_message(filters.channel)
async def channel_forwarder(_, message):
    chat_id = message.chat.id
    try:
        cursor = links_col.find({
            "source_chat_id": {"$in": [chat_id, str(chat_id)]},
            "is_active": True,
            "target_chat_id": {"$ne": None}
        })
    except Exception as e:
        logger.exception("DB query failed: %s", e)
        return
    for link in cursor:
        target = link.get("target_chat_id")
        if not target:
            continue
        try:
            await message.copy(chat_id=target)
            logger.info("Forwarded %s -> %s", chat_id, target)
        except Exception as e:
            logger.exception("Forward failed: %s", e)

# Ping
@bot.on_message(filters.command("ping") & filters.private)
async def ping_cmd(_, message):
    t0 = time.time()
    m = await message.reply_text("Pinging...")
    dt = int((time.time() - t0) * 1000)
    await m.edit_text(f"Pong! {dt} ms")

def run_bot():
    logger.info("Starting bot...")
    bot.run()

if __name__ == "__main__":
    # start flask in thread and bot in main thread
    Thread(target=run_flask, daemon=True).start()
    logger.info("Flask started on port %s", os.environ.get("PORT", "8000"))
    run_bot()
