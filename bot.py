import os
import html
import logging
import json
import urllib.request
import urllib.error
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set.")

API_URL = "https://api.dictionaryapi.dev/api/v2/entries/{lang}/{word}"
DEFAULT_LANG = "en"

LANGUAGES = {
    "en":    "🇬🇧 English",
    "pt-BR": "🇧🇷 Portuguese",
    "es":    "🇪🇸 Spanish",
    "fr":    "🇫🇷 French",
    "de":    "🇩🇪 German",
    "it":    "🇮🇹 Italian",
}

# ── API fetch (pure stdlib, no httpx) ────────────────────────────────────────
def fetch_word(word: str, lang: str) -> tuple:
    url = API_URL.format(lang=lang, word=word.lower().strip())
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PolyglotBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, list) and len(data) > 0:
                    return True, data
        return False, None
    except Exception as e:
        logger.error(f"API fetch failed: {e}")
        return False, None


# ── Result formatter ──────────────────────────────────────────────────────────
def build_result(data: list, lang: str) -> tuple:
    entry    = data[0]
    word     = entry.get("word", "")
    phonetic = entry.get("phonetic", "")
    meanings = entry.get("meanings", [])

    # Resolve audio URL
    audio_url = None
    for p in entry.get("phonetics", []):
        raw = p.get("audio", "")
        if raw:
            audio_url = raw if raw.startswith("http") else "https:" + raw
            break

    lines = [f"📖 <b>{html.escape(word.upper())}</b>"]
    if phonetic:
        lines.append(f"🔊 <code>{html.escape(phonetic)}</code>")
    lines.append(f"🌐 <i>{html.escape(LANGUAGES.get(lang, lang))}</i>")
    lines.append("━━━━━━━━━━━━━━━")

    for meaning in meanings[:3]:
        pos  = meaning.get("partOfSpeech", "").capitalize()
        defs = meaning.get("definitions", [])
        syns = meaning.get("synonyms", [])
        ants = meaning.get("antonyms", [])

        lines.append(f"\n<b>{html.escape(pos)}</b>")
        for i, d in enumerate(defs[:2], 1):
            defn_text = html.escape(d.get("definition", ""))
            example   = html.escape(d.get("example", ""))
            lines.append(f"{i}. {defn_text}")
            if example:
                lines.append(f'   💬 <i>"{example}"</i>')

        if syns:
            lines.append(f"✅ <b>Synonyms:</b> {html.escape(', '.join(syns[:5]))}")
        if ants:
            lines.append(f"❌ <b>Antonyms:</b> {html.escape(', '.join(ants[:5]))}")

    return "\n".join(lines), audio_url


# ── Keyboards ─────────────────────────────────────────────────────────────────
def lang_keyboard() -> InlineKeyboardMarkup:
    buttons, row = [], []
    for code, label in LANGUAGES.items():
        row.append(InlineKeyboardButton(label, callback_data=f"lang:{code}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


# ── Handlers ──────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = context.user_data.get("lang", DEFAULT_LANG)
    await update.message.reply_text(
        "👋 <b>Welcome to Polyglot Dictionary Bot!</b>\n\n"
        "I look up words in <b>6 languages</b> and return:\n\n"
        "📖  Full definitions\n"
        "💬  Example sentences\n"
        "✅  Synonyms\n"
        "❌  Antonyms\n"
        "🔊  Phonetic pronunciation + audio\n\n"
        f"Current language: <b>{LANGUAGES.get(lang, lang)}</b>\n\n"
        "Just <b>send any word</b> to get started.\n"
        "Use /lang to switch language.",
        parse_mode="HTML",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang_list = "\n".join(f"  • {v}" for v in LANGUAGES.values())
    await update.message.reply_text(
        "📚 <b>How to use this bot:</b>\n\n"
        "1.  Send any word → full definition\n"
        "2.  /lang → switch dictionary language\n"
        "3.  /start → welcome screen\n"
        "4.  /help → this message\n\n"
        f"<b>Supported languages:</b>\n{lang_list}",
        parse_mode="HTML",
    )


async def lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current = context.user_data.get("lang", DEFAULT_LANG)
    await update.message.reply_text(
        f"🌐 <b>Select a language:</b>\n\n"
        f"Currently using: <b>{LANGUAGES.get(current, current)}</b>",
        reply_markup=lang_keyboard(),
        parse_mode="HTML",
    )


async def lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    lang_code = query.data.split(":", 1)[1]
    if lang_code not in LANGUAGES:
        await query.answer("Unknown language.", show_alert=True)
        return
    context.user_data["lang"] = lang_code
    await query.edit_message_text(
        f"✅ Language switched to <b>{LANGUAGES[lang_code]}</b>\n\n"
        "Now send any word to look it up!",
        parse_mode="HTML",
    )


async def handle_word(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    word = update.message.text.strip()
    lang = context.user_data.get("lang", DEFAULT_LANG)

    clean = word.replace("-", "").replace(" ", "")
    if not clean.isalpha():
        await update.message.reply_text(
            "⚠️ Please send a word using letters only (no numbers or symbols)."
        )
        return

    if len(word.split()) > 3:
        await update.message.reply_text(
            "⚠️ Please look up one word (or short phrase) at a time."
        )
        return

    loading_msg = await update.message.reply_text("🔍 Looking up...")

    success, data = fetch_word(word, lang)

    if not success or not data:
        await loading_msg.edit_text(
            f"❌ <b>'{html.escape(word)}'</b> was not found "
            f"in <b>{LANGUAGES.get(lang, lang)}</b>.\n\n"
            "Try a different spelling or switch language with /lang",
            parse_mode="HTML",
        )
        return

    try:
        result_text, audio_url = build_result(data, lang)
        await loading_msg.edit_text(result_text, parse_mode="HTML")

        if audio_url:
            try:
                await update.message.reply_audio(
                    audio=audio_url,
                    caption=f"🔊 Pronunciation: <b>{html.escape(word)}</b>",
                    parse_mode="HTML",
                )
            except Exception as audio_err:
                logger.warning(f"Audio delivery failed: {audio_err}")

    except Exception as e:
        logger.error(f"Result build error: {e}")
        await loading_msg.edit_text(
            "⚠️ Something went wrong formatting the result. Please try again."
        )


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help",  help_command))
    app.add_handler(CommandHandler("lang",  lang_command))
    app.add_handler(CallbackQueryHandler(lang_callback, pattern="^lang:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_word))

    logger.info("✅ Polyglot Dictionary Bot is running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
