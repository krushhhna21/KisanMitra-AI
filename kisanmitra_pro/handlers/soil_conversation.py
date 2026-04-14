"""
KisanMitra — Soil Conversation Handler (v2 — Hybrid Fusion Engine)
Multi-step /soilstart wizard that collects pH, N, P, K, Organic Matter,
and an OPTIONAL crop photo. Generates a unified GoI Soil Health Card
using XGBoost + AgroMonitoring + Plantix/Vision fusion.
Saves the full report to the soil_reports table.
"""
from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
)
from config import GROQ_CHAT_MODEL
from database.db import get_land_details, get_farmer, save_soil_report
from services.soil_fusion import generate_unified_soil_report

# Conversation states (added ASK_PHOTO)
ASK_PH, ASK_N, ASK_P, ASK_K, ASK_OM, ASK_PHOTO = range(6)


def _float_or_none(text: str):
    try:
        return float(text.strip().replace(",", "."))
    except ValueError:
        return None


def _detect_language(user_id: int) -> str:
    """Get farmer's preferred language from DB, default Hindi."""
    try:
        farmer = get_farmer(user_id)
        return farmer.get("language", "hi") or "hi"
    except Exception:
        return "hi"


def _lang_text(lang: str, hi: str, mr: str, en: str) -> str:
    """Return text in farmer's language."""
    if lang == "mr":
        return mr
    elif lang == "en":
        return en
    return hi


# ── Step 0: /soilstart ────────────────────────────────────────────────────────
async def soilstart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    context.user_data["soil"] = {}
    lang = _detect_language(user_id)
    context.user_data["soil"]["lang"] = lang

    # Greet + instructions
    lands = get_land_details(user_id=user_id)
    if lands:
        land = lands[0]
        context.user_data["soil"]["land_id"] = land["id"]
        context.user_data["soil"]["crop"]    = land.get("crop_type", "")
        context.user_data["soil"]["location"] = f"{land.get('village', '')}, {land.get('district', '')}"
        field_info = f"\n📍 Field: *{land['village']}, {land['district']}* | Crop: *{land['crop_type']}*"
    else:
        context.user_data["soil"]["land_id"] = 0
        field_info = _lang_text(lang,
            "\n_(Koi khet registered nahi — kisanmitra dashboard pe register karein)_",
            "\n_(शेत नोंदणी नाही — kisanmitra dashboard वर नोंदणी करा)_",
            "\n_(No field registered yet — register at kisanmitra dashboard)_"
        )

    greeting = _lang_text(lang,
        f"🧪 *Soil Report Wizard*\nMitti ki jaanch ke result daalein — main analysis karoonga!{field_info}\n\n"
        "*Step 1/6:* Mitti ka *pH* kya hai?\n_(e.g. 6.5)_\n\n/cancel — Rok dein",
        f"🧪 *माती अहवाल विझार्ड*\nमातीच्या चाचणीचे निकाल टाका — मी विश्लेषण करतो!{field_info}\n\n"
        "*Step 1/6:* मातीचा *pH* किती आहे?\n_(उदा. 6.5)_\n\n/cancel — थांबा",
        f"🧪 *Soil Report Wizard*\nEnter your soil test results — I'll analyze them!{field_info}\n\n"
        "*Step 1/6:* What is the soil *pH*?\n_(e.g. 6.5)_\n\n/cancel — Stop"
    )

    await update.message.reply_text(greeting, parse_mode="Markdown")
    return ASK_PH


# ── Step 1: pH ────────────────────────────────────────────────────────────────
async def ask_ph(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = _float_or_none(update.message.text)
    lang = context.user_data.get("soil", {}).get("lang", "hi")

    if val is None or not (3 <= val <= 10):
        msg = _lang_text(lang,
            "⚠️ Sahi pH daalen (3.0 – 10.0), e.g. *6.8*",
            "⚠️ योग्य pH टाका (3.0 – 10.0), उदा. *6.8*",
            "⚠️ Enter valid pH (3.0 – 10.0), e.g. *6.8*"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
        return ASK_PH

    context.user_data["soil"]["ph"] = val
    msg = _lang_text(lang,
        f"✅ pH = *{val}*\n\n*Step 2/6:* Nitrogen *(N)* kitna hai? _(kg/ha, e.g. 240)_",
        f"✅ pH = *{val}*\n\n*Step 2/6:* नायट्रोजन *(N)* किती आहे? _(kg/ha, उदा. 240)_",
        f"✅ pH = *{val}*\n\n*Step 2/6:* Nitrogen *(N)* value? _(kg/ha, e.g. 240)_"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")
    return ASK_N


# ── Step 2: Nitrogen ─────────────────────────────────────────────────────────
async def ask_n(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = _float_or_none(update.message.text)
    lang = context.user_data.get("soil", {}).get("lang", "hi")

    if val is None or val < 0:
        msg = _lang_text(lang,
            "⚠️ Sahi Nitrogen daalen (kg/ha), e.g. *240*",
            "⚠️ योग्य Nitrogen टाका (kg/ha), उदा. *240*",
            "⚠️ Enter valid Nitrogen (kg/ha), e.g. *240*"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
        return ASK_N

    context.user_data["soil"]["n"] = val
    msg = _lang_text(lang,
        f"✅ N = *{val}* kg/ha\n\n*Step 3/6:* Phosphorus *(P)* kitna hai? _(kg/ha, e.g. 15)_",
        f"✅ N = *{val}* kg/ha\n\n*Step 3/6:* फॉस्फोरस *(P)* किती आहे? _(kg/ha, उदा. 15)_",
        f"✅ N = *{val}* kg/ha\n\n*Step 3/6:* Phosphorus *(P)* value? _(kg/ha, e.g. 15)_"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")
    return ASK_P


# ── Step 3: Phosphorus ───────────────────────────────────────────────────────
async def ask_p(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = _float_or_none(update.message.text)
    lang = context.user_data.get("soil", {}).get("lang", "hi")

    if val is None or val < 0:
        msg = _lang_text(lang,
            "⚠️ Sahi Phosphorus daalen (kg/ha), e.g. *15*",
            "⚠️ योग्य Phosphorus टाका (kg/ha), उदा. *15*",
            "⚠️ Enter valid Phosphorus (kg/ha), e.g. *15*"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
        return ASK_P

    context.user_data["soil"]["p"] = val
    msg = _lang_text(lang,
        f"✅ P = *{val}* kg/ha\n\n*Step 4/6:* Potassium *(K)* kitna hai? _(kg/ha, e.g. 180)_",
        f"✅ P = *{val}* kg/ha\n\n*Step 4/6:* पोटॅशियम *(K)* किती आहे? _(kg/ha, उदा. 180)_",
        f"✅ P = *{val}* kg/ha\n\n*Step 4/6:* Potassium *(K)* value? _(kg/ha, e.g. 180)_"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")
    return ASK_K


# ── Step 4: Potassium ────────────────────────────────────────────────────────
async def ask_k(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = _float_or_none(update.message.text)
    lang = context.user_data.get("soil", {}).get("lang", "hi")

    if val is None or val < 0:
        msg = _lang_text(lang,
            "⚠️ Sahi Potassium daalen (kg/ha), e.g. *180*",
            "⚠️ योग्य Potassium टाका (kg/ha), उदा. *180*",
            "⚠️ Enter valid Potassium (kg/ha), e.g. *180*"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
        return ASK_K

    context.user_data["soil"]["k"] = val
    msg = _lang_text(lang,
        f"✅ K = *{val}* kg/ha\n\n*Step 5/6:* Organic Matter *(OM)* kitni hai? _(%, e.g. 1.2)_\n"
        "Pata nahi? *0* daalen.",
        f"✅ K = *{val}* kg/ha\n\n*Step 5/6:* सेंद्रिय पदार्थ *(OM)* किती आहे? _(%, उदा. 1.2)_\n"
        "माहित नाही? *0* टाका.",
        f"✅ K = *{val}* kg/ha\n\n*Step 5/6:* Organic Matter *(OM)* percentage? _(%, e.g. 1.2)_\n"
        "Don't know? Enter *0*."
    )
    await update.message.reply_text(msg, parse_mode="Markdown")
    return ASK_OM


# ── Step 5: Organic Matter → ask photo ────────────────────────────────────────
async def ask_om(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = _float_or_none(update.message.text)
    lang = context.user_data.get("soil", {}).get("lang", "hi")

    if val is None or val < 0:
        msg = _lang_text(lang,
            "⚠️ Sahi OM % daalen, e.g. *1.2* ya *0*",
            "⚠️ योग्य OM % टाका, उदा. *1.2* किंवा *0*",
            "⚠️ Enter valid OM %, e.g. *1.2* or *0*"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
        return ASK_OM

    context.user_data["soil"]["om"] = val

    msg = _lang_text(lang,
        f"✅ OM = *{val}%*\n\n*Step 6/6:* 📸 Fasal ki photo bhejein agar disease/kamzori dikhi ho.\n"
        "Photo nahi hai? Type karein /skip",
        f"✅ OM = *{val}%*\n\n*Step 6/6:* 📸 पिकाचा फोटो पाठवा जर रोग/कमतरता दिसत असेल.\n"
        "फोटो नाही? /skip टाईप करा",
        f"✅ OM = *{val}%*\n\n*Step 6/6:* 📸 Send a crop photo if you see any disease/deficiency.\n"
        "No photo? Type /skip"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")
    return ASK_PHOTO


# ── Step 6a: Photo received → Generate full report ───────────────────────────
async def handle_soil_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Farmer sent a crop photo — run full fusion with vision."""
    lang = context.user_data.get("soil", {}).get("lang", "hi")

    await context.bot.send_chat_action(update.effective_chat.id, "typing")

    processing_msg = _lang_text(lang,
        "📸 Photo mil gayi! 🔬 AI Soil + Vision analysis ho raha hai... ⏳\n_(30-40 seconds)_",
        "📸 फोटो मिळाला! 🔬 AI माती + व्हिजन विश्लेषण चालू आहे... ⏳\n_(30-40 सेकंद)_",
        "📸 Photo received! 🔬 AI Soil + Vision analysis in progress... ⏳\n_(30-40 seconds)_"
    )
    await update.message.reply_text(processing_msg, parse_mode="Markdown")

    try:
        photo = update.message.photo[-1]
        photo_file = await context.bot.get_file(photo.file_id)
        image_bytes = bytes(await photo_file.download_as_bytearray())
    except Exception as e:
        print(f"Soil photo download error: {e}")
        image_bytes = None

    return await _generate_final_report(update, context, image_bytes)


# ── Step 6b: /skip → Generate report without photo ───────────────────────────
async def skip_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Farmer skipped photo — run fusion without vision."""
    lang = context.user_data.get("soil", {}).get("lang", "hi")

    await context.bot.send_chat_action(update.effective_chat.id, "typing")

    processing_msg = _lang_text(lang,
        "🔬 *AI Soil Analysis ho raha hai (XGBoost + Satellite)...* ⏳",
        "🔬 *AI माती विश्लेषण चालू (XGBoost + सॅटेलाईट)...* ⏳",
        "🔬 *AI Soil Analysis in progress (XGBoost + Satellite)...* ⏳"
    )
    await update.message.reply_text(processing_msg, parse_mode="Markdown")

    return await _generate_final_report(update, context, image_bytes=None)


# ── Final Report Generator ───────────────────────────────────────────────────
async def _generate_final_report(update: Update, context: ContextTypes.DEFAULT_TYPE, image_bytes=None):
    """Generate and send the unified soil health card."""
    soil = context.user_data.get("soil", {})
    user_id = update.effective_user.id
    lang = soil.get("lang", "hi")

    ph = soil.get("ph", 7.0)
    n  = soil.get("n", 0)
    p  = soil.get("p", 0)
    k  = soil.get("k", 0)
    om = soil.get("om", 0)
    crop    = soil.get("crop", "")
    land_id = soil.get("land_id", 0)
    location = soil.get("location", "Maharashtra")
    farmer_name = update.effective_user.first_name or "Kisan"

    # Get farmer's lat/lon
    farmer = get_farmer(user_id)
    lat = farmer.get("lat", 18.4088)
    lon = farmer.get("lon", 76.5604)
    if not location or location == "Maharashtra":
        location = farmer.get("location", "Maharashtra")

    # ── Run the fusion engine ────────────────────────────────────────────
    try:
        result = generate_unified_soil_report(
            n=n, p=p, k=k, ph=ph,
            moisture=40.0, ec=0.5,
            lat=lat, lon=lon, location=location,
            image_bytes=image_bytes,
            farmer_name=farmer_name,
            crop_type=crop,
            language=lang,
        )
    except Exception as e:
        print(f"Fusion engine error: {e}")
        # Graceful fallback — at least show something
        error_msg = _lang_text(lang,
            "⚠️ Analysis mein dikkat aayi. Basic data save ho gaya hai.\nThodi der baad /soilcard try karein.",
            "⚠️ विश्लेषणात अडचण आली. मूलभूत डेटा सेव्ह झाला.\nथोड्या वेळाने /soilcard वापरा.",
            "⚠️ Analysis error. Basic data saved.\nTry /soilcard again shortly."
        )
        await update.message.reply_text(error_msg, parse_mode="Markdown")
        context.user_data.pop("soil", None)
        return ConversationHandler.END

    # Save to DB
    rec_text = result.get("formatted_card", "") + "\n\n" + result.get("ai_summary", "")
    try:
        save_soil_report(
            land_id=land_id, user_id=user_id, email="",
            ph=ph, nitrogen=n, phosphorus=p, potassium=k,
            organic_matter=om, moisture=0, ec=0,
            recommendation=rec_text,
        )
    except Exception as e:
        print(f"Soil save error: {e}")

    # Send the card
    card = result.get("formatted_card", "")
    ai_summary = result.get("ai_summary", "")

    # Telegram has 4096 char limit — split if needed
    if len(card) + len(ai_summary) + 30 <= 4096:
        full_msg = f"<pre>{card}</pre>\n\n💡 <b>AI Summary:</b>\n{ai_summary}"
        await update.message.reply_text(full_msg, parse_mode="HTML")
    else:
        await update.message.reply_text(f"<pre>{card}</pre>", parse_mode="HTML")
        await update.message.reply_text(f"💡 <b>AI Summary:</b>\n{ai_summary}", parse_mode="HTML")

    # Closing message
    close_msg = _lang_text(lang,
        "━━━━━━━━━━━━━━━━━━━━\n_✅ Report saved! 3 AI sources ka data merge ho gaya._\n"
        "_📊 /soilcard — Kabhi bhi dekhein | 💬 Koi sawaal?_",
        "━━━━━━━━━━━━━━━━━━━━\n_✅ अहवाल सेव्ह! 3 AI स्रोतांचा डेटा एकत्र झाला._\n"
        "_📊 /soilcard — कधीही पहा | 💬 काही प्रश्न?_",
        "━━━━━━━━━━━━━━━━━━━━\n_✅ Report saved! Data merged from 3 AI sources._\n"
        "_📊 /soilcard — View anytime | 💬 Any questions?_"
    )
    await update.message.reply_text(close_msg, parse_mode="Markdown")

    context.user_data.pop("soil", None)
    return ConversationHandler.END


# ── Cancel ────────────────────────────────────────────────────────────────────
async def cancel_soil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("soil", {}).get("lang", "hi")
    context.user_data.pop("soil", None)

    msg = _lang_text(lang,
        "❌ Soil report wizard band kiya. Jab chahein /soilstart karein. 🌾",
        "❌ माती अहवाल विझार्ड बंद केला. कधीही /soilstart करा. 🌾",
        "❌ Soil report wizard cancelled. Run /soilstart anytime. 🌾"
    )
    await update.message.reply_text(msg)
    return ConversationHandler.END


# ── Exported ConversationHandler ──────────────────────────────────────────────
soil_conversation_handler = ConversationHandler(
    entry_points=[CommandHandler("soilstart", soilstart)],
    states={
        ASK_PH:    [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_ph)],
        ASK_N:     [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_n)],
        ASK_P:     [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_p)],
        ASK_K:     [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_k)],
        ASK_OM:    [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_om)],
        ASK_PHOTO: [
            MessageHandler(filters.PHOTO, handle_soil_photo),
            CommandHandler("skip", skip_photo),
            MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: skip_photo(u, c)),
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel_soil)],
    allow_reentry=True,
)
