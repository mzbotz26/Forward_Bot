import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("13441344"))
API_HASH = os.getenv("2f10533d9068507d0c10bf1074527167")
BOT_TOKEN = os.getenv("7771472205:AAENcUwaWSrT_zx2W8agFA_BS5auhOn7pN4")

MONGO_URI = os.getenv("mongodb+srv://Anant:Anant@movieforu.09ibn.mongodb.net/?retryWrites=true&w=majority&appName=Movieforu")
DB_NAME = "forwarder_db"
COLLECTION = "users"
