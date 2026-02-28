"""
bot.py – Telegram bot with full command support
"""
import os
import json
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)
from telegram.constants import ParseMode, ChatAction

from services.youtube import extract_video_id, fetch_transcript, get_video_metadata
from services.ai import (
    generate_summary, answer_question,
    detect_language_request, generate_deep_dive, generate_action_points,
    LANGUAGE_NAMES,
)
from services.db import SessionLocal, Video, Session as UserSession, ChatMessage, init_db

logger = logging.getLogger(__name__)

# ── Session cache (in-memory, backed by DB) ───────────────────
_sessions: dict[str, dict] = {}


def _get_session(telegram_id: str) -> dict:
    if telegram_id not in _sessions:
        db = SessionLocal()
        try:
            sess = db.query(UserSession).filter_by(telegram_id=telegram_id).first()
            if sess:
                _sessions[telegram_id] = {
                    "video_id": sess.current_video,
                    "language": sess.language,
                    "history": [],
                }
            else:
                _sessions[telegram_id] = {"video_id": None, "language": "en", "history": []}
        finally:
            db.close()
    return _sessions[telegram_id]


def _save_session(telegram_id: str, username: str = ""):
    sess_data = _sessions.get(telegram_id, {})
    db = SessionLocal()
    try:
        sess = db.query(UserSession).filter_by(telegram_id=telegram_id).first()
        if not sess:
            sess = UserSession(telegram_id=telegram_id, username=username)
            db.add(sess)
        sess.current_video = sess_data.get("video_id")
        sess.language = sess_data.get("language", "en")
        db.commit()
    finally:
        db.close()


def _get_cached_video(video_id: str) -> Video | None:
    db = SessionLocal()
    try:
        return db.query(Video).filter_by(video_id=video_id).first()
    finally:
        db.close()


def _save_video(video_id: str, metadata: dict, transcript_data: dict, summary: dict) -> Video:
    db = SessionLocal()
    try:
        video = db.query(Video).filter_by(video_id=video_id).first()
        if not video:
            video = Video(video_id=video_id)
            db.add(video)
        video.title = metadata.get("title", "")
        video.channel = metadata.get("channel", "")
        video.duration_secs = metadata.get("duration_secs", 0)
        video.thumbnail_url = metadata.get("thumbnail_url", "")
        video.transcript = transcript_data.get("text", "")
        video.summary_en = summary.get("summary_paragraph", "")
        video.key_points = json.dumps(summary.get("key_points", []))
        video.timestamps = json.dumps(summary.get("critical_timestamps", []))
        video.core_insight = summary.get("core_insight", "")
        db.commit()
        db.refresh(video)
        return video
    finally:
        db.close()


def _save_message(telegram_id: str, video_id: str, role: str, content: str, language: str):
    db = SessionLocal()
    try:
        msg = ChatMessage(
            telegram_id=telegram_id,
            video_id=video_id,
            role=role,
            content=content,
            language=language,
        )
        db.add(msg)
        db.commit()
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _format_summary_message(summary: dict, metadata: dict) -> str:
    title = metadata.get("title", "YouTube Video")
    channel = metadata.get("channel", "")
    duration = metadata.get("duration_secs", 0)
    dur_str = f"{duration // 60}:{duration % 60:02d}" if duration else "N/A"

    key_points = summary.get("key_points", [])
    timestamps = summary.get("critical_timestamps", [])
    core_insight = summary.get("core_insight", "")
    summary_para = summary.get("summary_paragraph", "")

    def _normalize_field(field):
        if field is None:
            return ""
        if isinstance(field, str):
            return field
        # If it's a dict/list, try to make a short readable string
        try:
            if isinstance(field, dict):
                # Prefer existing keys if present
                if "summary_paragraph" in field:
                    return field["summary_paragraph"]
                if "core_insight" in field:
                    return field["core_insight"]
                if "key_points" in field:
                    return "\n".join(str(p) for p in field.get("key_points", []))
            if isinstance(field, list):
                return "\n".join(str(x) for x in field)
            return json.dumps(field, ensure_ascii=False)
        except Exception:
            return str(field)

    points_text = "\n".join(f"  • {_escape(p)}" for p in key_points[:5])
    
    ts_lines = []
    for t in timestamps[:5]:
        if isinstance(t, dict):
            time_str = _escape(t.get("time", ""))
            label_str = _escape(t.get("label", ""))
            ts_lines.append(f"  ⏱ {time_str} — {label_str}")
        else:
            ts_lines.append(f"  ⏱ {_escape(str(t))}")
    ts_text = "\n".join(ts_lines)

    # Normalize possibly-structured fields into readable strings
    core_insight_text = _normalize_field(core_insight)
    summary_para_text = _normalize_field(summary_para)

    # Build suggested questions
    questions_list = summary.get("suggested_questions", [])
    if questions_list and isinstance(questions_list, list):
        questions_text = "\n".join(f"  • {_escape(str(q))}" for q in questions_list[:4])
    else:
        questions_text = '  • "What did they say about X?"'

    msg = f"""🎥 *{_escape(title)}*
📺 {_escape(channel)} · ⏱ {dur_str}

━━━━━━━━━━━━━━━━━━━━
📌 *Key Points*
{points_text}

🕐 *Critical Sections*
{ts_text if ts_text else "  No critical sections identified"}

🧠 *Core Takeaway*
{_escape(core_insight_text)}

📄 *Overview*
{_escape(summary_para_text)}

━━━━━━━━━━━━━━━━━━━━
💬 *Ask me anything about this video\\!*
Try asking:
{questions_text}
"""
    return msg


def _escape(text: str) -> str:
    """Escape MarkdownV2 special chars."""
    special = r'_*[]()~`>#+-=|{}.!'
    # Escape any character in 'special' with a backslash
    return "".join(f"\\{c}" if c in special else c for c in str(text))


LANGUAGE_KEYBOARD = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
        InlineKeyboardButton("🇮🇳 Hindi", callback_data="lang_hi"),
    ],
    [
        InlineKeyboardButton("Tamil", callback_data="lang_ta"),
        InlineKeyboardButton("Telugu", callback_data="lang_te"),
    ],
    [
        InlineKeyboardButton("Kannada", callback_data="lang_kn"),
        InlineKeyboardButton("Marathi", callback_data="lang_mr"),
    ],
])

def get_translate_keyboard(current_lang: str) -> InlineKeyboardMarkup:
    """Returns a dynamic inline keyboard excluding the current language and including English if needed."""
    buttons = []
    
    if current_lang != "en":
        buttons.append(InlineKeyboardButton("🇬🇧 English", callback_data="translate_en"))
    if current_lang != "hi":
        buttons.append(InlineKeyboardButton("🇮🇳 Hindi", callback_data="translate_hi"))
    if current_lang != "ta":
        buttons.append(InlineKeyboardButton("Tamil", callback_data="translate_ta"))
    if current_lang != "te":
        buttons.append(InlineKeyboardButton("Telugu", callback_data="translate_te"))
    if current_lang != "kn":
        buttons.append(InlineKeyboardButton("Kannada", callback_data="translate_kn"))
    if current_lang != "mr":
        buttons.append(InlineKeyboardButton("Marathi", callback_data="translate_mr"))
        
    # Group into rows of 2 or 3
    keyboard = []
    for i in range(0, len(buttons), 2):
        keyboard.append(buttons[i:i+2])
        
    # Add clear session button at the bottom
    keyboard.append([InlineKeyboardButton("🔄 Start New Session", callback_data="cmd_clear")])
        
    return InlineKeyboardMarkup(keyboard)


# ─────────────────────────────────────────────────────────────
# COMMAND HANDLERS
# ─────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    sess = _get_session(str(user.id))
    _save_session(str(user.id), user.username or "")

    await update.message.reply_text(
        f"👋 *Welcome, {_escape(user.first_name)}\\!*\n\n"
        "I'm your AI research assistant for YouTube videos\\.\n\n"
        "📎 *Send me any YouTube link* to get:\n"
        "  • Structured summary\n"
        "  • Key timestamps\n"
        "  • Core insights\n\n"
        "Then *ask me anything* about the video\\!\n\n"
        "🌐 I support *English* and *Indian languages* \\(Hindi, Tamil, Kannada, Telugu, Marathi\\)\\.\n\n"
        "*Commands:*\n"
        "/summary \\- Re\\-show summary\n"
        "/language \\- Change response language\n"
        "/deepdive \\- Detailed analysis\n"
        "/actionpoints \\- Extract action items\n"
        "/clear \\- Start fresh\n"
        "/help \\- Show this message",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, context)


async def cmd_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    sess = _get_session(user_id)

    if not sess.get("video_id"):
        await update.message.reply_text("❌ No video loaded. Send me a YouTube link first!")
        return

    video = _get_cached_video(sess["video_id"])
    if not video or not video.summary_en:
        await update.message.reply_text("⚠️ Summary not available. Please resend the video link.")
        return

    metadata = {
        "title": video.title,
        "channel": video.channel,
        "duration_secs": video.duration_secs,
    }
    summary = {
        "key_points": json.loads(video.key_points or "[]"),
        "critical_timestamps": json.loads(video.timestamps or "[]"),
        "core_insight": video.core_insight,
        "summary_paragraph": video.summary_en,
    }
    await update.message.reply_text(
        _format_summary_message(summary, metadata),
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=get_translate_keyboard(sess.get("language", "en")),
    )


async def cmd_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌐 *Select your preferred language:*",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=LANGUAGE_KEYBOARD,
    )


async def cmd_deepdive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    sess = _get_session(user_id)

    if not sess.get("video_id"):
        await update.message.reply_text("❌ No video loaded. Send me a YouTube link first!")
        return

    video = _get_cached_video(sess["video_id"])
    if not video:
        await update.message.reply_text("⚠️ Video not found. Please resend the link.")
        return

    status_msg = await update.message.reply_text("⏳ *Analyzing video for a deep dive... this might take a minute!*", parse_mode=ParseMode.MARKDOWN)
    
    try:
        analysis = generate_deep_dive(video.transcript, video.title, sess.get("language", "en"))
        await status_msg.delete()
        await update.message.reply_text(f"🔬 *Deep Dive Analysis*\n\n{analysis}", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Deep dive error: {e}")
        await status_msg.edit_text("❌ Something went wrong generating the deep dive.")


async def cmd_actionpoints(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    sess = _get_session(user_id)

    if not sess.get("video_id"):
        await update.message.reply_text("❌ No video loaded. Send me a YouTube link first!")
        return

    video = _get_cached_video(sess["video_id"])
    if not video:
        await update.message.reply_text("⚠️ Video not found. Please resend the link.")
        return

    status_msg = await update.message.reply_text("⏳ *Extracting action points... this might take a minute!*", parse_mode=ParseMode.MARKDOWN)
    
    try:
        actions = generate_action_points(video.transcript, video.title, sess.get("language", "en"))
        await status_msg.delete()
        await update.message.reply_text(f"✅ *Action Points*\n\n{actions}", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Action points error: {e}")
        await status_msg.edit_text("❌ Something went wrong generating action points.")


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    _sessions[user_id] = {"video_id": None, "language": "en", "history": []}
    _save_session(user_id, update.effective_user.username or "")
    await update.message.reply_text("🗑️ Session cleared! Send me a new YouTube link to get started.")


# ─────────────────────────────────────────────────────────────
# CALLBACK HANDLERS
# ─────────────────────────────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    await query.answer()

    if query.data.startswith("lang_"):
        lang_code = query.data.replace("lang_", "")
        sess = _get_session(user_id)
        sess["language"] = lang_code
        _save_session(user_id, query.from_user.username or "")
        lang_name = LANGUAGE_NAMES.get(lang_code, lang_code)
        await query.edit_message_text(f"✅ Language set to *{lang_name}*\nAll responses will now be in {lang_name}.", parse_mode=ParseMode.MARKDOWN)

    elif query.data.startswith("translate_"):
        lang_code = query.data.replace("translate_", "")
        sess = _get_session(user_id)
        sess["language"] = lang_code
        _save_session(user_id, query.from_user.username or "")
        
        lang_name = LANGUAGE_NAMES.get(lang_code, lang_code)
        video_id = sess.get("video_id")
        
        if not video_id:
            await query.edit_message_text("❌ No video loaded to translate.")
            return

        video = _get_cached_video(video_id)
        if not video:
            await query.edit_message_text("⚠️ Video data lost.")
            return

        await query.edit_message_text(f"⏳ *Translating summary to {lang_name}...*", parse_mode=ParseMode.MARKDOWN)
        
        # Reconstruct transcript data dictionary for the mapped pipeline
        pseudo_data_dict = {"text": video.transcript, "segments": []}
        summary = generate_summary(pseudo_data_dict, video.title, lang_code)
        
        metadata = {"title": video.title, "channel": video.channel, "duration_secs": video.duration_secs}
        
        await query.message.reply_text(
            f"🌐 Translated to *{_escape(lang_name)}*\\!\n\n" + _format_summary_message(summary, metadata),
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=get_translate_keyboard(lang_code),
        )

    elif query.data == "cmd_clear":
        sess = _get_session(user_id)
        _sessions[user_id] = {"video_id": None, "language": "en", "history": []}
        _save_session(user_id, query.from_user.username or "")
        
        # Edit the message to formally close the session out visually
        await query.message.reply_text("🗑️ **Session cleared!** Send me a new YouTube link to get started.", parse_mode=ParseMode.MARKDOWN)
        # Answer the callback to remove the loading spinner on the button
        await query.answer("Session Cleared!")


# ─────────────────────────────────────────────────────────────
# MAIN MESSAGE HANDLER
# ─────────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    text = update.message.text.strip()
    sess = _get_session(user_id)

    # ── Quick greeting/casual chat interceptor ────────────────
    lower_text = text.lower()
    if lower_text in ["hi", "hello", "hey", "start", "help"]:
        await update.message.reply_text(
            "👋 Hi there! I am your YouTube Summarizer Bot.\n\n"
            "To get started, simply **paste a YouTube link** here and I will generate a comprehensive summary for you!\n\n"
            "If you've already sent a link, you can ask me specific questions about the video.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # ── Language switch detection ──────────────────────────────
    lang_request = detect_language_request(text)
    if lang_request and any(kw in text.lower() for kw in ["summarize in", "explain in", "respond in", "translate to", "in hindi", "in tamil", "in kannada", "in telugu", "in marathi"]):
        sess["language"] = lang_request
        lang_name = LANGUAGE_NAMES.get(lang_request, lang_request)
        _save_session(user_id, user.username or "")

        # If they also have a video, re-summarize
        if sess.get("video_id"):
            video = _get_cached_video(sess["video_id"])
            if video:
                await update.message.chat.send_action(ChatAction.TYPING)
                
                # Reconstruct transcript data dictionary for the mapped pipeline
                pseudo_data_dict = {"text": video.transcript, "segments": []}
                summary = generate_summary(pseudo_data_dict, video.title, lang_request)
                
                metadata = {"title": video.title, "channel": video.channel, "duration_secs": video.duration_secs}
                await update.message.reply_text(
                    f"🌐 Switching to *{_escape(lang_name)}*\\!\n\n" + _format_summary_message(summary, metadata),
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                return
        await update.message.reply_text(f"✅ Language set to *{lang_name}*. Send a YouTube link to get started!", parse_mode=ParseMode.MARKDOWN)
        return

    # ── YouTube URL detection ─────────────────────────────────
    video_id = extract_video_id(text)
    if video_id:
        await _process_video(update, user_id, user.username or "", video_id, sess)
        return

    # ── Q&A mode ──────────────────────────────────────────────
    if sess.get("video_id"):
        await _handle_qa(update, user_id, text, sess)
        return

    # ── Fallback ──────────────────────────────────────────────
    await update.message.reply_text(
        "👆 Please send me a YouTube link first!\n\nExample:\nhttps://youtube.com/watch?v=dQw4w9WgXcQ"
    )


async def _process_video(update: Update, user_id: str, username: str, video_id: str, sess: dict):
    """Full pipeline: transcript → summary → respond."""

    # Force english for new video submissions unless explicitly translated
    sess["language"] = "en"
    
    # Check cache
    cached = _get_cached_video(video_id)
    if cached and cached.summary_en:
        sess["video_id"] = video_id
        sess["history"] = []
        _save_session(user_id, username)
        metadata = {"title": cached.title, "channel": cached.channel, "duration_secs": cached.duration_secs}
        summary = {
            "key_points": json.loads(cached.key_points or "[]"),
            "critical_timestamps": json.loads(cached.timestamps or "[]"),
            "core_insight": cached.core_insight,
            "summary_paragraph": cached.summary_en,
        }
        # Translate if needed
        lang = sess.get("language", "en")
        if lang != "en":
            from services.ai import translate_summary
            summary = translate_summary(summary, lang)

        await update.message.reply_text(
            "⚡ *Loaded from cache\\!*\n\n" + _format_summary_message(summary, metadata),
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=get_translate_keyboard(lang),
        )
        return

    # Processing message
    processing_msg = await update.message.reply_text(
        "⏳ *Processing your video\\.\\.\\.*\n\n"
        "1️⃣ Fetching transcript\\.\\.\\.\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )

    try:
        # Step 1: Transcript
        transcript_data = fetch_transcript(video_id)

        if transcript_data.get("error"):
            error_map = {
                "transcripts_disabled": "❌ Transcripts are disabled for this video.",
                "video_unavailable": "❌ This video is unavailable or private.",
                "no_transcript": "❌ No transcript found for this video.\n\nTry a video with captions enabled.",
                "rate_limited": "⏳ YouTube is rate-limiting requests. Please try again in a few moments.",
            }
            msg = error_map.get(transcript_data["error"], f"❌ Error: {transcript_data['error']}")
            await processing_msg.edit_text(msg)
            return

        await processing_msg.edit_text(
            "⏳ *Processing your video\\.\\.\\.*\n\n"
            "1️⃣ ✅ Transcript fetched\n"
            "2️⃣ Fetching metadata\\.\\.\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

        # Step 2: Metadata
        metadata = get_video_metadata(video_id)

        await processing_msg.edit_text(
            "⏳ *Processing your video\\.\\.\\.*\n\n"
            "1️⃣ ✅ Transcript fetched\n"
            "2️⃣ ✅ Metadata loaded\n"
            "3️⃣ Generating AI summary\\.\\.\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

        # Step 3: Summary
        lang = sess.get("language", "en")
        summary = generate_summary(transcript_data, metadata["title"], lang)

        # Step 4: Save
        _save_video(video_id, metadata, transcript_data, summary)
        sess["video_id"] = video_id
        sess["history"] = []
        _save_session(user_id, "")

        await processing_msg.delete()
        await update.message.reply_text(
            _format_summary_message(summary, metadata),
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=get_translate_keyboard(lang),
        )

        # Step 5: Pre-build FAISS index in the background (Non-blocking)
        # Skip if transcript is very short since AI context window easily handles it
        transcript_text = transcript_data.get("text", "")
        word_count = len(transcript_text.split())
        
        if word_count >= 500:
            import threading
            def _build_faiss_bg():
                try:
                    from services.retriever import build_index
                    build_index(video_id, transcript_text)
                except Exception as idx_err:
                    logger.warning(f"Background FAISS index build failed (non-fatal): {idx_err}")

            threading.Thread(target=_build_faiss_bg, daemon=True).start()
        else:
            logger.info(f"Skipping FAISS for {video_id} (short: {word_count} words)")

    except Exception as e:
        logger.error(f"Video processing error: {e}")
        await processing_msg.edit_text(
            "❌ Something went wrong while processing this video.\n\n"
            f"Error: {str(e)[:200]}\n\nPlease try again."
        )


async def _handle_qa(update: Update, user_id: str, question: str, sess: dict):
    """Handle Q&A for a loaded video."""
    video_id = sess["video_id"]
    video = _get_cached_video(video_id)

    if not video:
        await update.message.reply_text("⚠️ Video data lost. Please resend the YouTube link.")
        return

    status_msg = await update.message.reply_text("⏳ *Thinking...*", parse_mode=ParseMode.MARKDOWN)

    history = sess.get("history", [])
    lang = sess.get("language", "en")

    answer, usage = answer_question(
        question=question,
        transcript=video.transcript,
        title=video.title,
        history=history,
        language=lang,
        video_id=video_id,   # ← enables FAISS semantic retrieval
    )

    # Update history
    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": answer})
    sess["history"] = history[-20:]  # keep last 10 exchanges

    # Persist to DB
    _save_message(user_id, video_id, "user", question, lang)
    _save_message(user_id, video_id, "assistant", answer, lang)

    await status_msg.delete()
    await update.message.reply_text(_escape(answer), parse_mode=ParseMode.MARKDOWN_V2)


# ─────────────────────────────────────────────────────────────
# APP FACTORY
# ─────────────────────────────────────────────────────────────

def create_bot_app():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN not set")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("summary", cmd_summary))
    app.add_handler(CommandHandler("language", cmd_language))
    app.add_handler(CommandHandler("deepdive", cmd_deepdive))
    app.add_handler(CommandHandler("actionpoints", cmd_actionpoints))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app