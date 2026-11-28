"""RAG ingestion: PDF documentation -> text -> chunks -> embeddings -> ChromaDB.

Usage:  python -m rag.ingestion [--rebuild]

Large manuals are indexed only on chapters relevant to the debugging target: a chapter is
kept when its top-level table-of-contents title matches one of the configured keywords.
"""
import glob
import os
import re
import sys

DOC_DIR = "knowledge_base/documentation"
DB_DIR = "knowledge_base/chroma"
COLLECTION = "embedded_docs"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
CHUNK_CHARS, OVERLAP_CHARS = 1000, 200

# file-name prefix -> (short source name, chapter keywords or None for the whole document)
DOCS = {
    "DUI0552A": ("Cortex-M3 Generic User Guide", None),
    "pm0056": ("PM0056 Cortex-M3 Programming Manual", None),
    "apnt209": ("Keil AN209 Fault Exceptions", None),
    # 858 pages: keep programmers' models (registers, exception model, faults), memory model,
    # system address map (SCS, SysTick, NVIC) and register index; skip instruction encodings,
    # trace/debug units and pseudocode.
    "DDI0403E": ("ARMv7-M Architecture Reference Manual",
                 ["programmers", "architecture memory model", "system address map",
                  "register index"]),
    # 1,363 pages: keep only the peripherals and system blocks the benchmark firmware uses.
    "rm0033": ("RM0033 STM32F205 Reference Manual",
               ["memory and bus", "reset and clock", "system configuration",
                "interrupts and events", "general-purpose timers (tim2", "universal synchronous",
                "debug support"]),
}


def doc_info(path):
    base = os.path.basename(path)
    for prefix, info in DOCS.items():
        if base.lower().startswith(prefix.lower()):
            return info
    return os.path.splitext(base)[0], None


def page_sections(doc, keywords):
    """Map page number (1-based) -> top-level section title; drop pages outside kept chapters."""
    toc = [(lvl, title.strip(), page) for lvl, title, page in doc.get_toc() if page > 0]
    top = [(t, p) for lvl, t, p in toc if lvl == 1] or [("", 1)]
    sections = {}
    for i, (title, start) in enumerate(top):
        end = top[i + 1][1] if i + 1 < len(top) else doc.page_count + 1
        keep = keywords is None or any(k in title.lower() for k in keywords)
        if keep:
            for p in range(start, end):
                sections[p] = title
    if keywords is None:                                    # front matter before first chapter
        for p in range(1, top[0][1]):
            sections.setdefault(p, "")
    return sections


def clean(text):
    text = text.replace("­", "")                       # soft hyphens
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    # PDF extraction puts every table cell / line on its own line; register bit-field
    # diagrams become '15\n14\n...\nrw\nrw'. Join single line breaks so chunks carry
    # content (e.g. 'Bit 1 UDIS: Update disable') instead of layout noise.
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    return text.strip()


def chunk(text, size=CHUNK_CHARS, overlap=OVERLAP_CHARS):
    """Split into ~size-char chunks with overlap, breaking at whitespace."""
    out, start = [], 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            cut = text.rfind(" ", start + size // 2, end)
            end = cut if cut > 0 else end
        piece = text[start:end].strip()
        if len(piece) > 80:                                # skip near-empty fragments
            out.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return out


def extract_chunks(path):
    import fitz                                            # PyMuPDF

    source, keywords = doc_info(path)
    doc = fitz.open(path)
    chunks = []
    for page_no, section in sorted(page_sections(doc, keywords).items()):
        text = clean(doc[page_no - 1].get_text())
        for i, piece in enumerate(chunk(text)):
            chunks.append({"id": f"{os.path.basename(path)}:{page_no}:{i}", "text": piece,
                           "meta": {"source": source, "file": os.path.basename(path),
                                    "page": page_no, "section": section}})
    return chunks


def get_collection(create=False):
    import chromadb

    client = chromadb.PersistentClient(path=DB_DIR)
    if create:
        return client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
    return client.get_collection(COLLECTION)


def ingest(rebuild=False):
    from sentence_transformers import SentenceTransformer
    import chromadb

    if rebuild and os.path.isdir(DB_DIR):
        try:
            chromadb.PersistentClient(path=DB_DIR).delete_collection(COLLECTION)
        except Exception:
            pass
    col = get_collection(create=True)
    done = {m["file"] for m in col.get(include=["metadatas"])["metadatas"]}
    model = SentenceTransformer(EMBED_MODEL)

    pdfs = sorted(glob.glob(os.path.join(DOC_DIR, "*.pdf")))
    if not pdfs:
        print(f"No PDFs in {DOC_DIR}")
    for path in pdfs:
        name = os.path.basename(path)
        if name in done:
            print(f"skip   {name} (already indexed)")
            continue
        chunks = extract_chunks(path)
        for i in range(0, len(chunks), 256):
            batch = chunks[i:i + 256]
            texts = [c["text"] for c in batch]
            col.add(ids=[c["id"] for c in batch], documents=texts,
                    metadatas=[c["meta"] for c in batch],
                    embeddings=model.encode(texts, normalize_embeddings=True).tolist())
        pages = len({c["meta"]["page"] for c in chunks})
        print(f"index  {name}: {pages} pages -> {len(chunks)} chunks", flush=True)
    print(f"Collection '{COLLECTION}' now holds {col.count()} chunks in {DB_DIR}")
    return col.count()


if __name__ == "__main__":
    ingest(rebuild="--rebuild" in sys.argv)
