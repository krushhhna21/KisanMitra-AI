import asyncio
import requests
from telegram import Update
from telegram.ext import ContextTypes
from agents.chat_agent import chat, generate_pest_advisory, _add_idempotency_hash
from agents.vision_agent import analyze_crop_photo
from agents.voice_agent import transcribe_voice
from services.mandi import get_mandi_prices
from services.schemes import find_schemes
from services.plantix import analyze_plant_health
from database.db import (
    log_query, upsert_farmer, update_farmer_location, add_pest_report, get_farmer,
    check_pest_outbreak, get_alert_users_by_location, get_soil_reports
)

MANDI_KEYWORDS = ["bhav", "price", "rate", "mandi", "bazar", "pyaaz", "tamatar",
                  "gehu", "soyabean", "chana", "aalu", "dhan", "khareed", "bechu"]
SCHEME_KEYWORDS = ["yojana", "scheme", "pm-kisan", "bima", "subsidy",
                   "sarkar", "government", "apply", "registration"]


def split_long_response(text: str, max_length: int = 4000) -> list:
    """
    PHASE 3 - Split long responses into multiple messages
    
    Telegram has 4096 char limit. If response too long, split intelligently:
    - Split at sentence boundaries (. ! ?)
    - Keep emojis with their sentences
    - Ensure each chunk is meaningful
    
    Returns: List of message chunks
    """
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    current_chunk = ""
    
    # Split by sentences
    sentences = text.replace('।', '.').split('. ')
    
    for sentence in sentences:
        test_chunk = current_chunk + sentence + '. '
        
        if len(test_chunk) > max_length:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence + '. '
        else:
            current_chunk = test_chunk
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks if chunks else [text]



async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message.text
    upsert_farmer(user.id, user.first_name or "", user.username or "")

    # PHASE 4: Idempotency check - prevent duplicate processing
    message_hash = hash(message)
    last_hash = context.user_data.get('last_message_hash')
    if last_hash == message_hash and context.user_data.get('last_response_sent'):
        # Same message just sent, skip
        return
    context.user_data['last_message_hash'] = message_hash

    # PHASE 3: Add typing indicator to prevent timeouts
    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    msg_lower = message.lower()

    if any(k in msg_lower for k in MANDI_KEYWORDS):
        await update.message.reply_text("💰 Mandi bhav check kar raha hoon... ⏳")
        reply = get_mandi_prices(message)
        log_query(user.id, "mandi", message, reply, "mandi")

    elif any(k in msg_lower for k in SCHEME_KEYWORDS):
        reply = find_schemes(message)
        log_query(user.id, "text", message, reply, "scheme")

    else:
        reply, intent, language = chat(user.id, message)
        log_query(user.id, "text", message, reply, intent, language)

    # PHASE 3: Split long responses to prevent truncation
    chunks = split_long_response(reply)
    
    for i, chunk in enumerate(chunks):
        try:
            await update.message.reply_text(chunk)
            # Add small delay between chunks if multiple
            if i < len(chunks) - 1:
                await asyncio.sleep(0.5)
        except Exception as e:
            print(f"Error sending message chunk {i+1}: {e}")
    
    # PHASE 4: Mark response as sent (idempotency)
    context.user_data['last_response_sent'] = True



async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_farmer(user.id, user.first_name or "", user.username or "")
    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    await update.message.reply_text("🗣️ Awaaz sun raha hoon... 🎧")

    # Step 1: Download audio
    try:
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        voice_bytes = await voice_file.download_as_bytearray()
    except Exception as e:
        print(f"Voice download error: {e}")
        await update.message.reply_text("🙏 Voice download nahi hua. Dobara bhejein.")
        return

    # Step 2: Transcribe
    text = transcribe_voice(bytes(voice_bytes))
    if not text:
        await update.message.reply_text("🙏 Awaaz samajh nahi aaya. Thoda seedha bolein ya text likhein.")
        return

    # Step 3: Get AI reply (no echo — voice assistants respond, not repeat)
    try:
        await context.bot.send_chat_action(update.effective_chat.id, "typing")
        reply, intent, language = chat(user.id, text)
        await update.message.reply_text(reply)
    except Exception as e:
        print(f"Voice chat error: {e}")
        await update.message.reply_text("🙏 Jawab dene mein dikkat hui. Thodi der baad try karein.")
        return

    # Step 4: Log (isolated — a DB error won't affect the user)
    try:
        log_query(user.id, "voice", text, reply, intent, language)
    except Exception as e:
        print(f"Voice log error (non-critical): {e}")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    farmer = get_farmer(user.id)
    lang = farmer.get("language", "hi") or "hi"

    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    await update.message.reply_text("📸 Photo mil gayi! Analysis ho raha hai... 🔍\n_(15-20 seconds)_", parse_mode="Markdown")

    try:
        photo = update.message.photo[-1]
        photo_file = await context.bot.get_file(photo.file_id)
        image_bytes = await photo_file.download_as_bytearray()

        # Primary analysis via existing vision agent (for display + pest logging)
        analysis, crop_detected, pest_detected = analyze_crop_photo(bytes(image_bytes))
        log_query(user.id, "photo", f"photo:{crop_detected}", analysis, "pest")

        # ── Enrichment: If farmer has soil data, add Plantix structured insights ─
        email = farmer.get("email", "")
        soil_reports = get_soil_reports(email=email, limit=1) if email else get_soil_reports(user_id=user.id, limit=1)

        if soil_reports:
            try:
                # Get structured diagnosis from Plantix/Groq Vision
                plantix_result = analyze_plant_health(bytes(image_bytes), language=lang)
                r = soil_reports[0]

                enrichment = []
                if plantix_result.get("disease", "None") != "None":
                    enrichment.append(f"\n🔬 *Detailed Diagnosis:* {plantix_result['disease']} ({plantix_result['severity']})")
                    enrichment.append(f"💊 *Treatment:* {plantix_result['treatment']}")
                if plantix_result.get("deficiency", "None") != "None":
                    enrichment.append(f"🧪 *Nutrient Deficiency:* {plantix_result['deficiency']}")

                enrichment.append(
                    f"\n📊 *Your Soil Data:* pH={r.get('ph','-')} | "
                    f"N={r.get('nitrogen_kg_ha','-')} | P={r.get('phosphorus_kg_ha','-')} | K={r.get('potassium_kg_ha','-')}"
                )
                enrichment.append(f"_Source: {plantix_result.get('source', 'AI Vision')}_")

                if enrichment:
                    analysis += "\n" + "\n".join(enrichment)
            except Exception as enrich_err:
                print(f"Photo enrichment error (non-critical): {enrich_err}")

        # Auto-log pest report if pest detected
        if pest_detected and pest_detected not in ["none", "unknown", ""]:
            add_pest_report(
                user_id=user.id,
                lat=farmer.get("lat", 18.4088),
                lon=farmer.get("lon", 76.5604),
                location=farmer.get("location", "Latur"),
                crop=crop_detected,
                pest=pest_detected,
                severity="medium",
                photo_id=photo.file_id
            )
            analysis += f"\n\n📍 _Yeh pest report community map mein add ho gaya. Aas-paas ke kisan alert honge!_ 🗺️"

            # Check if this crosses the threshold for a pest outbreak alert
            if check_pest_outbreak(farmer.get("location", "Latur"), pest_detected, days=7, threshold=3):
                alert_users = get_alert_users_by_location(farmer.get("location", "Latur"))
                
                if alert_users:
                    # Generate the advisory text with precautions and fertilizers
                    advisory = generate_pest_advisory(pest_detected, crop_detected, farmer.get("location", "Latur"))
                    
                    # Broadcast to affected users silently in the background
                    for auth_user in alert_users:
                        uid = auth_user["user_id"]
                        if uid != user.id:
                            try:
                                await context.bot.send_message(
                                    chat_id=uid,
                                    text=advisory,
                                    parse_mode="Markdown"
                                )
                                await asyncio.sleep(0.1)  # tiny delay to avoid hitting Telegram API limits instantly
                            except Exception as be:
                                print(f"Broadcast failed for {uid}: {be}")

        await update.message.reply_text(analysis, parse_mode="Markdown")
        await update.message.reply_text("💬 Koi aur sawaal? Main hamesha yahan hoon. 🌾")

    except Exception as e:
        print(f"Photo handler error: {e}")
        await update.message.reply_text("🙏 Photo process nahi hua. Dobara bhejein.")


async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    loc = update.message.location
    lat, lon = loc.latitude, loc.longitude

    try:
        geo_url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
        geo_res = requests.get(geo_url, headers={"User-Agent": "KisanMitraAI/2.0"}, timeout=5)
        addr = geo_res.json().get("address", {})
        location_name = addr.get("village") or addr.get("town") or addr.get("city") or addr.get("county") or "Aapka Gaon"
    except Exception as e:
        print(f"Geocoding error: {e}")
        location_name = "Aapka Gaon"

    update_farmer_location(user.id, lat, lon, location_name)

    from services.weather import get_weather
    w = get_weather(lat, lon, location_name)
    await update.message.reply_text(
        f"✅ *Location set: {location_name}!*\n\nAb sahi local mausam milega. 🎯\n\n{w['summary']}",
        parse_mode="Markdown"
    )
