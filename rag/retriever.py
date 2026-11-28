"""RAG retrieval: similarity search over the ChromaDB documentation index.

Usage:  python -m rag.retriever "CFSR INVSTATE bit meaning"
"""
import re
import sys

from rag.ingestion import EMBED_MODEL, get_collection

CANDIDATES = 20        # vector-search candidates that are re-ranked
TERM_WEIGHT = 0.4      # weight of exact query-term overlap in the final score


class Retriever:
    """Callable: retriever(query) -> [{text, source, page, section, score}] (best first)."""

    def __init__(self, k=4, min_score=0.2):
        from sentence_transformers import SentenceTransformer

        self.k, self.min_score = k, min_score
        self.col = get_collection()                      # raises if not ingested yet
        self.model = SentenceTransformer(EMBED_MODEL)

    def __call__(self, query, k=None):
        """Vector search for CANDIDATES chunks, then re-rank with an exact-term bonus.

        Embeddings capture the topic ('timer control register') but not exact register or
        bit names ('UDIS', 'DIVBYZERO'), which are what firmware debugging queries contain.
        """
        emb = self.model.encode([query], normalize_embeddings=True).tolist()
        r = self.col.query(query_embeddings=emb, n_results=CANDIDATES,
                           include=["documents", "metadatas", "distances"])
        terms = {w.lower() for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", query)}
        hits = []
        for doc, meta, dist in zip(r["documents"][0], r["metadatas"][0], r["distances"][0]):
            words = set(re.findall(r"[a-z0-9_]+", doc.lower()))
            overlap = len(terms & words) / len(terms) if terms else 0.0
            hits.append({"text": doc, "source": meta["source"], "file": meta["file"],
                         "page": meta["page"], "section": meta.get("section", ""),
                         "similarity": round(1 - dist, 3),
                         "score": round((1 - TERM_WEIGHT) * (1 - dist) + TERM_WEIGHT * overlap, 3)})
        hits.sort(key=lambda h: h["score"], reverse=True)
        return [h for h in hits if h["similarity"] >= self.min_score][:k or self.k]


def load_retriever(**kw):
    """Retriever, or None (with a message) if the index has not been built."""
    try:
        return Retriever(**kw)
    except Exception as e:
        print(f"[rag] retrieval disabled: {e}. Run: python -m rag.ingestion")
        return None


if __name__ == "__main__":
    r = Retriever()
    for h in r(" ".join(sys.argv[1:]) or "HardFault INVSTATE"):
        print(f"--- {h['source']} p.{h['page']} ({h['section']}) score={h['score']}")
        print(h["text"][:500])
