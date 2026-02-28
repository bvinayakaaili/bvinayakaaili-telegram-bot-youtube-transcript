# YouTube AI Summarizer & Semantic Q&A Bot

A highly optimized Telegram bot acting as a personal research assistant for YouTube videos. It fully processes transcripts, generates structured insights using an intelligent Map-Reduce pipeline, answers contextual follow-up questions mathematically via a local FAISS semantic retrieval engine, and provides instant UI translation pivot keyboards natively supporting English, Hindi, Tamil, Telugu, Kannada, and Marathi.

**Powered entirely locally by OpenClaw / Ollama.**

---

## 📸 Project Demonstration

### 1. Robust Video Parsing & Core Insights
The bot extracts the YouTube ID, pulls the transcript, and generates a structured JSON payload detailing Key Points, contextual timestamps, and the Core Takeaway.
![Bot Parsing Example](./photos/Screenshot%202026-02-28%20141007.png)

### 2. Semantic Contextual Q&A
Users can ask conversational follow-up questions. The bot parses mathematical intent against a Vector Database, locating exact paragraphs to answer grounded questions while structurally refusing to hallucinate answers on missing context.
![Q&A Example](./photos/Screenshot%202026-02-28%20141037.png)

### 3. Deep Dives & Action Points
Users can drill down into the video via single-tap inline keyboard commands that instantly generate actionable takeaways.
![Action Points Example](./photos/Screenshot%202026-02-28%20141218.png)

### 4. Natively Cross-Lingual
Switch languages effortlessly with dynamic translation buttons. The system detects "Hinglish/Tanglish" Romanized dialect requests but strictly answers back in the native Unicode scripts.
![Multi-language Translation Example](./photos/Screenshot%202026-02-28%20141347.png)

---

## 🚀 Setup Instructions

### Prerequisites
1. **Python 3.10+**
2. **Ollama** installed locally (`ollama run llama3.2:1b`)
3. **Telegram Bot Token** (From [@BotFather](https://t.me/botfather))

### Installation
1. **Clone the repo**
```bash
git clone <repository_url>
cd backend
```
2. **Install local environment & dependencies**
```bash
python -m venv venv
venv\Scripts\Activate.ps1   # On Windows
pip install -r requirements.txt
```
3. **Configure Environment**
Create a `.env` file in the root directory:
```env
TELEGRAM_BOT_TOKEN="your_token_here"
OLLAMA_BASE_URL="http://localhost:11434/v1"
OLLAMA_MODEL="llama3.2:1b"
```
4. **Boot the Backend Framework**
```bash
python app.py
```

---

## 🏛️ System Architecture

### 1. Data Ingestion layer (`youtube.py`)
Relies on `youtube-transcript-api` to pull WebVTT files cleanly. Features a built-in fallback to headless `yt-dlp` to force-scrape closed captions if the primary API is rate-limited by Google.

### 2. Hierarchical Summarization (`summarizer.py`)
To solve the narrow "Context Window" limitation of small 1B parameter AI models, long transcripts are processed through a **Map-Reduce Pipeline**:
- **Map:** Text is split into 1500-word chunks (with literal `[MM:SS]` timestamp injections). The AI writes a mini-summary for each chunk.
- **Reduce:** The AI reads all mini-summaries simultaneously and synthesizes a final, highly structured JSON output.

### 3. Semantic Retrieval Pipeline (`retriever.py`)
Using `sentence-transformers/all-MiniLM-L6-v2`, user questions are mathematically mapped into an N-dimensional space against the chunks of the video transcript using a **FAISS Vector Database**. This ensures:
1. **Speed:** The Q&A search is nearly instant.
2. **Hallucination Guarding:** By applying a `SIM_THRESHOLD` of `0.40`, the bot mathematically verifies if text context relates to the question. If the user asks about "maths" on a "Redis" video, the semantic overlap naturally scores `< 0.40`, triggering an automated rejection to protect database integrity without even pinging the LLM.

---

## ⚖️ Design Trade-Offs & Optimizations

### 1. Database State over RAM Context
Instead of keeping a massive conversation string in RAM or within the LLM's context window, we persist all video data, transcript dictionaries, and conversation history via SQLite (`youtube_bot.db`). We selectively inject only the last 10 messages of history array tuples per-call. This eliminates Context Degradation completely.

### 2. Background Threading vs. Blocking Coroutines
To prevent the user from waiting ~40s while the local CPU compiled the FAISS Vector Database, FAISS `build_index()` was decoupled and cast to a background daemon `threading.Thread()`. Telegram replies with the initial video summary *instantly* while the system mathematically indexes the transcript data in the background, making Time-To-First-Message latency near zero.

### 3. Field-by-Field Translation Mapping
When pivoting an english JSON dictionary into Hindi or Tamil out of a 1-Billion parameter LLM, it frequently "giving up" halfway through the translation to preserve output tokens. 
**Trade-off:** We increased internal generation time by translating every single JSON key independently via sequential localized requests inside a `<json_to_translate>` XML tag structure, completely eliminating translation failure at the cost of slight UI delay.

### 4. Global Model Instantiation
The 80MB local embedding model was extracted from the Q&A generation lifecycle and pinned to the global python execution scope in `retriever.py`. 
**Trade-off:** The Python server inherently utilizes ~1.5GB of GPU/System memory at idle, but entirely bypasses the 5-7 second I/O cold-start delay for every user question.

---

## 🛡️ Edge Cases Handled Successfully
*   **Invalid Youtube Link** → Caught by pre-fetch Regex validation. Returns generic error.
*   **Disabled Transcripts** → Catches metadata unavailability and instructs user to select videos with CC enabled.
*   **Very Long Videos (3+ hrs)** → Automatically throttled by the Map-Reduce recursive sampling chunker. Preserves beginning and end, samples the middle evenly to prevent extreme API token waste.
*   **Casual Conversation Injection** → A custom `HANDLE_MESSAGE` listener traps naive greeting commands (e.g. "hi", "help") to prevent the FAISS Retrieval engine from wasting GPU cycles building semantic maps against small talk.
*   **Infinite Question Loops** → Added an explicit `[🔄 Start New Session]` graphical database UI button mapped to a `cmd_clear` cache-wipe, empowering users to manually decouple the session tree without sending text.
