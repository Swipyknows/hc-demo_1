"""RAG retrieval: similarity search over the ChromaDB documentation index.

Usage:  python -m rag.retriever "CFSR INVSTATE bit meaning"
"""
import sys

from rag.ingestion import EMBED_MODEL, get_collection


class Retriever:
    """Callable: retriever(query) -> [{text, source, page, section, score}] (best first)."""

    def __init__(self, k=4, min_score=0.2):
        from sentence_transformers import SentenceTransformer

        self.k, self.min_score = k, min_score
        self.col = get_collection()                      # raises if not ingested yet
        self.model = SentenceTransformer(EMBED_MODEL)

    def __call__(self, query, k=None):
        emb = self.model.encode([query], normalize_embeddings=True).tolist()
        r = self.col.query(query_embeddings=emb, n_results=k or self.k,
                           include=["documents", "metadatas", "distances"])
        hits = [{"text": doc, "source": meta["source"], "file": meta["file"],
                 "page": meta["page"], "section": meta.get("section", ""),
                 "score": round(1 - dist, 3)}
                for doc, meta, dist in zip(r["documents"][0], r["metadatas"][0], r["distances"][0])]
        return [h for h in hits if h["score"] >= self.min_score]


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
