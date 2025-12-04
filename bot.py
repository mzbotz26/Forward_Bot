from pyrogram import Client, filters
from pyrogram.types import ReplyKeyboardMarkup, KeyboardButton
from pymongo import MongoClient
from config import *

# ========== MONGO DB SETUP ==========
mongo = MongoClient(MONGO_URI)
db = mongo[DB_NAME]
users = db[COLLECTION]

# ========== TELEGRAM BOT SETUP ==========
bot = Client(
    "forwarder-bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ========== START BUTTONS ==========
main_buttons = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📥 Set Source Channel")],
        [KeyboardButton("📤 Set Target Channel")],
        [KeyboardButton("🚀 Start Bot")]
    ],
    resize_keyboard=True
)

# ========== START COMMAND ==========
@bot.on_message(filters.command("start"))
async def start(_, msg):
    user_id = msg.from_user.id

    # MongoDB में user entry create अगर न हो
    if not users.find_one({"user_id": user_id}):
        users.insert_one({"user_id": user_id, "source": None, "target": None})

    await msg.reply(
        "Welcome! 👋\n\nSet your Source & Target channels.",
        reply_markup=main_buttons
    )


# ========== SOURCE CHANNEL SET ==========
@bot.on_message(filters.text == "📥 Set Source Channel")
async def set_source(_, msg):
    await msg.reply("Source channel ID भेजें (जैसे: `-1001234567890`)")


@bot.on_message(filters.regex(r"^-100"))
async def save_channel(_, msg):
    user_id = msg.from_user.id
    text = msg.text

    if "source" not in text:
        users.update_one(
            {"user_id": user_id},
            {"$set": {"source": text}}
        )
        await msg.reply("✅ Source channel saved!")
        return


# ========== TARGET CHANNEL SET ==========
@bot.on_message(filters.text == "📤 Set Target Channel")
async def set_target(_, msg):
    await msg.reply("Target channel ID भेजें (जैसे: `-1001234567890`)")


@bot.on_message(filters.regex(r"^-100"))
async def save_target(_, msg):
    user_id = msg.from_user.id
    text = msg.text

    users.update_one(
        {"user_id": user_id},
        {"$set": {"target": text}}
    )
    await msg.reply("✅ Target channel saved!")


# ========== START BOT ==========
@bot.on_message(filters.text == "🚀 Start Bot")
async def start_forwarding(_, msg):
    user = users.find_one({"user_id": msg.from_user.id})

    if not user["source"] or not user["target"]:
        await msg.reply("❗ पहले Source और Target सेट करें!")
        return

    await msg.reply("Bot चालू हो चुका है! अब Source channel में पोस्ट करते ही Target में जाएगा।")



# ========== AUTO FORWARDER ==========
@bot.on_message(filters.channel)
async def auto_forwarder(client, msg):
    # सारे user configs लूप करें
    all_users = users.find()

    for user in all_users:
        source = str(user.get("source"))
        target = int(user.get("target"))

        # अगर यह उसी यूज़र का Source channel है
        if str(msg.chat.id) == source:
            try:
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
