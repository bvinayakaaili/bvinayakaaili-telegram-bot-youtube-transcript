"""
retriever.py — Semantic retrieval upgrade for Q&A
Replaces: _find_relevant_context() in ai.py

Provides:
  - Transcript chunking with overlap
  - Local sentence-transformers embeddings (no API cost)
  - FAISS vector search
  - Similarity-score hallucination threshold guard

Install once:
    pip install faiss-cpu sentence-transformers numpy
"""

import os
import json
import logging
import hashlib
import numpy as np
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────
EMBED_MODEL    = os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")   # 80 MB, fast, free
CHUNK_SIZE     = int(os.getenv("CHUNK_SIZE", "400"))             # words per chunk
CHUNK_OVERLAP  = int(os.getenv("CHUNK_OVERLAP", "60"))           # word overlap
TOP_K          = int(os.getenv("RETRIEVAL_TOP_K", "4"))          # chunks to retrieve
SIM_THRESHOLD  = float(os.getenv("SIM_THRESHOLD", "0.40"))       # cosine sim floor
INDEX_DIR      = Path(os.getenv("INDEX_DIR", "./faiss_indexes")) # persist indexes

INDEX_DIR.mkdir(exist_ok=True)

# Lazy-loaded globals (loaded once per process)
_index_cache: dict[str, dict] = {}   # video_id → {index, chunks}


# ─────────────────────────────────────────────────────────────
# EMBEDDER
# ─────────────────────────────────────────────────────────────

from sentence_transformers import SentenceTransformer
logger.info(f"Loading global embedding model: {EMBED_MODEL}")
embedding_model = SentenceTransformer(EMBED_MODEL)

def _embed(texts: list[str]) -> np.ndarray:
    """Embed a list of texts → float32 numpy array, L2-normalised."""
    vecs = embedding_model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
    # Normalise for cosine similarity via inner product
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    return (vecs / norms).astype("float32")


# ─────────────────────────────────────────────────────────────
# CHUNKING
# ─────────────────────────────────────────────────────────────

def chunk_by_words(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    Split transcript into overlapping word-count chunks.
    Word-based (not char-based) → consistent semantic density.
    """
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + size, len(words))
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        if end == len(words):
            break
        start += size - overlap
    return chunks


# ─────────────────────────────────────────────────────────────
# INDEX BUILD + PERSIST
# ─────────────────────────────────────────────────────────────

def _index_path(video_id: str) -> tuple[Path, Path]:
    return INDEX_DIR / f"{video_id}.index", INDEX_DIR / f"{video_id}.chunks.json"


def build_index(video_id: str, transcript: str) -> dict:
    import faiss

    idx_path, chunks_path = _index_path(video_id)

    # ── Load from disk if exists AND valid ───────────────────
    if idx_path.exists() and chunks_path.exists():
        try:
            content = chunks_path.read_text().strip()
            if content:  # only load if file is not empty
                index  = faiss.read_index(str(idx_path))
                chunks = json.loads(content)
                if chunks:  # only use if chunks list is not empty
                    logger.info(f"Loading existing FAISS index for {video_id}")
                    result = {"index": index, "chunks": chunks}
                    _index_cache[video_id] = result
                    return result
        except Exception as e:
            logger.warning(f"Corrupt index for {video_id}, rebuilding: {e}")
            # Delete corrupt files and rebuild
            try:
                idx_path.unlink(missing_ok=True)
                chunks_path.unlink(missing_ok=True)
            except Exception:
                pass

    # ── Build fresh ───────────────────────────────────────────
    logger.info(f"Building FAISS index for {video_id} …")
    chunks = chunk_by_words(transcript)

    if not chunks:
        raise ValueError("Empty transcript — cannot build index")

    vecs  = _embed(chunks)
    dim   = vecs.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(vecs)

    # Persist atomically (write to temp first, then rename)
    tmp_chunks = chunks_path.with_suffix(".tmp")
    tmp_chunks.write_text(json.dumps(chunks, ensure_ascii=False), encoding='utf-8')
    tmp_chunks.replace(chunks_path)  # atomic rename
    faiss.write_index(index, str(idx_path))

    logger.info(f"FAISS index built: {len(chunks)} chunks, dim={dim}")

    result = {"index": index, "chunks": chunks}
    _index_cache[video_id] = result
    return result


def get_or_build_index(video_id: str, transcript: str) -> dict:
    """Return cached index or build it."""
    if video_id in _index_cache:
        return _index_cache[video_id]
    return build_index(video_id, transcript)


# ─────────────────────────────────────────────────────────────
# SEMANTIC RETRIEVAL  (replaces _find_relevant_context)
# ─────────────────────────────────────────────────────────────

def retrieve_context(
    question: str,
    video_id: str,
    transcript: str,
    top_k: int = TOP_K,
) -> tuple[str, float]:
    """
    Semantic retrieval: embed question → FAISS search → return context.

    Returns:
        context_text  : concatenated top-k chunks
        best_score    : highest cosine similarity (float 0–1)

    REPLACES: _find_relevant_context(question, transcript) in ai.py
    """
    store  = get_or_build_index(video_id, transcript)
    index  = store["index"]
    chunks = store["chunks"]

    q_vec = _embed([question])                        # shape (1, dim)
    k     = min(top_k, len(chunks))
    scores, indices = index.search(q_vec, k)          # scores: cosine similarities

    best_score = float(scores[0][0]) if len(scores[0]) > 0 else 0.0

    # Maintain reading order for coherence
    ordered = sorted(zip(indices[0], scores[0]), key=lambda x: x[0])
    selected_chunks = [chunks[i] for i, _ in ordered if i < len(chunks)]

    context = "\n\n---\n\n".join(selected_chunks)
    logger.debug(f"Retrieval: best_score={best_score:.3f}, chunks={len(selected_chunks)}")
    return context, best_score


# ─────────────────────────────────────────────────────────────
# HALLUCINATION GUARD
# ─────────────────────────────────────────────────────────────

NOT_IN_VIDEO_MSG = "This topic is not covered in the video."

def check_relevance(best_score: float, threshold: float = SIM_THRESHOLD) -> bool:
    """
    Returns True if the retrieved context is relevant enough to answer.
    If False, the caller should return NOT_IN_VIDEO_MSG directly
    without even calling the LLM — saves tokens and prevents hallucination.

    Threshold tuning guide:
      0.30 → very permissive (rarely rejects)
      0.40 → strict default ← recommended for 1B models
      0.50 → very strict (rejects tangential questions)
    """
    return best_score >= threshold


def delete_index(video_id: str):
    """Remove index files for a video (e.g. when clearing cache)."""
    idx_path, chunks_path = _index_path(video_id)
    if idx_path.exists():
        idx_path.unlink()
    if chunks_path.exists():
        chunks_path.unlink()
    _index_cache.pop(video_id, None)
    logger.info(f"Deleted FAISS index for {video_id}")