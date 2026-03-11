from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from database.db import upsert_farmer, get_farmer, toggle_alerts
from services.weather import get_weather
from services.schemes import get_crop_calendar, find_schemes
from services.mandi import get_mandi_prices
from services.satellite import get_crop_health


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_farmer(user.id, user.first_name or "", user.username or "")

    keyboard = [
        [InlineKeyboardButton("🌤️ Mausam", callback_data="weather"),
         InlineKeyboardButton("📅 Calendar", callback_data="calendar")],
        [InlineKeyboardButton("💰 Mandi Bhav", callback_data="mandi"),
         InlineKeyboardButton("🏛️ Yojnayein", callback_data="schemes")],
        [InlineKeyboardButton("🛰️ Crop Health", callback_data="satellite"),
         InlineKeyboardButton("📍 Location Set", callback_data="set_location")],
        [InlineKeyboardButton("📸 Photo Diagnosis", callback_data="photo_help"),
         InlineKeyboardButton("📊 My Stats", callback_data="my_stats")]
    ]

    await update.message.reply_text(
        f"""🌾 *KisanMitra AI mein swagat hai, {user.first_name or 'Kisan Bhai'} ji!*
_Har khet ka saathi — Every farm's companion_ v2.0

Namaste! 🙏 Main aapka AI farming expert hoon.

🌱 Fasal advice | 📸 Photo diagnosis
🗣️ Voice message | 💰 Live mandi prices
🛰️ Satellite crop health | 🌤️ Local weather
📅 Crop calendar | 🏛️ Govt schemes
🔔 Daily 7 AM alerts

Sawaal likhein, photo ya voice bhejein! ✍️""",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""🌾 *KisanMitra AI — Help*

*💬 Text:* Koi bhi sawaal Hindi/Marathi/English mein
*🗣️ Voice:* Baat karein — main samjhunga
*📸 Photo:* Bimaar fasal photo → turant diagnosis
*🛰️ /satellite* — NASA satellite se crop health

*Commands:*
/start /weather /calendar /mandi
/schemes /satellite /alerts /setlocation /help""",
        parse_mode="Markdown")


async def weather_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    farmer = get_farmer(update.effective_user.id)
    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    w = get_weather(farmer.get("lat", 18.4088), farmer.get("lon", 76.5604), farmer.get("location", "Latur"))
    await update.message.reply_text(w["summary"], parse_mode="Markdown")


async def calendar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    await update.message.reply_text(get_crop_calendar(), parse_mode="Markdown")


async def mandi_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💰 Kaun si fasal ka bhav?\nExample: *pyaaz, tamatar, gehu, soyabean*", parse_mode="Markdown")


async def schemes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏛️ Kaun si yojana?\nExample: *PM-KISAN, fasal bima, soil health card*", parse_mode="Markdown")


async def satellite_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    farmer = get_farmer(update.effective_user.id)
    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    await update.message.reply_text("🛰️ NASA satellite se aapke khet ka analysis ho raha hai... ⏳")
    result = get_crop_health(
        farmer.get("lat", 18.4088),
        farmer.get("lon", 76.5604),
        farmer.get("location", "Latur")
    )
    await update.message.reply_text(result, parse_mode="Markdown")


async def alerts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    enabled = toggle_alerts(user_id)
    if enabled:
        await update.message.reply_text("🔔 *Subah ke alerts ON!*\nRoz 7 baje mausam + farming tip milegi. 🌅", parse_mode="Markdown")
    else:
        await update.message.reply_text("🔕 *Alerts band.*\nPhir ON karne ke liye /alerts.", parse_mode="Markdown")


async def setlocation_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    markup = ReplyKeyboardMarkup(
        [[KeyboardButton("📍 Apni Location Bhejein", request_location=True)]],
        one_time_keyboard=True, resize_keyboard=True
    )
    await update.message.reply_text(
        "📍 *Location bhejein — sahi mausam ke liye!*",
        parse_mode="Markdown", reply_markup=markup
    )
