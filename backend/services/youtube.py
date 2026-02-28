"""
youtube.py – transcript extraction + video metadata
"""
import re
import json
import logging
import time
from typing import Optional
from urllib.parse import urlparse, parse_qs

from youtube_transcript_api import (
    YouTubeTranscriptApi,
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)
from requests.exceptions import HTTPError

logger = logging.getLogger(__name__)

# ── Supported transcript languages (priority order) ──────────
LANG_PRIORITY = ["en", "hi", "ta", "te", "kn", "mr", "en-US", "en-GB"]


def extract_video_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from any valid URL format."""
    patterns = [
        r"(?:v=|\/videos\/|embed\/|youtu\.be\/|\/v\/|\/e\/|watch\?v%3D|watch\?feature=player_embedded&v=|%2Fvideos%2F|embed%\u200C\u200B2F|youtu\.be%2F|%2Fv%2F)([^#\&\?\n]*)",
        r"youtu\.be\/([^#\&\?\n]*)",
        r"youtube\.com\/shorts\/([^#\&\?\n]*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            vid = match.group(1).strip()
            if re.match(r"^[A-Za-z0-9_-]{11}$", vid):
                return vid
    return None


def get_video_metadata(video_id: str) -> dict:
    """
    Fetch lightweight metadata via yt-dlp (no API key needed).
    Falls back to minimal info if yt-dlp is unavailable.
    """
    try:
        import yt_dlp
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": False,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}", download=False
            )
            return {
                "title": info.get("title", "Unknown Title"),
                "channel": info.get("uploader", "Unknown Channel"),
                "duration_secs": info.get("duration", 0),
                "thumbnail_url": info.get("thumbnail", ""),
                "view_count": info.get("view_count", 0),
            }
    except Exception as e:
        logger.warning(f"yt-dlp metadata fetch failed: {e}")
        return {
            "title": f"YouTube Video ({video_id})",
            "channel": "Unknown",
            "duration_secs": 0,
            "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
            "view_count": 0,
        }

def fetch_transcript(video_id: str) -> dict:
    """
    Fetch transcript for a video with retry logic for rate limiting.
    Returns: { text, segments, language, word_count, error }
    """
    max_retries = 3
    for attempt in range(max_retries):
        result = _fetch_transcript_attempt(video_id)
        
        # If it's not a rate-limit error, return immediately
        if result.get("error") != "rate_limited":
            return result
        
        # On rate limit, back off exponentially
        if attempt < max_retries - 1:
            wait_time = 2 ** attempt
            logger.warning(f"Rate limited on attempt {attempt + 1}, waiting {wait_time}s before retry...")
            time.sleep(wait_time)
        else:
            logger.error(f"Rate limited after {max_retries} attempts, giving up")
            return {"error": "rate_limited", "text": None}
    
    return {"error": "rate_limited", "text": None}


def _fetch_transcript_attempt(video_id: str) -> dict:
    """
    Single attempt to fetch transcript for a video.
    Returns: { text, segments, language, word_count, error }
    """
    try:
        # Try new API style (v0.7+): YouTubeTranscriptApi.list()
        try:
            transcript_list = YouTubeTranscriptApi().list(video_id)
            
            # transcript_list is now a TranscriptList object
            transcript_obj = None
            detected_lang = "en"

            for lang in LANG_PRIORITY:
                try:
                    transcript_obj = transcript_list.find_transcript([lang])
                    detected_lang = lang
                    break
                except Exception:
                    continue

            if not transcript_obj:
                try:
                    all_transcripts = list(transcript_list)
                    if all_transcripts:
                        transcript_obj = all_transcripts[0]
                        detected_lang = transcript_obj.language_code
                except Exception:
                    pass

            if not transcript_obj:
                return {"error": "no_transcript", "text": None}

            segments = transcript_obj.fetch()

        except AttributeError:
            # Fallback for older API: YouTubeTranscriptApi.fetch()
            logger.warning(f"Using fallback API for {video_id}")
            segments = YouTubeTranscriptApi.fetch(video_id, languages=LANG_PRIORITY)
            detected_lang = "en"

        # Normalize segment format (dict or object)
        processed = []
        for s in segments:
            if isinstance(s, dict):
                processed.append({
                    "start": s.get("start", 0),
                    "text": s.get("text", ""),
                    "start_fmt": _format_time(s.get("start", 0)),
                })
            else:
                # Object format
                processed.append({
                    "start": getattr(s, 'start', 0),
                    "text": getattr(s, 'text', ''),
                    "start_fmt": _format_time(getattr(s, 'start', 0)),
                })

        if not processed:
            return {"error": "no_transcript", "text": None}

        full_text = " ".join(s["text"] for s in processed)

        return {
            "text": full_text,
            "segments": processed,
            "language": detected_lang,
            "word_count": len(full_text.split()),
            "error": None,
        }

    except TranscriptsDisabled:
        return {"error": "transcripts_disabled", "text": None}
    except VideoUnavailable:
        return {"error": "video_unavailable", "text": None}
    except NoTranscriptFound:
        return {"error": "no_transcript", "text": None}
    except HTTPError as e:
        if e.response.status_code == 429:
            logger.warning(f"Rate limited (429) fetching transcript for {video_id}")
            return {"error": "rate_limited", "text": None}
        logger.error(f"HTTP error fetching transcript for {video_id}: {e}")
        return _fetch_transcript_ytdlp(video_id)
    except Exception as e:
        logger.error(f"Transcript fetch error for {video_id}: {e}")
        # Try one more time with yt-dlp as fallback
        return _fetch_transcript_ytdlp(video_id)

def _fetch_transcript_ytdlp(video_id: str) -> dict:
    """
    Fallback transcript fetcher using yt-dlp.
    Used when youtube-transcript-api fails.
    """
    try:
        import yt_dlp
        import json as _json

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["en", "hi", "ta", "te", "kn"],
            "subtitlesformat": "json3",
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={video_id}",
                    download=False
                )
        except Exception as e:
            logger.warning(f"yt-dlp extraction for {video_id} failed: {e}")
            return {"error": "no_transcript", "text": None}

        # Try to get subtitles from info dict
        subtitles = info.get("subtitles", {}) or {}
        auto_subs = info.get("automatic_captions", {}) or {}

        # Prefer manual, then auto
        all_subs = {**auto_subs, **subtitles}

        for lang in ["en", "hi", "ta", "te", "kn"]:
            if lang not in all_subs:
                continue
                
            sub_data = all_subs[lang]
            # Find json3 or srv3 format
            for fmt in sub_data:
                try:
                    if fmt.get("ext") in ("json3", "srv3", "vtt"):
                        import urllib.request
                        url = fmt["url"]
                        with urllib.request.urlopen(url, timeout=10) as r:
                            raw = r.read().decode("utf-8")

                        # Parse json3 format
                        if fmt.get("ext") == "json3":
                            data = _json.loads(raw)
                            events = data.get("events", [])
                            segments = []
                            for ev in events:
                                if "segs" not in ev:
                                    continue
                                text = "".join(s.get("utf8", "") for s in ev["segs"]).strip()
                                if text and text != "\n":
                                    segments.append({
                                        "start": ev.get("tStartMs", 0) / 1000,
                                        "text": text,
                                        "start_fmt": _format_time(ev.get("tStartMs", 0) / 1000),
                                    })
                        else:
                            # vtt fallback — strip tags
                            import re
                            lines = raw.split("\n")
                            text_lines = [
                                re.sub(r"<[^>]+>", "", l).strip()
                                for l in lines
                                if l.strip() and "-->" not in l and not l.startswith("WEBVTT")
                            ]
                            segments = [{"start": 0, "text": t, "start_fmt": "0:00"} for t in text_lines if t]

                        if segments:
                            full_text = " ".join(s["text"] for s in segments)
                            logger.info(f"Successfully fetched transcript via yt-dlp for {video_id} in {lang}")
                            return {
                                "text": full_text,
                                "segments": segments,
                                "language": lang,
                                "word_count": len(full_text.split()),
                                "error": None,
                            }
                except Exception as e:
                    logger.debug(f"Failed to parse {lang} subtitle format for {video_id}: {e}")
                    continue

        logger.warning(f"yt-dlp fallback: no subtitles available for {video_id}")
        return {"error": "no_transcript", "text": None}

    except Exception as e:
        logger.error(f"yt-dlp transcript fallback also failed for {video_id}: {e}")
        return {"error": "no_transcript", "text": None}


def chunk_transcript(text: str, max_tokens: int = 8000) -> list[str]:
    """
    Split long transcripts into overlapping chunks for Q&A retrieval.
    Rough estimate: 1 token ≈ 4 chars.
    """
    max_chars = max_tokens * 4
    overlap = 500  # chars overlap between chunks

    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        # Try to break at sentence boundary
        if end < len(text):
            boundary = text.rfind(". ", start, end)
            if boundary != -1:
                end = boundary + 1
        chunks.append(text[start:end])
        start = end - overlap

    return chunks


def _format_time(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"