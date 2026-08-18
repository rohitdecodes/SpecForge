"""FAISS vector index for retrieval — Phase 2.

Embeds text chunks with sentence-transformers and builds a per-product
FAISS index for similarity search.
"""
from __future__ import annotations

import numpy as np

try:
    import faiss
    HAS_FAISS = True
except ImportError:
    HAS_FAISS = False

try:
    from sentence_transformers import SentenceTransformer
    _MODEL = SentenceTransformer("all-MiniLM-L6-v2")
except ImportError:
    _MODEL = None


def is_available() -> bool:
    return HAS_FAISS and _MODEL is not None


def build_index(chunks: list[str]):
    """Embed chunks and build a FAISS L2 index.

    Args:
        chunks: List of text chunks to embed and index.

    Returns:
        Tuple of (faiss_index, chunks_list).  Returns (None, chunks) if
        either dependency is missing.
    """
    if not is_available():
        return None, chunks
    if not chunks:
        return None, chunks
    embeddings = _MODEL.encode(chunks, show_progress_bar=False)
    dim = embeddings.shape[1]
    index = faiss.IndexFlatL2(dim)
    index.add(np.array(embeddings, dtype=np.float32))
    return index, chunks


def retrieve(
    query: str, index, chunks: list[str], k: int = 3
) -> list[tuple[str, float]]:
    """Search the FAISS index and return top-k (chunk, distance) pairs.

    Args:
        query: The search query (e.g. "voltage rating").
        index: FAISS index from build_index().
        chunks: Original chunk list.
        k: Number of results to return.

    Returns:
        List of (chunk_text, distance) pairs, sorted by distance ascending.
    """
    if index is None or not chunks:
        return []
    if not is_available():
        return []

    q_emb = _MODEL.encode([query], show_progress_bar=False)
    distances, ids = index.search(np.array(q_emb, dtype=np.float32), k)
    results: list[tuple[str, float]] = []
    for i, d in zip(ids[0], distances[0]):
        if i >= 0 and i < len(chunks):
            results.append((chunks[i], float(d)))
    return results
