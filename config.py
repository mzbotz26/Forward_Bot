# config.py

import os

# --- Telegram Bot Configuration ---
# Telegram Bot Token, जिसे BotFather से प्राप्त किया जाता है।
BOT_TOKEN = os.getenv("")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN Environment Variable सेट नहीं है।")

# --- MongoDB Configuration ---
# MongoDB कनेक्शन स्ट्रिंग (URI), जिसे MongoDB Atlas या आपके सर्वर से प्राप्त किया जाता है।
MONGO_URI = os.getenv("mongodb+srv://ybawaskar1987:bBpiCuWZ5RLKuuzg@mzfilestore.ah4tr.mongodb.net/?retryWrites=true&w=majority&appName=mzfilestore")
if not MONGO_URI:
    raise ValueError("MONGO_URI Environment Variable सेट नहीं है।")

# MongoDB Database का नाम जहाँ चैनल IDs सेव होंगी।
DB_NAME = "mzfilestore"

# MongoDB Collection का नाम जहाँ Source और Target चैनल पेयर्स सेव होंगे।
COLLECTION_NAME = "channel_pairs"

