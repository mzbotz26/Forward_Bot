import os

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://Anant:Anant@movieforu.09ibn.mongodb.net/?retryWrites=true&w=majority&appName=Movieforu")   # IMPORTANT: set this in Heroku
DB_NAME = os.getenv("DB_NAME", "forwarder")
COLLECTION = os.getenv("COLLECTION", "links")
