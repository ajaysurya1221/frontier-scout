"""Deterministic local document and graph store."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

from ..core.ids import stable_id
from ..core.types import Provenance


class Document(BaseModel):
    id: str
    title: str
    path: str
    service: str
    visibility: str = "team"
    text: str
    provenance: Provenance


class Chunk(BaseModel):
    id: str
    document_id: str
    text: str
    service: str
    provenance: Provenance


class Edge(BaseModel):
    source: str
    relation: str
    target: str
    provenance: Provenance


class MemoryStore:
    def __init__(self) -> None:
        self.documents: dict[str, Document] = {}
        self.chunks: dict[str, Chunk] = {}
        self.edges: list[Edge] = []

    def ingest_path(self, path: Path) -> Document:
        text = path.read_text()
        metadata, body = _frontmatter(text)
        title = str(metadata.get("title") or path.stem.replace("-", " ").title())
        service = str(metadata.get("service") or _guess_service(body) or "platform")
        doc_id = stable_id("doc", str(path), body)
        provenance = Provenance(
            source_id=doc_id,
            path=str(path),
            line_start=1,
            line_end=max(1, len(text.splitlines())),
            checksum=stable_id("sha", body),
        )
        document = Document(
            id=doc_id,
            title=title,
            path=str(path),
            service=service,
            visibility=str(metadata.get("visibility") or "team"),
            text=body,
            provenance=provenance,
        )
        self.documents[doc_id] = document
        for i, chunk_text in enumerate(_chunk(body)):
            chunk_id = stable_id("chunk", doc_id, i, chunk_text)
            self.chunks[chunk_id] = Chunk(
                id=chunk_id,
                document_id=doc_id,
                text=chunk_text,
                service=service,
                provenance=provenance,
            )
        for relation, target in _extract_edges(body):
            self.edges.append(
                Edge(source=f"service:{service}", relation=relation, target=target, provenance=provenance)
            )
        self.edges.append(
            Edge(source=f"document:{doc_id}", relation="about", target=f"service:{service}", provenance=provenance)
        )
        return document

    def graph_neighbors(self, service: str) -> list[Edge]:
        needle = f"service:{service}"
        return [edge for edge in self.edges if edge.source == needle or edge.target == needle]


def ingest_directory(path: Path) -> MemoryStore:
    store = MemoryStore()
    for file in sorted(path.rglob("*.md")):
        store.ingest_path(file)
    return store


def _frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    metadata: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()
    return metadata, parts[2].strip()


def _chunk(text: str, max_words: int = 90) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    return [" ".join(words[i : i + max_words]) for i in range(0, len(words), max_words)]


def _guess_service(text: str) -> str | None:
    match = re.search(r"\b(service|system):\s*([A-Za-z0-9_-]+)", text, re.I)
    return match.group(2).lower() if match else None


def _extract_edges(text: str) -> list[tuple[str, str]]:
    edges: list[tuple[str, str]] = []
    for match in re.finditer(r"\b(depends_on|calls|owned_by|alerts_to):\s*([A-Za-z0-9_:@.-]+)", text, re.I):
        relation = match.group(1).lower()
        target = match.group(2)
        if relation == "owned_by" and not target.startswith("user:"):
            target = f"user:{target}"
        elif relation != "owned_by" and not target.startswith("service:"):
            target = f"service:{target.lower()}"
        edges.append((relation, target))
    return edges
