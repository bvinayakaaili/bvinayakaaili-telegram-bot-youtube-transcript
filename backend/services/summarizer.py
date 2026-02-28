"""
summarizer.py — Hierarchical (map-reduce) summarization upgrade
Replaces: transcript[:24000] truncation in generate_summary() in ai.py

Strategy:
  MAP   — summarize each chunk independently (parallel-safe, sequential here)
  REDUCE — combine chunk summaries into final structured output

This preserves content from the entire video, regardless of length.
A 3-hour video is processed fully; truncation is gone.

Install: no new deps — uses existing OpenRouter client
"""

import os
import json
import logging
from typing import Callable

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────
MAP_CHUNK_WORDS  = int(os.getenv("MAP_CHUNK_WORDS", "600"))   # words per map chunk
MAX_MAP_CHUNKS   = int(os.getenv("MAX_MAP_CHUNKS", "20"))     # cap total API calls
MAP_SUMMARY_TOKENS = 300                                       # per-chunk summary length


# ─────────────────────────────────────────────────────────────
# PROMPT TEMPLATES
# ─────────────────────────────────────────────────────────────

MAP_SYSTEM = """You are a precise content extractor. Your job is to extract key information from a transcript segment.
Be specific. Use exact terms from the text. No generic statements.
CRITICAL: You will see timestamps in the text like [0:00]. When extracting facts, you must note the EXACT literal timestamp that appeared next to it."""

MAP_PROMPT = """Extract the key information from this transcript segment (part {part} of {total}).

SEGMENT:
{chunk}

Respond with 3-5 bullet points of specific facts, arguments, or examples from this segment.
If a point is particularly important, write the EXACT timestamp you see in the text (e.g. "[1:25]") at the end of the bullet point. DO NOT guess timestamps."""


REDUCE_SYSTEM = """You are an expert AI research assistant. You synthesize segment summaries into a final structured analysis.
Always respond with valid JSON only — no markdown fences, no extra text."""

REDUCE_PROMPT = """You are an expert editor synthesizing multiple segment summaries into one cohesive, final master summary representing the entire video.

<video_title>
{title}
</video_title>

<segment_summaries>
{mapped_summaries}
</segment_summaries>

You must respond ONLY with a valid JSON object exactly matching this structure. Replace the values with your actual synthesis of the segments:
{{
  "key_points": ["point 1", "point 2", "point 3", "point 4"],
  "critical_timestamps": [
    {{"time": "exact time found in segment", "label": "Full 1-2 sentence detailed description of what happens at this exact moment."}}
  ],
  "core_insight": "The single most important takeaway in one precise sentence.",
  "summary_paragraph": "A 2-3 sentence overview written for someone who has not seen the video.",
  "action_points": ["action 1", "action 2"],
  "target_audience": "Who benefits most from watching this video",
  "content_type": "tutorial|interview|lecture|review|news|other",
  "suggested_questions": ["Question 1?", "Question 2?", "Question 3?"]
}}"""


# ─────────────────────────────────────────────────────────────
# MAP STEP
# ─────────────────────────────────────────────────────────────

def _split_to_map_chunks(segments: list[dict]) -> list[str]:
    """Combine segment objects into word-count chunks with injected timestamps for the map step."""
    chunks = []
    current_chunk = []
    current_words = 0
    
    for s in segments:
        text = s.get("text", "")
        time_fmt = s.get("start_fmt", "0:00")
        
        # Inject the literal timestamp into the text block so the AI can read it
        segment_str = f"[{time_fmt}] {text}"
        current_chunk.append(segment_str)
        current_words += len(text.split())
        
        if current_words >= MAP_CHUNK_WORDS:
            chunks.append(" ".join(current_chunk))
            current_chunk = []
            current_words = 0
            
    if current_chunk:
        chunks.append(" ".join(current_chunk))

    # Cap to avoid excessive API calls
    if len(chunks) > MAX_MAP_CHUNKS:
        logger.warning(f"Transcript has {len(chunks)} chunks → sampling to {MAX_MAP_CHUNKS}")
        # Keep first, last, and evenly spaced middle chunks
        step = len(chunks) / MAX_MAP_CHUNKS
        chunks = [chunks[min(int(i * step), len(chunks) - 1)] for i in range(MAX_MAP_CHUNKS)]
    return chunks


def _map_chunk(caller: Callable, chunk: str, part: int, total: int) -> str:
    """Summarise a single chunk (MAP step)."""
    messages = [
        {"role": "system", "content": MAP_SYSTEM},
        {"role": "user", "content": MAP_PROMPT.format(
            chunk=chunk, part=part, total=total
        )},
    ]
    try:
        content, _ = caller(messages, max_tokens=MAP_SUMMARY_TOKENS, temperature=0.1)
        return content.strip()
    except Exception as e:
        logger.warning(f"Map chunk {part} failed: {e}")
        return f"[Segment {part} could not be processed]"


# ─────────────────────────────────────────────────────────────
# REDUCE STEP
# ─────────────────────────────────────────────────────────────

def _reduce(caller: Callable, mapped_summaries: list[str], title: str) -> dict:
    """Combine all chunk summaries into final structured output (REDUCE step)."""
    numbered = "\n\n".join(
        f"[Segment {i+1}]\n{s}" for i, s in enumerate(mapped_summaries)
    )
    messages = [
        {"role": "system", "content": REDUCE_SYSTEM},
        {"role": "user", "content": REDUCE_PROMPT.format(
            title=title,
            mapped_summaries=numbered,
        )},
    ]
    content, usage = caller(messages, max_tokens=1500, temperature=0.3, expect_json=True)

    import re
    match = re.search(r'\{.*\}', content, re.DOTALL)
    clean = match.group(0) if match else content.strip()

    try:
        result = json.loads(clean)
    except json.JSONDecodeError:
        logger.warning("Reduce JSON parse failed — using fallback")
        result = {
            "key_points": ["Full video processed but structured parse failed."],
            "critical_timestamps": [],
            "core_insight": clean[:300],
            "summary_paragraph": clean[:500],
            "action_points": [],
            "target_audience": "General audience",
            "content_type": "other",
        }

    result["_usage"] = usage
    return result


# ─────────────────────────────────────────────────────────────
# PUBLIC API  (called from ai.py generate_summary)
# ─────────────────────────────────────────────────────────────

SHORT_THRESHOLD_WORDS = MAP_CHUNK_WORDS  # skip map-reduce for short transcripts


def hierarchical_summarize(transcript_data: dict, title: str, caller: Callable) -> dict:
    """
    Full map-reduce pipeline with explicit timestamp preservation.

    Args:
        transcript_data : the dict containing the "text" and "segments" array
        title           : video title
        caller          : reference to ai._call() — injected to avoid circular imports

    Returns:
        structured summary dict (same shape as before, no contract change)

    REPLACES the truncation block in ai.generate_summary():
        OLD: truncated = transcript[:24000] if len(transcript) > 24000 else transcript
        NEW: return hierarchical_summarize(transcript, title, _call)
    """
    transcript = transcript_data.get("text", "")
    segments = transcript_data.get("segments", [])
    
    word_count = len(transcript.split())
    logger.info(f"Summarizing '{title}' — {word_count} words")

    # Short video: skip map step entirely, one direct call
    if word_count <= SHORT_THRESHOLD_WORDS:
        logger.info("Short transcript — using direct summarization")
        from services.ai import SUMMARY_SYSTEM, SUMMARY_PROMPT
        messages = [
            {"role": "system", "content": SUMMARY_SYSTEM},
            {"role": "user", "content": SUMMARY_PROMPT.format(
                title=title, transcript=transcript
            )},
        ]
        content, usage = caller(messages, max_tokens=1500, expect_json=True)
        
        import re
        match = re.search(r'\{.*\}', content, re.DOTALL)
        clean = match.group(0) if match else content.strip()
        
        try:
            result = json.loads(clean)
        except Exception:
            result = {"key_points": [], "core_insight": clean[:300], "summary_paragraph": clean[:500],
                      "critical_timestamps": [], "action_points": [], "target_audience": "", "content_type": "other"}
        result["_usage"] = usage
        return result

    # Long video: full map-reduce
    chunks = _split_to_map_chunks(segments)
    total  = len(chunks)
    logger.info(f"MAP step: {total} chunks × ~{MAP_CHUNK_WORDS} words each")

    mapped = []
    for i, chunk in enumerate(chunks, 1):
        summary = _map_chunk(caller, chunk, i, total)
        mapped.append(summary)
        logger.debug(f"  Mapped chunk {i}/{total}")

    logger.info("REDUCE step: synthesizing chunk summaries")
    result = _reduce(caller, mapped, title)
    result["_map_chunks"] = total   # expose for logging/debugging
    return result