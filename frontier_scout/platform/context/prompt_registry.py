"""Prompt registry validation."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class PromptMetadata(BaseModel):
    version: str
    author: str
    created: str
    eval_id: str
    changelog: str
    body: str


def load_prompt(path: Path) -> PromptMetadata:
    text = path.read_text()
    if not text.startswith("---"):
        raise ValueError(f"{path} missing prompt metadata header")
    parts = text.split("---", 2)
    metadata: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()
    metadata["body"] = parts[2].strip()
    for required in ("version", "author", "created", "eval_id", "changelog"):
        if not metadata.get(required):
            raise ValueError(f"{path} missing prompt metadata: {required}")
    return PromptMetadata(**metadata)
