import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv(""))
API_HASH = os.getenv("")
BOT_TOKEN = os.getenv("")

MONGO_URI = os.getenv("")
DB_NAME = "forwarder_db"
COLLECTION = "users"
