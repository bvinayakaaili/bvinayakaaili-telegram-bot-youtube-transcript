"""
app.py – Flask REST API + Telegram bot runner
"""
import os
import json
import threading
import asyncio
import logging
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

from services.db import init_db, SessionLocal, Video, Session as UserSession, ChatMessage, ApiLog
from services.youtube import extract_video_id, fetch_transcript, get_video_metadata
from services.ai import generate_summary, LANGUAGE_NAMES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins=["http://localhost:3000", "http://localhost:5173", "*"])
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret")


# ─────────────────────────────────────────────────────────────
# HEALTH
# ─────────────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})


# ─────────────────────────────────────────────────────────────
# DASHBOARD STATS
# ─────────────────────────────────────────────────────────────

@app.route("/api/stats")
def get_stats():
    db = SessionLocal()
    try:
        total_videos   = db.query(Video).count()
        total_sessions = db.query(UserSession).count()
        total_messages = db.query(ChatMessage).count()
        recent_videos  = db.query(Video).order_by(Video.created_at.desc()).limit(5).all()

        # Messages in last 24h
        cutoff = datetime.utcnow() - timedelta(hours=24)
        messages_today = db.query(ChatMessage).filter(ChatMessage.created_at >= cutoff).count()

        return jsonify({
            "total_videos": total_videos,
            "total_sessions": total_sessions,
            "total_messages": total_messages,
            "messages_today": messages_today,
            "recent_videos": [
                {
                    "video_id": v.video_id,
                    "title": v.title,
                    "channel": v.channel,
                    "thumbnail": v.thumbnail_url,
                    "created_at": v.created_at.isoformat() if v.created_at else None,
                }
                for v in recent_videos
            ],
        })
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────
# VIDEOS
# ─────────────────────────────────────────────────────────────

@app.route("/api/videos")
def get_videos():
    db = SessionLocal()
    try:
        page  = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 20))
        offset = (page - 1) * limit

        videos = db.query(Video).order_by(Video.created_at.desc()).offset(offset).limit(limit).all()
        total  = db.query(Video).count()

        return jsonify({
            "videos": [
                {
                    "video_id": v.video_id,
                    "title": v.title,
                    "channel": v.channel,
                    "thumbnail": v.thumbnail_url,
                    "duration_secs": v.duration_secs,
                    "summary": v.summary_en,
                    "core_insight": v.core_insight,
                    "key_points": json.loads(v.key_points or "[]"),
                    "created_at": v.created_at.isoformat() if v.created_at else None,
                }
                for v in videos
            ],
            "total": total,
            "page": page,
            "pages": (total + limit - 1) // limit,
        })
    finally:
        db.close()


@app.route("/api/videos/<video_id>")
def get_video(video_id):
    db = SessionLocal()
    try:
        video = db.query(Video).filter_by(video_id=video_id).first()
        if not video:
            return jsonify({"error": "Video not found"}), 404

        return jsonify({
            "video_id": video.video_id,
            "title": video.title,
            "channel": video.channel,
            "thumbnail": video.thumbnail_url,
            "duration_secs": video.duration_secs,
            "summary": video.summary_en,
            "core_insight": video.core_insight,
            "key_points": json.loads(video.key_points or "[]"),
            "timestamps": json.loads(video.timestamps or "[]"),
            "created_at": video.created_at.isoformat() if video.created_at else None,
        })
    finally:
        db.close()


@app.route("/api/videos/<video_id>/messages")
def get_video_messages(video_id):
    db = SessionLocal()
    try:
        msgs = (
            db.query(ChatMessage)
            .filter_by(video_id=video_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(50)
            .all()
        )
        return jsonify([
            {
                "role": m.role,
                "content": m.content,
                "language": m.language,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in reversed(msgs)
        ])
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────
# PROCESS VIDEO (web UI trigger)
# ─────────────────────────────────────────────────────────────

@app.route("/api/process", methods=["POST"])
def process_video():
    data = request.json or {}
    url  = data.get("url", "").strip()
    lang = data.get("language", "en")

    if not url:
        return jsonify({"error": "URL is required"}), 400

    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({"error": "Invalid YouTube URL"}), 400

    # Check cache
    db = SessionLocal()
    try:
        cached = db.query(Video).filter_by(video_id=video_id).first()
        if cached and cached.summary_en:
            return jsonify({
                "cached": True,
                "video_id": video_id,
                "title": cached.title,
                "channel": cached.channel,
                "thumbnail": cached.thumbnail_url,
                "summary": cached.summary_en,
                "key_points": json.loads(cached.key_points or "[]"),
                "timestamps": json.loads(cached.timestamps or "[]"),
                "core_insight": cached.core_insight,
            })
    finally:
        db.close()

    # Full pipeline
    transcript_data = fetch_transcript(video_id)
    if transcript_data.get("error"):
        error_map = {
            "transcripts_disabled": "Transcripts are disabled for this video.",
            "video_unavailable": "This video is unavailable or private.",
            "no_transcript": "No transcript found for this video.",
        }
        return jsonify({"error": error_map.get(transcript_data["error"], transcript_data["error"])}), 422

    metadata = get_video_metadata(video_id)
    summary  = generate_summary(transcript_data["text"], metadata["title"], lang)

    # Save
    db = SessionLocal()
    try:
        video = Video(
            video_id=video_id,
            title=metadata.get("title", ""),
            channel=metadata.get("channel", ""),
            duration_secs=metadata.get("duration_secs", 0),
            thumbnail_url=metadata.get("thumbnail_url", ""),
            transcript=transcript_data.get("text", ""),
            summary_en=summary.get("summary_paragraph", ""),
            key_points=json.dumps(summary.get("key_points", [])),
            timestamps=json.dumps(summary.get("timestamps", [])),
            core_insight=summary.get("core_insight", ""),
        )
        db.add(video)
        db.commit()
    finally:
        db.close()

    return jsonify({
        "cached": False,
        "video_id": video_id,
        "title": metadata.get("title"),
        "channel": metadata.get("channel"),
        "thumbnail": metadata.get("thumbnail_url"),
        "summary": summary.get("summary_paragraph"),
        "key_points": summary.get("key_points", []),
        "timestamps": summary.get("timestamps", []),
        "core_insight": summary.get("core_insight"),
        "action_points": summary.get("action_points", []),
    })


# ─────────────────────────────────────────────────────────────
# SESSIONS
# ─────────────────────────────────────────────────────────────

@app.route("/api/sessions")
def get_sessions():
    db = SessionLocal()
    try:
        sessions = db.query(UserSession).order_by(UserSession.updated_at.desc()).limit(50).all()
        return jsonify([
            {
                "telegram_id": s.telegram_id,
                "username": s.username,
                "current_video": s.current_video,
                "language": LANGUAGE_NAMES.get(s.language, s.language),
                "message_count": s.message_count,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            }
            for s in sessions
        ])
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────
# BOT RUNNER (background thread)
# ─────────────────────────────────────────────────────────────

def run_bot():
    from bot import create_bot_app
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    bot_app = create_bot_app()
    logger.info("Starting Telegram bot (polling)...")
    bot_app.run_polling(drop_pending_updates=True)


# ─────────────────────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    logger.info("Database initialized")

    # Start bot in background thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    port = int(os.getenv("FLASK_PORT", 5000))
    logger.info(f"Flask API running on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)