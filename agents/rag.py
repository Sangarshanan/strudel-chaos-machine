"""Local ChromaDB knowledge index for Strudel context retrieval (RAG)."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

_COLLECTION = "strudel_knowledge"
_CHUNK_SIZE = 400

# Chunking utilities
def _md_sections(text: str, source: str) -> list[tuple[str, dict]]:
    """Split markdown into heading-delimited sections."""
    sections: list[tuple[str, dict]] = []
    heading = source
    lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            body = "\n".join(lines).strip()
            if body:
                sections.append((body, {"source": source, "heading": heading}))
            heading = line.lstrip("#").strip()
            lines = []
        else:
            lines.append(line)
    body = "\n".join(lines).strip()
    if body:
        sections.append((body, {"source": source, "heading": heading}))
    return sections


def _split(text: str, source: str, heading: str, size: int = _CHUNK_SIZE) -> list[tuple[str, dict]]:
    """Sub-split long text into fixed-size chunks."""
    if len(text) <= size:
        return [(text, {"source": source, "heading": heading})]
    chunks = []
    for i in range(0, len(text), size):
        part = text[i : i + size].strip()
        if part:
            chunks.append((part, {"source": source, "heading": f"{heading}[{i}]"}))
    return chunks


# Index knowledge in ChromaDB.
class KnowledgeIndex:
    """Thin wrapper around a ChromaDB collection for Strudel knowledge."""

    def __init__(self, persist_dir: str | Path | None = None) -> None:
        if persist_dir is not None:
            self._client: chromadb.ClientAPI = chromadb.PersistentClient(
                path=str(persist_dir)
            )
        else:
            self._client = chromadb.EphemeralClient()

        self._col = self._client.get_or_create_collection(
            name=_COLLECTION,
            embedding_function=DefaultEmbeddingFunction(),
        )

    def is_built(self) -> bool:
        return self._col.count() > 0

    def build(
        self,
        syntax_md: str,
        patterns_md: str,
        sounds: dict,
        banks: list[str],
        effects: list[str],
        rebuild: bool = False,
    ) -> int:
        """Chunk + embed all knowledge. Returns the number of documents added."""
        if rebuild and self.is_built():
            self._client.delete_collection(_COLLECTION)
            self._col = self._client.get_or_create_collection(
                name=_COLLECTION,
                embedding_function=DefaultEmbeddingFunction(),
            )

        docs: list[str] = []
        ids: list[str] = []
        metas: list[dict] = []
        seen: set[str] = set()

        def _add(text: str, meta: dict) -> None:
            uid = hashlib.md5(text.encode()).hexdigest()
            if uid not in seen:
                seen.add(uid)
                docs.append(text)
                ids.append(uid)
                metas.append(meta)

        # Markdown knowledge (syntax + patterns)
        for md, src in [(syntax_md, "syntax"), (patterns_md, "patterns")]:
            for body, meta in _md_sections(md, src):
                for chunk, m in _split(body, meta["source"], meta["heading"]):
                    _add(chunk, m)

        # Sounds by category
        for cat, items in sounds.items():
            if isinstance(items, list):
                text = f"{cat}: {', '.join(str(x) for x in items)}"
                for chunk, m in _split(text, "sounds", cat):
                    _add(chunk, m)

        # Banks and effects in batches of 30
        for label, lst in [("banks", banks), ("effects", effects)]:
            for i in range(0, len(lst), 30):
                batch = lst[i : i + 30]
                _add(
                    f"{label}: {', '.join(batch)}",
                    {"source": label, "heading": f"{label}[{i}]"},
                )

        if docs:
            self._col.add(documents=docs, ids=ids, metadatas=metas)

        return len(docs)

    def query(self, text: str, n_results: int = 6) -> list[str]:
        """Return the top-k most relevant knowledge chunks for ``text``."""
        if not text.strip() or not self.is_built():
            return []
        n = min(n_results, self._col.count())
        results = self._col.query(query_texts=[text], n_results=n)
        return [doc for doc in (results["documents"] or [[]])[0] if doc]
