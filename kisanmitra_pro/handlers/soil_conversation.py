"""
KisanMitra — Soil Conversation Handler
Multi-step /soilstart wizard that collects pH, N, P, K, Organic Matter
from the farmer via chat, generates a Groq AI recommendation,
and saves the report to the soil_reports table.
"""
from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
)
from groq import Groq
from config import GROQ_API_KEY, GROQ_CHAT_MODEL
from database.db import get_land_details, save_soil_report

groq_client = Groq(api_key=GROQ_API_KEY)

# Conversation states
ASK_PH, ASK_N, ASK_P, ASK_K, ASK_OM = range(5)


def _float_or_none(text: str):
    try:
        return float(text.strip().replace(",", "."))
    except ValueError:
        return None


def _generate_soil_rec(ph, n, p, k, om, crop=""):
    crop_ctx = f" for {crop}" if crop else ""
    prompt = f"""You are an expert soil scientist advising an Indian farmer{crop_ctx}.
Soil test: pH={ph}, N={n}kg/ha, P={p}kg/ha, K={k}kg/ha, OM={om}%

Give SHORT personalised soil health advice (max 180 words):
1. 🟢/🟡/🔴 Overall health rating
2. Key issues
3. Fertiliser fix (specific amounts)
4. Organic amendment (FYM/compost)
5. One most urgent action this week

Hindi/English mix. Use emojis. Bullet points."""
    try:
        res = groq_client.chat.completions.create(
            model=GROQ_CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=350,
            temperature=0.5,
        )
        return res.choices[0].message.content.strip()
    except Exception as e:
        return f"⚠️ AI analysis unavailable: {e}"


# ── Step 0: /soilstart ────────────────────────────────────────────────────────
async def soilstart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    context.user_data["soil"] = {}

    # Greet + instructions
    lands = get_land_details(user_id=user_id)
    if lands:
        land = lands[0]
        context.user_data["soil"]["land_id"] = land["id"]
        context.user_data["soil"]["crop"]    = land.get("crop_type", "")
        field_info = f"\n📍 Field: *{land['village']}, {land['district']}* | Crop: *{land['crop_type']}*"
    else:
        context.user_data["soil"]["land_id"] = 0
        field_info = "\n_(No field registered yet — you can register at kisanmitra.onrender.com)_"

    await update.message.reply_text(
        f"🧪 *Soil Report Wizard*\nMitti ki jaanch ke result daalein — main analysis karoonga!\n{field_info}\n\n"
        "*Step 1/5:* Mitti ka *pH* kya hai?\n_(e.g. 6.5)_\n\n/cancel — Rok dein",
        parse_mode="Markdown"
    )
    return ASK_PH


# ── Step 1: pH ────────────────────────────────────────────────────────────────
async def ask_ph(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = _float_or_none(update.message.text)
    if val is None or not (3 <= val <= 10):
        await update.message.reply_text("⚠️ Sahi pH daalen (3.0 – 10.0), e.g. *6.8*", parse_mode="Markdown")
        return ASK_PH
    context.user_data["soil"]["ph"] = val
    await update.message.reply_text(
        f"✅ pH = *{val}*\n\n*Step 2/5:* Nitrogen *(N)* kitna hai? _(kg/ha, e.g. 240)_",
        parse_mode="Markdown"
    )
    return ASK_N


# ── Step 2: Nitrogen ─────────────────────────────────────────────────────────
async def ask_n(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = _float_or_none(update.message.text)
    if val is None or val < 0:
        await update.message.reply_text("⚠️ Sahi Nitrogen daalen (kg/ha), e.g. *240*", parse_mode="Markdown")
        return ASK_N
    context.user_data["soil"]["n"] = val
    await update.message.reply_text(
        f"✅ N = *{val}* kg/ha\n\n*Step 3/5:* Phosphorus *(P)* kitna hai? _(kg/ha, e.g. 15)_",
        parse_mode="Markdown"
    )
    return ASK_P


# ── Step 3: Phosphorus ───────────────────────────────────────────────────────
async def ask_p(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = _float_or_none(update.message.text)
    if val is None or val < 0:
        await update.message.reply_text("⚠️ Sahi Phosphorus daalen (kg/ha), e.g. *15*", parse_mode="Markdown")
        return ASK_P
    context.user_data["soil"]["p"] = val
    await update.message.reply_text(
        f"✅ P = *{val}* kg/ha\n\n*Step 4/5:* Potassium *(K)* kitna hai? _(kg/ha, e.g. 180)_",
        parse_mode="Markdown"
    )
    return ASK_K


# ── Step 4: Potassium ────────────────────────────────────────────────────────
async def ask_k(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = _float_or_none(update.message.text)
    if val is None or val < 0:
        await update.message.reply_text("⚠️ Sahi Potassium daalen (kg/ha), e.g. *180*", parse_mode="Markdown")
        return ASK_K
    context.user_data["soil"]["k"] = val
    await update.message.reply_text(
        f"✅ K = *{val}* kg/ha\n\n*Step 5/5:* Organic Matter *(OM)* kitni hai? _(%, e.g. 1.2)_\n"
        "Pata nahi? *0* daalen.",
        parse_mode="Markdown"
    )
    return ASK_OM


# ── Step 5: Organic Matter → generate report ─────────────────────────────────
async def ask_om(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = _float_or_none(update.message.text)
    if val is None or val < 0:
        await update.message.reply_text("⚠️ Sahi OM % daalen, e.g. *1.2* ya *0*", parse_mode="Markdown")
        return ASK_OM

    soil = context.user_data["soil"]
    soil["om"] = val

    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    await update.message.reply_text("🔬 *AI Soil Analysis ho raha hai...* ⏳", parse_mode="Markdown")

    ph = soil["ph"]
    n  = soil["n"]
    p  = soil["p"]
    k  = soil["k"]
    om = soil["om"]
    crop    = soil.get("crop", "")
    land_id = soil.get("land_id", 0)
    user_id = update.effective_user.id

    rec = _generate_soil_rec(ph, n, p, k, om, crop)

    # Save to DB
    try:
        save_soil_report(
            land_id=land_id, user_id=user_id, email="",
            ph=ph, nitrogen=n, phosphorus=p, potassium=k,
            organic_matter=om, moisture=0, ec=0,
            recommendation=rec,
        )
    except Exception as e:
        print(f"Soil save error: {e}")

    summary = (
        f"🧪 *Soil Report Summary*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"pH: *{ph}* | N: *{n}* | P: *{p}* | K: *{k}* | OM: *{om}%*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{rec}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"_✅ Report saved! Ab KisanMitra aapki baat mein is data ka use karega._\n"
        f"_Zyada detail ke liye dashboard dekhein._"
    )

    await update.message.reply_text(summary, parse_mode="Markdown")
    context.user_data.pop("soil", None)
    return ConversationHandler.END


# ── Cancel ────────────────────────────────────────────────────────────────────
async def cancel_soil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("soil", None)
    await update.message.reply_text("❌ Soil report wizard band kiya. Jab chahein /soilstart karein. 🌾")
    return ConversationHandler.END


# ── Exported ConversationHandler ──────────────────────────────────────────────
soil_conversation_handler = ConversationHandler(
    entry_points=[CommandHandler("soilstart", soilstart)],
    states={
        ASK_PH: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_ph)],
        ASK_N:  [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_n)],
        ASK_P:  [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_p)],
        ASK_K:  [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_k)],
        ASK_OM: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_om)],
    },
    fallbacks=[CommandHandler("cancel", cancel_soil)],
    allow_reentry=True,
)
