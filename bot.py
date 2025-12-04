# bot.py  (Koyeb-ready)
import os
import logging
import time
from threading import Thread
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import ReplyKeyboardMarkup, KeyboardButton
from pymongo import MongoClient, errors

# ---------------- Config from environment ----------------
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
MONGO_URI = os.getenv("MONGO_URI", "")
DB_NAME = os.getenv("DB_NAME", "forwarder")
COLLECTION = os.getenv("COLLECTION", "links")  # we'll use 'links' by default

# ---------------- Basic checks ----------------
if not (API_ID and API_HASH and BOT_TOKEN):
    raise RuntimeError("API_ID / API_HASH / BOT_TOKEN missing in environment variables.")

if not MONGO_URI:
    raise RuntimeError("MONGO_URI missing in environment variables. Set it to your MongoDB Atlas URI.")

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# ---------------- Flask for Koyeb health check ----------------
app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 8000))
    # disable Flask logging spam in production
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host="0.0.0.0", port=port)

# ---------------- MongoDB connection ----------------
try:
    mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    # force a connection attempt to fail fast if credentials/URI bad
    mongo.server_info()
    db = mongo[DB_NAME]
    links_col = db[COLLECTION]
    logger.info("Connected to MongoDB (%s/%s)", DB_NAME, COLLECTION)
except errors.ServerSelectionTimeoutError as e:
    logger.exception("Cannot connect to MongoDB: %s", e)
    raise

# ---------------- Pyrogram Bot ----------------
bot = Client(
    "forwarder-bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    # Work nice on hosted envs — keep session in memory
    workdir="."
)

# ---------------- Helpers (synchronous, using pymongo) ----------------
def ensure_user_doc(user_id: int):
    if links_col.find_one({"user_id": user_id}) is None:
        links_col.insert_one({
            "user_id": user_id,
            "source_chat_id": None,
            "target_chat_id": None,
            "is_active": False,
            "state": None  # can be "await_source" or "await_target"
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

# ---------------- Reply Keyboard ----------------
def start_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📥 Set Source Channel")],
            [KeyboardButton("📤 Set Target Channel")],
            [KeyboardButton("▶️ Start Forwarding"), KeyboardButton("⏸ Stop Forwarding")],
            [KeyboardButton("ℹ️ Status")]
        ],
        resize_keyboard=True
    )

# ---------------- Command: /start ----------------
@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    user_id = message.from_user.id
    ensure_user_doc(user_id)
    link = get_link(user_id)
    text = (
        "📡 Forward Bot Setup\n\n"
        f"Source: {link.get('source_chat_id')}\n"
        f"Target: {link.get('target_chat_id')}\n"
        f"Active: {link.get('is_active')}\n\n"
        "Buttons se configure karein."
    )
    await message.reply_text(text, reply_markup=start_keyboard())

# ---------------- Keyboard handlers (private) ----------------
@bot.on_message(filters.private & filters.text & filters.regex(r"^📥 Set Source Channel$"))
async def kb_set_source(client, message):
    user_id = message.from_user.id
    await message.reply_text("Source channel ka ID ya @username bhejo.\nExample: -1001234567890 ya @my_source_channel")
    set_state(user_id, "await_source")

@bot.on_message(filters.private & filters.text & filters.regex(r"^📤 Set Target Channel$"))
async def kb_set_target(client, message):
    user_id = message.from_user.id
    await message.reply_text("Target channel ka ID ya @username bhejo.\nExample: -1009876543210 ya @my_target_channel")
    set_state(user_id, "await_target")

@bot.on_message(filters.private & filters.text & filters.regex(r"^▶️ Start Forwarding$"))
async def kb_start_forwarding(client, message):
    user_id = message.from_user.id
    link = get_link(user_id)
    if not link.get("source_chat_id") or not link.get("target_chat_id"):
        await message.reply_text("❗ Pehle Source aur Target set karein.")
        return
    set_active(user_id, True)
    await message.reply_text("✅ Forwarding started.", reply_markup=start_keyboard())

@bot.on_message(filters.private & filters.text & filters.regex(r"^⏸ Stop Forwarding$"))
async def kb_stop_forwarding(client, message):
    user_id = message.from_user.id
    set_active(user_id, False)
    await message.reply_text("⏸ Forwarding stopped.", reply_markup=start_keyboard())

@bot.on_message(filters.private & filters.text & filters.regex(r"^ℹ️ Status$"))
async def kb_status(client, message):
    user_id = message.from_user.id
    link = get_link(user_id)
    await message.reply_text(
        f"Source: {link.get('source_chat_id')}\n"
        f"Target: {link.get('target_chat_id')}\n"
        f"Active: {link.get('is_active')}",
        reply_markup=start_keyboard()
    )

# ---------------- Handle plain text while in state (private) ----------------
@bot.on_message(filters.private & filters.text)
async def private_text_handler(client, message):
    user_id = message.from_user.id
    state = get_state(user_id)
    text = message.text.strip()

    if state == "await_source":
        # store @username as string or numeric ID as int
        if text.startswith("@"):
            chat_id = text
        else:
            try:
                chat_id = int(text)
            except ValueError:
                await message.reply_text("Galat ID. Example: -1001234567890 ya @username. Dobara bhejo.")
                return
        set_source(user_id, chat_id)
        set_state(user_id, None)
        await message.reply_text(f"✅ Source set: {chat_id}", reply_markup=start_keyboard())
        return

    if state == "await_target":
        if text.startswith("@"):
            chat_id = text
        else:
            try:
                chat_id = int(text)
            except ValueError:
                await message.reply_text("Galat ID. Example: -1009876543210 ya @username. Dobara bhejo.")
                return
        set_target(user_id, chat_id)
        set_state(user_id, None)
        await message.reply_text(f"✅ Target set: {chat_id}", reply_markup=start_keyboard())
        return

    # if not in a state, ignore or instruct
    # (this will also catch button commands already handled above)
    if text.startswith("/") or text in ["📥 Set Source Channel", "📤 Set Target Channel", "▶️ Start Forwarding", "⏸ Stop Forwarding", "ℹ️ Status"]:
        # these are handled elsewhere
        return
    await message.reply_text("Setup ke liye /start use karo.", reply_markup=start_keyboard())

# ---------------- Auto-forwarder: listens to channel messages ----------------
@bot.on_message(filters.channel)
async def channel_forwarder(client, message):
    chat_id = message.chat.id
    # find all active links where this chat is the source (stored either as int or str)
    try:
        cursor = links_col.find({
            "source_chat_id": {"$in": [chat_id, str(chat_id)]},
            "is_active": True,
            "target_chat_id": {"$ne": None}
        })
    except Exception as e:
        logger.exception("MongoDB query failed in forwarder: %s", e)
        return

    for link in cursor:
        target = link.get("target_chat_id")
        if not target:
            continue
        try:
            # message.copy or forward depending on need — using copy to preserve original sender details
            # If target is stored as username string (starts with @), Pyrogram accepts it.
            await message.copy(chat_id=target)
            logger.info("Forwarded message from %s -> %s for user %s", chat_id, target, link.get("user_id"))
        except Exception as e:
            logger.exception("Forward error for mapping %s -> %s : %s", chat_id, target, e)

# ---------------- Optional ping command for latency check ----------------
@bot.on_message(filters.command("ping") & filters.private)
async def ping_cmd(client, message):
    t0 = time.time()
    m = await message.reply_text("Pinging...")
    dt = int((time.time() - t0) * 1000)
    await m.edit_text(f"Pong! {dt} ms")

# ---------------- Start the bot ----------------
def run_bot():
    logger.info("Starting Pyrogram client...")
    try:
        bot.run()
    except Exception as e:
        logger.exception("Bot crashed: %s", e)
        raise

if __name__ == "__main__":
    # Start Flask in background thread (so Koyeb health check passes)
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("Flask health server started on port %s", os.environ.get("PORT", "8000"))

    # Start bot in main thread (blocking)
    run_bot()            try:
                await msg.copy(chat_id=target)
            except Exception as e:
                print("Forward error:", e)


print("Bot is running...")
bot.run()
@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    user_id = message.from_user.id
    link = await get_link(user_id)

    text = (
        "Forward Bot Setup\n\n"
        f"Source: {link.get('source_chat_id')}\n"
        f"Target: {link.get('target_chat_id')}\n"
        f"Active: {link.get('is_active')}"
    )

    await message.reply_text(
        text,
        reply_markup=start_keyboard(),
    )


@bot.on_callback_query()
async def callbacks(client, query):
    user_id = query.from_user.id
    data = query.data

    if data == "set_source":
        await set_state(user_id, "await_source")
        await query.message.edit_text(
            "Source channel ka ID ya @username bhejo.\n"
            "Example: -1001234567890 ya @my_source_channel"
        )
    elif data == "set_target":
        await set_state(user_id, "await_target")
        await query.message.edit_text(
            "Target channel ka ID ya @username bhejo.\n"
            "Example: -1009876543210 ya @my_target_channel"
        )
    elif data == "toggle_start":
        link = await get_link(user_id)
        src = link.get("source_chat_id")
        tgt = link.get("target_chat_id")

# bot_fixed.py
import os
import time
import logging
from pyrogram import Client, filters
from pyrogram.types import ReplyKeyboardMarkup, KeyboardButton
from pymongo import MongoClient
from config import *  # API_ID, API_HASH, BOT_TOKEN, MONGO_URI, DB_NAME, COLLECTION

# ----------------- logging -----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== MONGO DB SETUP ==========
# Ensure MONGO_URI comes from config or env
mongo = MongoClient(MONGO_URI)
db = mongo[DB_NAME]
users = db[COLLECTION]      # original users collection
links_col = db.get_collection("links")  # for storing per-user forward settings

# ========== TELEGRAM BOT SETUP ==========
bot = Client(
    "forwarder-bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ========== START BUTTONS ==========
def start_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📥 Set Source Channel")],
            [KeyboardButton("📤 Set Target Channel")],
            [KeyboardButton("🚀 Start Bot")]
        ],
        resize_keyboard=True
    )

# ---------------- helper DB functions ----------------
def ensure_user_doc(user_id: int):
    """Ensure a base document exists in links_col for the user."""
    if links_col.find_one({"user_id": user_id}) is None:
        links_col.insert_one({
            "user_id": user_id,
            "source_chat_id": None,
            "target_chat_id": None,
            "is_active": False,
            "state": None
        })

async def get_link(user_id: int):
    ensure_user_doc(user_id)
    return links_col.find_one({"user_id": user_id})

async def set_source(user_id: int, chat_id):
    ensure_user_doc(user_id)
    links_col.update_one({"user_id": user_id}, {"$set": {"source_chat_id": chat_id}})

async def set_target(user_id: int, chat_id):
    ensure_user_doc(user_id)
    links_col.update_one({"user_id": user_id}, {"$set": {"target_chat_id": chat_id}})

async def set_state(user_id: int, state: str | None):
    ensure_user_doc(user_id)
    links_col.update_one({"user_id": user_id}, {"$set": {"state": state}})

async def get_state(user_id: int):
    ensure_user_doc(user_id)
    doc = links_col.find_one({"user_id": user_id})
    return doc.get("state")

async def set_active(user_id: int, val: bool):
    ensure_user_doc(user_id)
    links_col.update_one({"user_id": user_id}, {"$set": {"is_active": bool(val)}})

# ========== START COMMAND ==========
@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(_, message):
    user_id = message.from_user.id
    ensure_user_doc(user_id)
    link = await get_link(user_id)
    text = (
        "Forward Bot Setup\n\n"
        f"Source: {link.get('source_chat_id')}\n"
        f"Target: {link.get('target_chat_id')}\n"
        f"Active: {link.get('is_active')}\n\n"
        "Use buttons below to configure."
    )
    await message.reply_text(text, reply_markup=start_keyboard())

# ========== Keyboard button handlers ==========
@bot.on_message(filters.private & filters.text & filters.regex(r"^📥 Set Source Channel$"))
async def set_source_button(_, message):
    user_id = message.from_user.id
    await set_state(user_id, "await_source")
    await message.reply_text("Source channel ID ya @username bhejo.\nExample: -1001234567890 ya @my_source_channel")

@bot.on_message(filters.private & filters.text & filters.regex(r"^📤 Set Target Channel$"))
async def set_target_button(_, message):
    user_id = message.from_user.id
    await set_state(user_id, "await_target")
    await message.reply_text("Target channel ID ya @username bhejo.\nExample: -1009876543210 ya @my_target_channel")

@bot.on_message(filters.private & filters.text & filters.regex(r"^🚀 Start Bot$"))
async def start_bot_button(_, message):
    user_id = message.from_user.id
    link = await get_link(user_id)
    if not link.get("source_chat_id") or not link.get("target_chat_id"):
        await message.reply_text("❗ Pehle Source aur Target set karo!")
        return
    await set_active(user_id, True)
    await message.reply_text("✅ Forwarding started. Ab source channel me aate hi messages target me jayenge.")

# ========== Generic private text handler for states ==========
@bot.on_message(filters.private & filters.text)
async def private_text_handler(client, message):
    user_id = message.from_user.id
    state = await get_state(user_id)
    text = message.text.strip()

    # If user is in state to give source
    if state == "await_source":
        if text.startswith("@"):
            chat_id = text  # store username string
        else:
            try:
                chat_id = int(text)
            except ValueError:
                await message.reply_text("Galat ID/username. Dubara bhejo.")
                return
        await set_source(user_id, chat_id)
        await set_state(user_id, None)
        await message.reply_text(f"Source set: {chat_id}\n\nAb Target set karo.", reply_markup=start_keyboard())
        return

    # If user is in state to give target
    if state == "await_target":
        if text.startswith("@"):
            chat_id = text
        else:
            try:
                chat_id = int(text)
            except ValueError:
                await message.reply_text("Galat ID/username. Dubara bhejo.")
                return
        await set_target(user_id, chat_id)
        await set_state(user_id, None)
        await message.reply_text(f"Target set: {chat_id}\n\nAb /start karke Start button dabao.", reply_markup=start_keyboard())
        return

    # Default fallback message
    await message.reply_text("Setup ke liye /start use karo.", reply_markup=start_keyboard())

# ---------- Forwarding from source to target ----------
@bot.on_message(filters.channel)
async def channel_forwarder(client, message):
    chat_id = message.chat.id
    # find users who use this chat as source and have active forwarding
    cursor = links_col.find({
        "source_chat_id": {"$in": [chat_id, str(chat_id)]},
        "is_active": True,
        "target_chat_id": {"$ne": None}
    })

    # cursor is a synchronous pymongo cursor; iterate normally
    for link in cursor:
        target = link.get("target_chat_id")
        try:
            # message.forward accepts int id or @username
            await message.forward(chat_id=target)
        except Exception as e:
            logger.error("Forward error for user %s -> %s : %s", link.get("user_id"), target, e)

# ---------- Ping command (optional) ----------
@bot.on_message(filters.command("ping") & filters.private)
async def ping_cmd(client, message):
    start_ts = time.time()
    msg = await message.reply_text("Pinging...")
    delta = (time.time() - start_ts) * 1000
    await msg.edit_text(f"Pong! {int(delta)} ms")

# ---------- Main ----------
if __name__ == "__main__":
    logger.info("Bot starting...")
    bot.run()
