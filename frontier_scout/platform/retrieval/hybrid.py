"""Hybrid lexical + graph retrieval with authorization filtering."""

from __future__ import annotations

import math
import re
from collections import Counter

from pydantic import BaseModel

from ..authz.engine import AuthzEngine
from ..core.types import Citation
from ..memory.store import Chunk, MemoryStore


class RetrievalResult(BaseModel):
    chunk: Chunk
    score: float
    citations: list[Citation]


class HybridRetriever:
    def __init__(self, store: MemoryStore, authz: AuthzEngine) -> None:
        self.store = store
        self.authz = authz

    def retrieve(self, query: str, *, actor: str, limit: int = 5) -> list[RetrievalResult]:
        query_terms = _terms(query)
        service_hints = {term for term in query_terms if term in {doc.service for doc in self.store.documents.values()}}
        results: list[RetrievalResult] = []
        for chunk in self.store.chunks.values():
            if not self.authz.can_read_document(actor, chunk.document_id):
                continue
            lexical = _cosine(query_terms, _terms(chunk.text))
            graph_boost = 0.2 if chunk.service in service_hints else 0.0
            if lexical == 0 and graph_boost == 0:
                continue
            citation = Citation(id=chunk.id, text=chunk.text[:240], provenance=chunk.provenance)
            results.append(RetrievalResult(chunk=chunk, score=lexical + graph_boost, citations=[citation]))
        return sorted(results, key=lambda result: result.score, reverse=True)[:limit]


def _terms(text: str) -> Counter[str]:
    return Counter(t.lower() for t in re.findall(r"[A-Za-z][A-Za-z0-9_-]+", text))


def _cosine(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[k] * b[k] for k in a.keys() & b.keys())
    if dot == 0:
        return 0.0
    mag_a = math.sqrt(sum(v * v for v in a.values()))
    mag_b = math.sqrt(sum(v * v for v in b.values()))
    return dot / (mag_a * mag_b)

