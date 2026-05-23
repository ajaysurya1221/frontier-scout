"""
Mem0 OSS wrapper — semantic memory over past radar verdicts.

Storage: Chroma vector store persisted to memory/chroma/ (committed to repo).
Embeddings: OpenAI text-embedding-3-small (existing configured vendor).
LLM (for memory consolidation): Anthropic Claude Sonnet 4.6.

All three vendors are already in the configured SOC2 vendor list — zero new surface.

Usage:
    from scripts.memory import mem
    mem.add_verdict(tool="mem0", verdict="trial", soc2="conditional",
                    category="data", text="Full verdict block...")
    hits = mem.search("agent memory tools", limit=5)
    prior = mem.prior_verdict("LangGraph", days=30)  # None if no recent match
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
STORE_DIR = REPO_ROOT / "memory" / "chroma"


class RadarMemory:
    """Lazy-init wrapper so importing this module doesn't require mem0ai at import time."""

    def __init__(self):
        self._m = None

    def _init(self):
        if self._m is not None:
            return
        from mem0 import Memory  # imported lazily — mem0ai is heavy
        STORE_DIR.mkdir(parents=True, exist_ok=True)
        config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "ai_telemetry",
                    "path": str(STORE_DIR),
                },
            },
            "embedder": {
                "provider": "openai",
                "config": {"model": "text-embedding-3-small"},
            },
            "llm": {
                "provider": "anthropic",
                "config": {"model": "claude-sonnet-4-6"},
            },
        }
        self._m = Memory.from_config(config)

    def add_verdict(
        self,
        tool: str,
        verdict: str,
        soc2: str,
        category: str,
        text: str,
    ) -> None:
        self._init()
        self._m.add(
            text,
            user_id="frontier-scout-team",
            metadata={
                "tool": tool,
                "verdict": verdict,
                "soc2": soc2,
                "category": category,
                "added_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def search(self, query: str, limit: int = 5) -> list[dict]:
        self._init()
        return self._m.search(query=query, user_id="frontier-scout-team", limit=limit)

    def prior_verdict(self, title: str, days: int = 30, threshold: float = 0.7) -> dict | None:
        """
        Return the most recent prior verdict for this title if one exists
        within `days` days and above similarity `threshold`. Used by Scout to
        skip re-evaluating tools we already covered recently.

        Returns None if Mem0 is unavailable or no match found — never raises.
        """
        if not is_available():
            return None
        try:
            hits = self.search(title, limit=1)
        except Exception:
            return None
        if not hits:
            return None
        # Mem0's response shape: {"results": [{"memory": str, "score": float, "metadata": {...}}]}
        results = hits.get("results", []) if isinstance(hits, dict) else hits
        if not results:
            return None
        top = results[0]
        score = top.get("score", 0)
        if score < threshold:
            return None
        meta = top.get("metadata", {}) or {}
        added_at = meta.get("added_at")
        if added_at:
            try:
                ts = datetime.fromisoformat(added_at.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) - ts > timedelta(days=days):
                    return None
            except ValueError:
                pass
        return {
            "tool": meta.get("tool"),
            "verdict": meta.get("verdict"),
            "soc2": meta.get("soc2"),
            "category": meta.get("category"),
            "added_at": meta.get("added_at"),
            "score": score,
            "text": top.get("memory"),
        }


# Module-level singleton — import as `from scripts.memory import mem`
mem = RadarMemory()


def is_available() -> bool:
    """Cheap check used by Scout/Pulse to gracefully skip Mem0 if not configured."""
    if not os.environ.get("OPENAI_API_KEY"):
        return False
    try:
        import mem0  # noqa: F401
        return True
    except ImportError:
        return False
