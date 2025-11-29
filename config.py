# config.py

import os
from dotenv import load_dotenv

# .env फ़ाइल से सभी variables को लोड करें
load_dotenv()

# --- Telegram Bot Configuration ---
# Telegram Bot Token, जिसे BotFather से प्राप्त किया जाता है।
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN Environment Variable सेट नहीं है।")

# --- MongoDB Configuration ---
# MongoDB कनेक्शन स्ट्रिंग (URI), जिसे MongoDB Atlas या आपके सर्वर से प्राप्त किया जाता है।
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI Environment Variable सेट नहीं है।")

# MongoDB Database का नाम जहाँ चैनल IDs सेव होंगी।
DB_NAME = "TelegramForwarderDB"

# MongoDB Collection का नाम जहाँ Source और Target चैनल पेयर्स सेव होंगे।
COLLECTION_NAME = "channel_pairs"

