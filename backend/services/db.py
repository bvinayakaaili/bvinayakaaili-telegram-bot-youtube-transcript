"""
db.py – SQLAlchemy models + session factory
"""
import os
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Text,
    DateTime, Boolean, Float
)
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///youtube_bot.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    echo=False,
)

SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
Base = declarative_base()


# ─────────────────────────────────────────────
class Video(Base):
    __tablename__ = "videos"

    id            = Column(Integer, primary_key=True, index=True)
    video_id      = Column(String(20), unique=True, index=True, nullable=False)
    title         = Column(String(500))
    channel       = Column(String(255))
    duration_secs = Column(Integer)
    thumbnail_url = Column(String(500))
    transcript    = Column(Text)          # raw full transcript
    summary_en    = Column(Text)          # cached English summary
    key_points    = Column(Text)          # JSON list
    timestamps    = Column(Text)          # JSON list
    core_insight  = Column(Text)
    created_at    = Column(DateTime, default=datetime.utcnow)
    last_accessed = Column(DateTime, default=datetime.utcnow)


class Session(Base):
    """One row per Telegram user – holds conversation state."""
    __tablename__ = "sessions"

    id            = Column(Integer, primary_key=True)
    telegram_id   = Column(String(50), unique=True, index=True)
    username      = Column(String(255))
    current_video = Column(String(20))    # video_id
    language      = Column(String(10), default="en")
    message_count = Column(Integer, default=0)
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id          = Column(Integer, primary_key=True)
    telegram_id = Column(String(50), index=True)
    video_id    = Column(String(20))
    role        = Column(String(10))      # user | assistant
    content     = Column(Text)
    language    = Column(String(10), default="en")
    created_at  = Column(DateTime, default=datetime.utcnow)


class ApiLog(Base):
    __tablename__ = "api_logs"

    id           = Column(Integer, primary_key=True)
    endpoint     = Column(String(100))
    tokens_in    = Column(Integer, default=0)
    tokens_out   = Column(Integer, default=0)
    latency_ms   = Column(Float)
    success      = Column(Boolean, default=True)
    created_at   = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()