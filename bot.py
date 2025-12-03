import asyncio
import logging
import time

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from motor.motor_asyncio import AsyncIOMotorClient

from config import API_ID, API_HASH, BOT_TOKEN, MONGODB_URI, DB_NAME

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------- MongoDB setup ----------
mongo_client = AsyncIOMotorClient(MONGODB_URI)
db = mongo_client[DB_NAME]
links_col = db["links"]          # channel mapping
states_col = db["user_states"]   # user input states


# ---------- Pyrogram client ----------
bot = Client(
    "forwarder-bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)


# ---------- Helper functions ----------

async def get_link(user_id: int) -> dict:
    doc = await links_col.find_one({"user_id": user_id})
    if not doc:
        doc = {
            "user_id": user_id,
            "source_chat_id": None,
            "target_chat_id": None,
            "is_active": False,
        }
        await links_col.insert_one(doc)
    return doc


async def set_source(user_id: int, chat_id: int):
    await links_col.update_one(
        {"user_id": user_id},
        {"$set": {"source_chat_id": chat_id}},
        upsert=True,
    )


async def set_target(user_id: int, chat_id: int):
    await links_col.update_one(
        {"user_id": user_id},
        {"$set": {"target_chat_id": chat_id}},
        upsert=True,
    )


async def set_active(user_id: int, value: bool):
    await links_col.update_one(
        {"user_id": user_id},
        {"$set": {"is_active": value}},
        upsert=True,
    )


async def set_state(user_id: int, state: str | None):
    if state is None:
        await states_col.delete_one({"user_id": user_id})
        return
    await states_col.update_one(
        {"user_id": user_id},
        {"$set": {"state": state}},
        upsert=True,
    )


async def get_state(user_id: int) -> str | None:
    doc = await states_col.find_one({"user_id": user_id})
    return doc["state"] if doc else None


def start_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Source", callback_data="set_source"),
                InlineKeyboardButton("Target", callback_data="set_target"),
            ],
            [
                InlineKeyboardButton("Start", callback_data="toggle_start"),
            ],
        ]
    )


# ---------- Handlers ----------

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

        if not src or not tgt:
            await query.answer("Pehle source aur target set karo.", show_alert=True)
            return

        new_value = not bool(link.get("is_active"))
        await set_active(user_id, new_value)

        await query.answer(
            "Forwarding started." if new_value else "Forwarding stopped.",
            show_alert=True,
        )

        link = await get_link(user_id)
        text = (
            "Forward Bot Setup\n\n"
            f"Source: {link.get('source_chat_id')}\n"
            f"Target: {link.get('target_chat_id')}\n"
            f"Active: {link.get('is_active')}"
        )
        await query.message.edit_text(text, reply_markup=start_keyboard())


@bot.on_message(filters.private & filters.text)
async def private_text_handler(client, message):
    user_id = message.from_user.id
    state = await get_state(user_id)
    text = message.text.strip()

    if state == "await_source":
        if text.startswith("@"):
            chat_id = text  # username string store
        else:
            try:
                chat_id = int(text)
            except ValueError:
                await message.reply_text("Galat ID/username. Dubara bhejo.")
                return

        await set_source(user_id, chat_id)
        await set_state(user_id, None)
        await message.reply_text(
            f"Source set: {chat_id}\n\nAb /start karke Target set karo.",
            reply_markup=start_keyboard(),
        )

    elif state == "await_target":
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
        await message.reply_text(
            f"Target set: {chat_id}\n\nAb /start karke Start button dabao.",
            reply_markup=start_keyboard(),
        )
    else:
        await message.reply_text(
            "Setup ke liye /start use karo.",
            reply_markup=start_keyboard(),
        )


# ---------- Forwarding from source to target ----------

@bot.on_message(filters.channel)
async def channel_forwarder(client, message):
    chat_id = message.chat.id

    # Jo bhi user ne is chat ko source rakha hai, un sab ke mappings nikaalo
    cursor = links_col.find(
        {
            "source_chat_id": {"$in": [chat_id, str(chat_id)]},
            "is_active": True,
            "target_chat_id": {"$ne": None},
        }
    )

    async for link in cursor:
        target = link["target_chat_id"]
        try:
            await message.forward(target)
        except Exception as e:
            logger.error("Forward error for user %s: %s", link["user_id"], e)


# ---------- Ping command (optional) ----------

@bot.on_message(filters.command("ping") & filters.private)
async def ping_cmd(client, message):
    start = time.time()
    msg = await message.reply_text("Pinging...")
    delta = (time.time() - start) * 1000
    await msg.edit_text(f"Pong! {int(delta)} ms")


# ---------- Main ----------

if __name__ == "__main__":
    logger.info("Bot starting...")
    bot.run()
