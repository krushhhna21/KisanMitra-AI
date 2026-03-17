from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from database.db import get_farmer, get_analytics
from services.weather import get_weather
from services.schemes import get_crop_calendar, find_schemes
from services.mandi import get_mandi_prices
from services.satellite import get_crop_health


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()

    farmer = get_farmer(user_id)
    lat = farmer.get("lat", 18.4088)
    lon = farmer.get("lon", 76.5604)
    location = farmer.get("location", "Latur")

    if query.data == "weather":
        w = get_weather(lat, lon, location)
        await query.message.reply_text(w["summary"], parse_mode="Markdown")

    elif query.data == "calendar":
        await query.message.reply_text(get_crop_calendar(), parse_mode="Markdown")

    elif query.data == "mandi":
        await query.message.reply_text("💰 Kaun si fasal ka bhav?\nExample: *pyaaz, tamatar, gehu, soyabean*", parse_mode="Markdown")

    elif query.data == "schemes":
        await query.message.reply_text("🏛️ Kaun si yojana?\nExample: *PM-KISAN, fasal bima, kisan credit card*", parse_mode="Markdown")

    elif query.data == "satellite":
        await query.message.reply_text("🛰️ NASA satellite analysis ho raha hai... ⏳")
        result = get_crop_health(lat, lon, location)
        await query.message.reply_text(result, parse_mode="Markdown")

    elif query.data == "set_location":
        markup = ReplyKeyboardMarkup(
            [[KeyboardButton("📍 Location Bhejein", request_location=True)]],
            one_time_keyboard=True, resize_keyboard=True
        )
        await query.message.reply_text("📍 Apna location bhejein!", reply_markup=markup)

    elif query.data == "photo_help":
        await query.message.reply_text(
            "📸 *Fasal ki photo bhejein!*\nDisease/pest turant pahchan kar dunga. 🔬\n\nPhoto bhejna → diagnosis → ilaaj",
            parse_mode="Markdown"
        )

    elif query.data == "my_stats":
        stats = get_analytics()
        await query.message.reply_text(
            f"""📊 *KisanMitra AI — Impact Dashboard*

👨‍🌾 Total Farmers: *{stats['total_farmers']}*
💬 Total Queries: *{stats['total_queries']}*
🐛 Pest Reports: *{stats['total_pest_reports']}*

_Har sawaal ek kisan ki madad!_ 🌾""",
            parse_mode="Markdown"
        )

    elif query.data == "soil_start":
        await query.message.reply_text(
            "🧪 *Soil Report Wizard Start!*\n\n"
            "Apni mitti ki jaanch ke result daalein aur main AI analysis karoonga.\n\n"
            "*Shuru karein:* /soilstart",
            parse_mode="Markdown"
        )

    elif query.data == "my_field":
        from handlers.commands import myfield_cmd
        await myfield_cmd(update, context)
