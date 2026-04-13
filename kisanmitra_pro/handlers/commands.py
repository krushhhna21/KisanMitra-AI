from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from database.db import upsert_farmer, get_farmer, toggle_alerts, get_land_details, get_soil_reports, update_farmer_email
from services.weather import get_weather
from services.schemes import get_crop_calendar, find_schemes
from services.mandi import get_mandi_prices
from services.satellite import get_crop_health
from services.soil_fusion import generate_quick_soil_card


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
         InlineKeyboardButton("📊 My Stats", callback_data="my_stats")],
        [InlineKeyboardButton("🧪 Soil Test", callback_data="soil_start"),
         InlineKeyboardButton("🌍 My Field", callback_data="my_field")],
    ]

    await update.effective_message.reply_text(
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
    await update.effective_message.reply_text("""🌾 *KisanMitra AI — Help*

*💬 Text:* Koi bhi sawaal Hindi/Marathi/English mein
*🗣️ Voice:* Baat karein — main samjhunga
*📸 Photo:* Bimaar fasal photo → turant diagnosis
*🛰️ /satellite* — NASA satellite se crop health
*🧪 /soilstart* — Soil report wizard (pH, NPK)
*🌍 /myfield* — Aapke khet ki jaankari

*Commands:*
/start /weather /calendar /mandi
/schemes /satellite /alerts /setlocation
/soilstart /myfield /help""",
        parse_mode="Markdown")


async def weather_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    farmer = get_farmer(update.effective_user.id)
    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    w = get_weather(farmer.get("lat", 18.4088), farmer.get("lon", 76.5604), farmer.get("location", "Latur"))
    await update.effective_message.reply_text(w["summary"], parse_mode="Markdown")


async def calendar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    await update.effective_message.reply_text(get_crop_calendar(), parse_mode="Markdown")


async def mandi_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("💰 Kaun si fasal ka bhav?\nExample: *pyaaz, tamatar, gehu, soyabean*", parse_mode="Markdown")


async def schemes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("🏛️ Kaun si yojana?\nExample: *PM-KISAN, fasal bima, soil health card*", parse_mode="Markdown")


async def satellite_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    farmer = get_farmer(update.effective_user.id)
    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    await update.effective_message.reply_text("🛰️ NASA satellite se aapke khet ka analysis ho raha hai... ⏳")
    result = get_crop_health(
        farmer.get("lat", 18.4088),
        farmer.get("lon", 76.5604),
        farmer.get("location", "Latur")
    )
    await update.effective_message.reply_text(result, parse_mode="Markdown")


async def alerts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    enabled = toggle_alerts(user_id)
    if enabled:
        await update.effective_message.reply_text("🔔 *Subah ke alerts ON!*\nRoz 7 baje mausam + farming tip milegi. 🌅", parse_mode="Markdown")
    else:
        await update.effective_message.reply_text("🔕 *Alerts band.*\nPhir ON karne ke liye /alerts.", parse_mode="Markdown")


async def setlocation_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    markup = ReplyKeyboardMarkup(
        [[KeyboardButton("📍 Apni Location Bhejein", request_location=True)]],
        one_time_keyboard=True, resize_keyboard=True
    )
    await update.effective_message.reply_text(
        "📍 *Location bhejein — sahi mausam ke liye!*",
        parse_mode="Markdown", reply_markup=markup
    )


async def myfield_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show farmer's registered land details and latest soil report."""
    user_id = update.effective_user.id
    farmer = get_farmer(user_id)
    email = farmer.get("email", "")
    
    # Try looking up by email first (web dashboard), fallback to user_id
    lands = get_land_details(email=email) if email else get_land_details(user_id=user_id)
    reports = get_soil_reports(email=email, limit=1) if email else get_soil_reports(user_id=user_id, limit=1)

    if not lands:
        await update.effective_message.reply_text(
            "🌍 *Koi khet registered nahi!*\n\n"
            "Dashboard pe jaake apna khet register karein:\n"
            "🔗 _kisanmitra-ai-g7rk.onrender.com_\n\n"
            "👉 Agar aapne wahan register kiya hai, toh pehle yahan apna email link karein:\n"
            "`/linkemail aapka@email.com`",
            parse_mode="Markdown"
        )
        return

    land = lands[0]
    msg  = (
        f"🌍 *Aapka Khet*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 Gaon: *{land['village']}, {land['district']}*, {land['state']}\n"
        f"🌾 Fasal: *{land['crop_type']}*\n"
        f"🪨 Mitti: *{land['soil_type']}*\n"
        f"📐 Area: *{land['area_acres']} acres*\n"
    )

    if reports:
        r = reports[0]
        msg += (
            f"\n🧪 *Last Soil Report ({r['created_at'][:10]})*\n"
            f"pH: *{r['ph']}* | N: *{r['nitrogen_kg_ha']}* | P: *{r['phosphorus_kg_ha']}* | K: *{r['potassium_kg_ha']}*\n"
            f"OM: *{r['organic_matter_pct']}%* | EC: *{r['ec_ds_m']} dS/m*\n\n"
        )
        if r.get('recommendation'):
            snippet = r['recommendation'][:200]
            msg += f"🤖 _AI Tip: {snippet}..._"
    else:
        msg += "\n🧪 _Koi soil report nahi. Dashboard se add karein._"

    msg += "\n\n_Aapka sab data KisanMitra ke jawab mein istemal hota hai. 🌾_"
    await update.effective_message.reply_text(msg, parse_mode="Markdown")

async def linkemail_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Link a Google Dashboard email to this Telegram account"""
    if not context.args:
        await update.effective_message.reply_text("📧 Kripya apna dashboard email aise likhein:\n`/linkemail abc@example.com`", parse_mode="Markdown")
        return
        
    email = context.args[0].strip().lower()
    user_id = update.effective_user.id
    
    update_farmer_email(user_id, email)
    
    await update.effective_message.reply_text(f"✅ Aapka account `{email}` se link ho gaya hai!\nAb aap /myfield check kar sakte hain.", parse_mode="Markdown")


async def soilcard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show GoI Soil Health Card with latest report + live satellite data."""
    user_id = update.effective_user.id
    farmer = get_farmer(user_id)
    email = farmer.get("email", "")
    lang = farmer.get("language", "hi") or "hi"

    # Get latest soil report
    reports = get_soil_reports(email=email, limit=1) if email else get_soil_reports(user_id=user_id, limit=1)

    if not reports:
        if lang == "mr":
            msg = "🧪 *कोणताही माती अहवाल नाही!*\n\n/soilstart — माती चाचणी विझार्ड सुरू करा"
        elif lang == "en":
            msg = "🧪 *No soil report found!*\n\n/soilstart — Start soil test wizard"
        else:
            msg = "🧪 *Koi soil report nahi!*\n\n/soilstart — Soil test wizard shuru karein"
        await update.effective_message.reply_text(msg, parse_mode="Markdown")
        return

    r = reports[0]
    lat = farmer.get("lat", 18.4088)
    lon = farmer.get("lon", 76.5604)
    location = farmer.get("location", "Maharashtra")
    farmer_name = update.effective_user.first_name or "Kisan"

    await context.bot.send_chat_action(update.effective_chat.id, "typing")

    if lang == "mr":
        await update.effective_message.reply_text("🛰️ सॅटेलाईट डेटा + AI विश्लेषण चालू... ⏳")
    elif lang == "en":
        await update.effective_message.reply_text("🛰️ Fetching satellite data + AI analysis... ⏳")
    else:
        await update.effective_message.reply_text("🛰️ Satellite data + AI analysis ho raha hai... ⏳")

    try:
        card = generate_quick_soil_card(
            n=float(r.get('nitrogen_kg_ha', 0)),
            p=float(r.get('phosphorus_kg_ha', 0)),
            k=float(r.get('potassium_kg_ha', 0)),
            ph=float(r.get('ph', 7.0)),
            moisture=float(r.get('moisture_pct', 40)),
            ec=float(r.get('ec_ds_m', 0.5)),
            lat=lat, lon=lon, location=location,
            farmer_name=farmer_name,
            language=lang,
        )

        # Split if too long for Telegram
        if len(card) <= 4096:
            await update.effective_message.reply_text(card, parse_mode="Markdown")
        else:
            mid = len(card) // 2
            await update.effective_message.reply_text(card[:mid])
            await update.effective_message.reply_text(card[mid:], parse_mode="Markdown")

    except Exception as e:
        print(f"Soilcard error: {e}")
        if lang == "mr":
            msg = "⚠️ Soil card तयार करताना अडचण. /soilstart वापरून नवीन report तयार करा."
        elif lang == "en":
            msg = "⚠️ Error generating soil card. Use /soilstart to create a new report."
        else:
            msg = "⚠️ Soil card banane mein dikkat. /soilstart se naya report banayein."
        await update.effective_message.reply_text(msg)

