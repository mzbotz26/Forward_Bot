# bot.py

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
)
from pymongo import MongoClient
from config import BOT_TOKEN, MONGO_URI, DB_NAME, COLLECTION_NAME

# --- 1. MongoDB Setup ---
try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client[DB_NAME]
    channel_collection = db[COLLECTION_NAME]
    print("MongoDB से सफलतापूर्वक कनेक्ट हुआ।")
except Exception as e:
    print(f"MongoDB कनेक्शन त्रुटि: {e}")
    exit()

# --- 2. Database Functions ---

def get_user_data(user_id):
    """उपयोगकर्ता का डेटा MongoDB से प्राप्त करता है।"""
    return channel_collection.find_one({"user_id": user_id})

def update_user_data(user_id, updates):
    """उपयोगकर्ता के डेटा को MongoDB में अपडेट करता है।"""
    channel_collection.update_one(
        {"user_id": user_id},
        {"$set": updates},
        upsert=True  # अगर user_id मौजूद नहीं है तो नया रिकॉर्ड बनाएगा
    )

# --- 3. Handlers Functions ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start कमांड पर कीबोर्ड दिखाता है।"""
    keyboard = [
        [InlineKeyboardButton("🔗 Source Channel Set करें", callback_data='set_source')],
        [InlineKeyboardButton("🎯 Target Channel Set करें", callback_data='set_target')],
        [InlineKeyboardButton("▶️ Forwarding Start करें", callback_data='start_forwarding')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "नमस्ते! मैं चैनल कंटेंट फ़ॉरवर्डर बॉट हूँ।\n"
        "कृपया **Source** और **Target** चैनल सेट करें। चैनल सेट करने के लिए, **उस चैनल के किसी भी मैसेज को मुझे फ़ॉरवर्ड करें**।\n\n"
        "**चेतावनी:** सुनिश्चित करें कि मैं दोनों चैनलों में **एडमिन** हूँ!",
        reply_markup=reply_markup
    )
# 

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inline बटन क्लिक्स को संभालता है।"""
    query = update.callback_query
    await query.answer()  # Query का जवाब तुरंत दें

    user_id = query.from_user.id
    data = get_user_data(user_id)

    if query.data == 'set_source':
        # उपयोगकर्ता को source_pending स्थिति में सेट करें
        update_user_data(user_id, {"setting_mode": "source_pending"})
        await query.edit_message_text(
            "कृपया उस **Source Channel** से कोई भी मैसेज मुझे **फ़ॉरवर्ड** करें।"
        )
    
    elif query.data == 'set_target':
        # उपयोगकर्ता को target_pending स्थिति में सेट करें
        update_user_data(user_id, {"setting_mode": "target_pending"})
        await query.edit_message_text(
            "कृपया उस **Target Channel** से कोई भी मैसेज मुझे **फ़ॉरवर्ड** करें।"
        )

    elif query.data == 'start_forwarding':
        if not data or not data.get("source_channel_id") or not data.get("target_channel_id"):
            await query.edit_message_text(
                "Source और Target चैनल ID पहले सेट करें!"
            )
            return
        
        # Forwarding को एक्टिवेट करें
        update_user_data(user_id, {"is_active": True, "setting_mode": None})
        
        source_id = data.get("source_channel_id")
        target_id = data.get("target_channel_id")
        
        await query.edit_message_text(
            f"✅ **Forwarding शुरू हो गई है!**\n\n"
            f"Source ID: `{source_id}`\n"
            f"Target ID: `{target_id}`\n"
            f"अब Source चैनल पर आने वाले सभी मैसेज Target चैनल पर फ़ॉरवर्ड होंगे।"
        )

async def handle_forwarded_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """फ़ॉरवर्ड किए गए मैसेज से चैनल ID निकालता है।"""
    if not update.message.forward_from_chat:
        # अगर यह फ़ॉरवर्ड किया गया मैसेज नहीं है
        return

    user_id = update.message.from_user.id
    chat_id = update.message.forward_from_chat.id # फ़ॉरवर्ड किए गए चैनल की ID
    
    data = get_user_data(user_id)
    if not data or not data.get("setting_mode"):
        await update.message.reply_text("पहले `/start` कमांड चलाकर 'Source' या 'Target' बटन दबाएँ।")
        return

    mode = data.get("setting_mode")

    if mode == "source_pending":
        update_user_data(user_id, {"source_channel_id": chat_id, "setting_mode": None})
        await update.message.reply_text(
            f"✅ **Source Channel** सेट हो गया। ID: `{chat_id}`\n"
            "अब आप `/start` चलाकर **Target Channel** सेट कर सकते हैं या Forwarding शुरू कर सकते हैं।"
        )
    
    elif mode == "target_pending":
        update_user_data(user_id, {"target_channel_id": chat_id, "setting_mode": None})
        await update.message.reply_text(
            f"✅ **Target Channel** सेट हो गया। ID: `{chat_id}`\n"
            "अब आप `/start` चलाकर Forwarding शुरू कर सकते हैं।"
        )

async def handle_new_channel_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Source Channel से आने वाले नए मैसेज को Target Channel में फ़ॉरवर्ड करता है।"""
    
    # यह handler तभी ट्रिगर होगा जब कोई नया मैसेज किसी चैनल या ग्रुप में पोस्ट किया जाता है।
    current_chat_id = update.effective_chat.id
    message_id = update.message.message_id

    # सभी active channel pairs को ढूंढें
    active_pairs = channel_collection.find({"is_active": True})

    for pair in active_pairs:
        source_id = pair.get("source_channel_id")
        target_id = pair.get("target_channel_id")

        # यदि current_chat_id किसी active pair का source_id है
        if current_chat_id == source_id:
            try:
                # Target Channel में मैसेज फ़ॉरवर्ड करें
                await context.bot.forward_message(
                    chat_id=target_id,
                    from_chat_id=source_id,
                    message_id=message_id
                )
                print(f"मैसेज {message_id} को {source_id} से {target_id} पर फ़ॉरवर्ड किया गया।")
            except Exception as e:
                # त्रुटि को संभालें (उदा. बॉट एडमिन नहीं है, या चैनल ID गलत है)
                print(f"Forwarding Error: {e}")
                # चाहें तो यूजर को एरर मैसेज भेज सकते हैं
                # await context.bot.send_message(pair.get("user_id"), f"फॉरवर्डिंग में त्रुटि: {e}")

# --- 4. Main Function ---

def main() -> None:
    """बॉट को चलाता है।"""
    # Application बिल्ड करें
    application = Application.builder().token(BOT_TOKEN).build()

    # Handlers जोड़ें
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(button_callback))

    # फ़ॉरवर्ड किए गए मैसेज को हैंडल करें (चैनल ID सेट करने के लिए)
    application.add_handler(
        MessageHandler(
            filters.FORWARDED & filters.PRIVATE, 
            handle_forwarded_message
        )
    )

    # Source Channel से आने वाले नए मैसेज को हैंडल करें (फ़ॉरवर्डिंग के लिए)
    # filters.ChatType.CHANNEL का उपयोग करें ताकि केवल चैनल पोस्ट ही ट्रिगर हों
    application.add_handler(
        MessageHandler(
            filters.ALL & filters.ChatType.CHANNEL,
            handle_new_channel_message
        )
    )

    # बॉट को पोलिंग मोड में शुरू करें
    print("बॉट शुरू हो रहा है...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()


