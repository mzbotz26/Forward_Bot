# bot.py — multi-target + broadcast + inline UI, Koyeb-ready (no Flask)
import os
import logging
import time
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient, errors

# ---------- Config ----------
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

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# ---------- Simple health server ----------
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.end_headers()

def run_health_server():
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logger.info("Health server listening on port %s", port)
    server.serve_forever()

# ---------- MongoDB ----------
try:
    mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    mongo.server_info()
    db = mongo[DB_NAME]
    links_col = db[COLLECTION]
    logger.info("Connected to MongoDB: %s/%s", DB_NAME, COLLECTION)
except errors.ServerSelectionTimeoutError as e:
    logger.exception("Cannot connect to MongoDB: %s", e)
    raise

# ---------- Pyrogram client ----------
bot = Client("forwarder-bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ---------- Helpers ----------
def ensure_user_doc(user_id: int):
    if links_col.find_one({"user_id": user_id}) is None:
        links_col.insert_one({
            "user_id": user_id,
            "source_chat_id": None,
            "targets": [],            # list of targets (ints or @usernames)
            "is_active": False,
            "state": None             # awaited states: 'await_source', 'await_add_target', 'await_broadcast', 'await_remove_target'
        })

def get_link(user_id: int):
    ensure_user_doc(user_id)
    return links_col.find_one({"user_id": user_id})

def set_source(user_id: int, chat_id):
    ensure_user_doc(user_id)
    links_col.update_one({"user_id": user_id}, {"$set": {"source_chat_id": chat_id}})

def add_target(user_id: int, chat_id):
    ensure_user_doc(user_id)
    # addToSet to avoid duplicates
    links_col.update_one({"user_id": user_id}, {"$addToSet": {"targets": chat_id}})

def remove_target(user_id: int, chat_id):
    ensure_user_doc(user_id)
    links_col.update_one({"user_id": user_id}, {"$pull": {"targets": chat_id}})

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

# ---------- UI ----------
def start_inline_keyboard():
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📥 Set Source", callback_data="set_source")],
            [InlineKeyboardButton("➕ Add Target", callback_data="add_target")],
            [InlineKeyboardButton("📋 List Targets", callback_data="list_targets")],
            [InlineKeyboardButton("📣 Broadcast", callback_data="broadcast")],
            [
                InlineKeyboardButton("▶️ Start", callback_data="start_forward"),
                InlineKeyboardButton("⏸ Stop", callback_data="stop_forward")
            ],
            [InlineKeyboardButton("ℹ️ Status", callback_data="status")]
        ]
    )
    return kb

# ---------- /start ----------
@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    user_id = message.from_user.id
    ensure_user_doc(user_id)
    link = get_link(user_id)
    targets = link.get("targets") or []
    text = (
        "📡 Forward Bot Setup\n\n"
        f"Source: {link.get('source_chat_id')}\n"
        f"Targets ({len(targets)}): {', '.join(map(str, targets)) if targets else 'None'}\n"
        f"Active: {link.get('is_active')}\n\n"
        "Use buttons below to configure (Add/Remove/List/Broadcast)."
    )
    await message.reply_text(text, reply_markup=start_inline_keyboard())

# ---------- Callbacks ----------
@bot.on_callback_query()
async def callbacks(client, query):
    user_id = query.from_user.id
    data = query.data

    if data == "set_source":
        set_state(user_id, "await_source")
        await query.answer("Send source channel ID or @username in this private chat.", show_alert=False)
        try:
            await query.message.edit_text("Send source channel ID or @username in this private chat.\nExample: -1001234567890 or @my_source_channel", reply_markup=None)
        except Exception:
            pass

    elif data == "add_target":
        set_state(user_id, "await_add_target")
        await query.answer("Send target channel ID or @username in this private chat.", show_alert=False)
        try:
            await query.message.edit_text("Send target channel ID or @username in this private chat.\nExample: -1009876543210 or @my_target_channel", reply_markup=None)
        except Exception:
            pass

    elif data == "list_targets":
        link = get_link(user_id)
        targets = link.get("targets") or []
        text = "Targets:\n" + ("\n".join(f"{i+1}. {t}" for i, t in enumerate(targets)) if targets else "No targets set.")
        await query.answer()
        try:
            await query.message.edit_text(text, reply_markup=start_inline_keyboard())
        except Exception:
            pass

    elif data == "broadcast":
        set_state(user_id, "await_broadcast")
        await query.answer("Send the message (text/media) you want to broadcast to all targets.", show_alert=False)
        try:
            await query.message.edit_text("Send the message (text/media) you want to broadcast to all targets.", reply_markup=None)
        except Exception:
            pass

    elif data == "start_forward":
        link = get_link(user_id)
        if not link.get("source_chat_id") or not link.get("targets"):
            await query.answer("First set source and at least one target.", show_alert=True)
            return
        set_active(user_id, True)
        await query.answer("Forwarding started.", show_alert=False)
        link = get_link(user_id)
        try:
            await query.message.edit_text("Forwarding started.\n\n" + f"Source: {link.get('source_chat_id')}\nTargets: {', '.join(map(str, link.get('targets', [])))}", reply_markup=start_inline_keyboard())
        except Exception:
            pass

    elif data == "stop_forward":
        set_active(user_id, False)
        await query.answer("Forwarding stopped.", show_alert=False)
        link = get_link(user_id)
        try:
            await query.message.edit_text("Forwarding stopped.\n\n" + f"Source: {link.get('source_chat_id')}\nTargets: {', '.join(map(str, link.get('targets', [])))}", reply_markup=start_inline_keyboard())
        except Exception:
            pass

    elif data == "status":
        link = get_link(user_id)
        targets = link.get("targets") or []
        await query.answer()
        try:
            await query.message.edit_text("Status\n\n" + f"Source: {link.get('source_chat_id')}\nTargets ({len(targets)}): {', '.join(map(str, targets)) if targets else 'None'}\nActive: {link.get('is_active')}", reply_markup=start_inline_keyboard())
        except Exception:
            pass

    else:
        await query.answer()

# ---------- Private message handler for states ----------
@bot.on_message(filters.private & filters.text)
async def private_state_handler(client, message):
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
                await message.reply_text("Invalid ID. Send -100... or @username.")
                return
        set_source(user_id, chat_id)
        set_state(user_id, None)
        await message.reply_text(f"✅ Source set to: {chat_id}\nUse buttons to add targets.", reply_markup=start_inline_keyboard())
        return

    if state == "await_add_target":
        if text.startswith("@"):
            chat_id = text
        else:
            try:
                chat_id = int(text)
            except ValueError:
                await message.reply_text("Invalid ID. Send -100... or @username.")
                return
        add_target(user_id, chat_id)
        set_state(user_id, None)
        await message.reply_text(f"✅ Target added: {chat_id}\nUse /start or buttons to see status.", reply_markup=start_inline_keyboard())
        return

    if text.startswith("/remove_target"):
        # format: /remove_target <target>
        parts = text.split(maxsplit=1)
        if len(parts) != 2:
            await message.reply_text("Usage: /remove_target <target_id_or_@username>")
            return
        target = parts[1].strip()
        remove_target(user_id, target if target.startswith("@") else int(target))
        await message.reply_text(f"✅ Removed target: {target}", reply_markup=start_inline_keyboard())
        return

    # broadcast state will accept any message (text/media) and copy it
    if state == "await_broadcast":
        link = get_link(user_id)
        targets = link.get("targets") or []
        if not targets:
            await message.reply_text("No targets set. Add targets first.", reply_markup=start_inline_keyboard())
            set_state(user_id, None)
            return

        # copy the message object to every target
        for tgt in targets:
            try:
                await message.copy(chat_id=tgt)
            except Exception as e:
                logger.exception("Broadcast copy failed to %s: %s", tgt, e)
        set_state(user_id, None)
        await message.reply_text(f"✅ Broadcast sent to {len(targets)} targets.", reply_markup=start_inline_keyboard())
        return

    # default fallback
    # ignore other plain messages to avoid spam
    return

# ---------- remove target command (alternative) ----------
@bot.on_message(filters.command("remove_target") & filters.private)
async def remove_target_cmd(client, message):
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)
    if len(args) != 2:
        await message.reply_text("Usage: /remove_target <target_id_or_@username>")
        return
    target = args[1].strip()
    try:
        val = int(target) if not target.startswith("@") else target
        remove_target(user_id, val)
        await message.reply_text(f"✅ Removed target: {target}", reply_markup=start_inline_keyboard())
    except ValueError:
        await message.reply_text("Invalid target id.")

# ---------- Channel forwarder ----------
@bot.on_message(filters.channel)
async def channel_forwarder(client, message):
    chat_id = message.chat.id
    try:
        # find all users who set this as source and have active True
        cursor = links_col.find({
            "source_chat_id": {"$in": [chat_id, str(chat_id)]},
            "is_active": True,
            "targets": {"$ne": []}
        })
    except Exception as e:
        logger.exception("DB query failed in forwarder: %s", e)
        return

    for link in cursor:
        targets = link.get("targets") or []
        for tgt in targets:
            try:
                await message.copy(chat_id=tgt)
                logger.info("Forwarded message from %s -> %s for user %s", chat_id, tgt, link.get("user_id"))
            except Exception as e:
                logger.exception("Forward error for mapping %s -> %s : %s", chat_id, tgt, e)

# ---------- ping ----------
@bot.on_message(filters.command("ping") & filters.private)
async def ping_cmd(client, message):
    t0 = time.time()
    m = await message.reply_text("Pinging...")
    dt = int((time.time() - t0) * 1000)
    await m.edit_text(f"Pong! {dt} ms")

# ---------- run ----------
def run_bot():
    logger.info("Starting Pyrogram client...")
    try:
        bot.run()
    except Exception as e:
        logger.exception("Bot crashed: %s", e)
        raise

if __name__ == "__main__":
    Thread(target=run_health_server, daemon=True).start()
    logger.info("Health server started on port %s", os.environ.get("PORT", "8000"))
    run_bot()
