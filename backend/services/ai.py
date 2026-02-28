"""
ai.py – OpenRouter integration for summarization, Q&A, and multilingual responses
"""
import os
import json
import time
import logging
from typing import Optional
from openai import OpenAI

logger = logging.getLogger(__name__)

# ── Language display names ────────────────────────────────────
LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi (हिन्दी)",
    "ta": "Tamil (தமிழ்)",
    "te": "Telugu (తెలుగు)",
    "kn": "Kannada (ಕನ್ನಡ)",
    "mr": "Marathi (मराठी)",
    "bn": "Bengali (বাংলা)",
    "gu": "Gujarati (ગુજરાતી)",
}

client = OpenAI(
    api_key=os.getenv("OLLAMA_API_KEY", "ollama"),  # API key is required by the SDK but ignored by local Ollama
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
)

# Default to llama3.1 (You must pull this model via `ollama run llama3.1` in your terminal)
# Override with OLLAMA_MODEL env var for other models like `mistral`, `phi3`, etc.
MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")


def _call(messages: list, max_tokens: int = 300, temperature: float = 0.2, expect_json: bool = False) -> tuple[str, dict]:
    """Raw OpenRouter/Ollama call. Returns (content, usage)."""
    t0 = time.time()
    try:
        kwargs = {
            "model": MODEL,
            "messages": messages,
            "max_tokens": max_tokens,  # Limits Ollama generation size for speed
            "temperature": temperature,
        }
        if expect_json:
            kwargs["response_format"] = {"type": "json_object"}
            
        resp = client.chat.completions.create(**kwargs)
        if not resp.choices:
             raise ValueError("Ollama returned empty choices, model is likely failing on response_format.")
        content = resp.choices[0].message.content or ""
        usage = {
            "prompt_tokens": resp.usage.prompt_tokens if resp.usage else 0,
            "completion_tokens": resp.usage.completion_tokens if resp.usage else 0,
            "latency_ms": round((time.time() - t0) * 1000),
        }
        return content, usage
    except Exception as e:
        # Fallback if model doesn't support JSON response format
        if expect_json and "response_format" in kwargs:
            logger.warning(f"Retrying without JSON response_format due to error: {e}")
            kwargs.pop("response_format")
            try:
                resp = client.chat.completions.create(**kwargs)
                content = resp.choices[0].message.content or ""
                usage = {
                    "prompt_tokens": resp.usage.prompt_tokens if resp.usage else 0,
                    "completion_tokens": resp.usage.completion_tokens if resp.usage else 0,
                    "latency_ms": round((time.time() - t0) * 1000),
                }
                return content, usage
            except Exception as e2:
                logger.error(f"Ollama fallback call failed: {e2}")
                raise e2
                
        error_str = str(e)
        logger.error(f"Ollama call failed: {e}. Ensure Ollama is running and model '{MODEL}' is pulled.")
        raise


# ─────────────────────────────────────────────────────────────
# SUMMARIZATION
# ─────────────────────────────────────────────────────────────

SUMMARY_SYSTEM = """You are an expert AI research assistant specializing in YouTube video analysis.
Your task is to create structured, insightful summaries that save people time and extract real value.
Always respond with valid JSON only – no markdown fences, no extra text."""

SUMMARY_PROMPT = """Analyze this YouTube video transcript and produce a structured summary.

<video_title>
{title}
</video_title>

<transcript>
{transcript}
</transcript>

You must respond ONLY with a valid JSON object exactly matching this structure. Replace the values with your actual analysis:
{{
  "key_points": ["point 1", "point 2", "point 3"],
  "critical_timestamps": [
    {{"time": "exact time found in text", "label": "Full 1-2 sentence detailed description of what happens at this exact moment."}}
  ],
  "core_insight": "The single most important takeaway in one sentence.",
  "summary_paragraph": "A 2-3 sentence overview of the entire video.",
  "action_points": ["action 1", "action 2"],
  "target_audience": "Who benefits most from this video",
  "content_type": "tutorial|interview|lecture|review|news|other",
  "suggested_questions": ["Question 1 about the video?", "Question 2?", "Question 3?"]
}}"""


def generate_summary(transcript_data: dict, title: str, language: str = "en") -> dict:
    """
    Generate a structured summary using hierarchical map-reduce.
    Full transcript is preserved — no truncation.
    """
    # ── UPGRADE: map-reduce replaces transcript[:24000] truncation ──
    from services.summarizer import hierarchical_summarize
    result = hierarchical_summarize(transcript_data, title, _call)
    # ────────────────────────────────────────────────────────────────

    # Translate if needed
    if language != "en":
        result = translate_summary(result, language)

    return result


# ─────────────────────────────────────────────────────────────
# Q&A
# ─────────────────────────────────────────────────────────────

QA_SYSTEM = """You are a helpful AI assistant answering questions about a YouTube video based on its transcript.
Use the provided transcript context to answer the user's question.
If the context doesn't contain the exact answer, give the best related summary you can based on the text.
Keep answers concise but complete (2-4 sentences unless more detail is needed).
If the user asks a question using English letters but in a different language (e.g. "Hinglish"), you must STILL answer back using the NATIVE script of that target language (e.g. Devanagari for Hindi). ALWAYS use native scripts, NEVER Romanized/Hinglish characters for your output."""

QA_PROMPT = """<video_title>
{title}
</video_title>

<transcript_context>
{context}
</transcript_context>

<conversation_history>
{history}
</conversation_history>

<question>
{question}
</question>

Based ONLY on the <transcript_context> above, answer the <question>. If the question is a general request like "brief it" or "example", simply summarize the core themes of the context."""


def answer_question(
    question: str,
    transcript: str,
    title: str,
    history: list[dict],
    language: str = "en",
    video_id: str = "",          # ← NEW: pass video_id for FAISS index lookup
) -> tuple[str, dict]:
    """
    Answer a user question grounded in the transcript.
    Uses semantic FAISS retrieval + hallucination score guard.
    Returns (answer_text, usage).
    """
    # ── UPGRADE: semantic retrieval replaces keyword search ───────
    from services.retriever import retrieve_context, check_relevance, NOT_IN_VIDEO_MSG

    if video_id:
        context, best_score = retrieve_context(question, video_id, transcript)
        if not check_relevance(best_score):
            logger.info(f"Q&A rejected (score={best_score:.3f} < threshold): '{question[:60]}'")
            return NOT_IN_VIDEO_MSG, {"prompt_tokens": 0, "completion_tokens": 0, "latency_ms": 0}
    else:
        # Fallback to full transcript if no video_id supplied
        context = transcript[:12000]
    # ──────────────────────────────────────────────────────────────

    # Build history string (last 6 exchanges)
    recent = history[-12:] if len(history) > 12 else history
    history_str = "\n".join(
        f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
        for m in recent
    )

    lang_instruction = ""
    if language != "en":
        lang_name = LANGUAGE_NAMES.get(language, language)
        lang_instruction = f"\n\nCRITICAL INSTRUCTION: You MUST write your ENTIRE final answer in {lang_name} USING ITS NATIVE SCRIPT (e.g. Devanagari). DO NOT respond in English. IMPORTANT: Even if the user asks their question in Romanized English letters ('aaise likha'), you MUST ignore the Romanization and reply strictly in the NATIVE SCRIPT of {lang_name}."

    messages = [
        {"role": "system", "content": QA_SYSTEM + lang_instruction},
        {"role": "user", "content": QA_PROMPT.format(
            title=title,
            context=context,
            history=history_str or "No previous conversation.",
            question=question,
        )},
    ]

    answer, usage = _call(messages, max_tokens=800, temperature=0.2)
    return answer.strip(), usage


# _find_relevant_context() removed — replaced by services/retriever.py:retrieve_context()


# ─────────────────────────────────────────────────────────────
# TRANSLATION / MULTILINGUAL
# ─────────────────────────────────────────────────────────────

def translate_summary(summary: dict, target_language: str) -> dict:
    """Translate summary fields to target language individually to prevent 1B model degradation."""
    lang_name = LANGUAGE_NAMES.get(target_language, target_language)

    def _translate_string(text: str) -> str:
        if not text.strip():
            return text
        messages = [
            {"role": "system", "content": f"You are a strict, professional {lang_name} translator. Your ONLY job is to translate the user's text into {lang_name}. DO NOT add any extra commentary, notes, or English text. Output ONLY the strict {lang_name} translation."},
            {"role": "user", "content": text},
        ]
        try:
            content, _ = _call(messages, max_tokens=1000, temperature=0.1)
            return content.strip()
        except Exception as e:
            logger.error(f"Text translation failed: {e}")
            return text

    logger.info(f"Translating summary to {lang_name} field-by-field...")
    
    # Translate scalar strings
    if "core_insight" in summary:
        summary["core_insight"] = _translate_string(summary["core_insight"])
    if "summary_paragraph" in summary:
        summary["summary_paragraph"] = _translate_string(summary["summary_paragraph"])

    # Translate lists of strings
    for list_key in ["key_points", "action_points", "suggested_questions"]:
        if list_key in summary and isinstance(summary[list_key], list):
            translated_list = []
            for item in summary[list_key]:
                translated_list.append(_translate_string(str(item)))
            summary[list_key] = translated_list

    # Translate the complex timestamp dictionary array
    if "critical_timestamps" in summary and isinstance(summary["critical_timestamps"], list):
        for ts in summary["critical_timestamps"]:
            if isinstance(ts, dict) and "label" in ts:
                ts["label"] = _translate_string(str(ts["label"]))

    return summary


def detect_language_request(text: str) -> Optional[str]:
    """
    Detect if user is requesting a specific language.
    Returns language code or None.
    """
    text_lower = text.lower()
    triggers = {
        "hindi": "hi", "हिंदी": "hi", "हिन्दी": "hi",
        "tamil": "ta", "தமிழ்": "ta",
        "telugu": "te", "తెలుగు": "te",
        "kannada": "kn", "ಕನ್ನಡ": "kn",
        "marathi": "mr", "मराठी": "mr",
        "bengali": "bn", "বাংলা": "bn",
        "gujarati": "gu", "ગુજરાતી": "gu",
        "english": "en",
    }
    for trigger, code in triggers.items():
        if trigger in text_lower:
            return code
    return None


def generate_deep_dive(transcript: str, title: str, language: str = "en") -> str:
    """Generate an extended deep-dive analysis."""
    truncated = transcript[:20000]
    messages = [
        {"role": "system", "content": "You are an expert content analyst. Provide deep, thoughtful analysis."},
        {"role": "user", "content": f"""Perform a deep-dive analysis of this video: {title}

TRANSCRIPT: {truncated}

Provide:
1. **Main Arguments** - Core thesis and supporting arguments
2. **Evidence & Examples** - Key examples or data mentioned  
3. **Implications** - What this means for the viewer
4. **Critical Perspective** - Any limitations or counterpoints
5. **Expert Verdict** - Your assessment of the content quality

{'Respond in ' + LANGUAGE_NAMES.get(language, language) + '.' if language != 'en' else ''}"""},
    ]
    content, _ = _call(messages, max_tokens=1200)
    return content


def generate_action_points(transcript: str, title: str, language: str = "en") -> str:
    """Extract concrete action points from the video."""
    truncated = transcript[:16000]
    messages = [
        {"role": "system", "content": "Extract concrete, actionable steps from video content."},
        {"role": "user", "content": f"""From this video "{title}", extract all actionable advice, steps, or recommendations.

TRANSCRIPT: {truncated}

Format as a numbered action plan with:
- Clear action items
- Why each matters
- How to implement

{'Respond in ' + LANGUAGE_NAMES.get(language, language) + '.' if language != 'en' else ''}"""},
    ]
    content, _ = _call(messages, max_tokens=1000)
    return content