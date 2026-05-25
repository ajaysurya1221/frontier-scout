"""Deterministic gateway with budget enforcement and provider isolation."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from ..context.compiler import ExecutionPacket
from ..core.budgets import BudgetLedger


class ModelResponse(BaseModel):
    text: str
    model: str
    tokens: int
    cost_usd: float


class ModelProvider(Protocol):
    name: str

    def complete(self, packet: ExecutionPacket) -> ModelResponse:
        ...


class LocalDeterministicProvider:
    name = "local-deterministic"

    def complete(self, packet: ExecutionPacket) -> ModelResponse:
        services = sorted({citation.provenance.source_id for citation in packet.citations})
        citation_ids = ", ".join(citation.id for citation in packet.citations[:4])
        evidence_text = " ".join(citation.text for citation in packet.citations[:4]).lower()
        redis_clause = (
            "redis-cluster saturation is part of the likely dependency path; "
            if "redis" in evidence_text
            else ""
        )
        text = (
            "Incident Change Scout recommends: validate the cache dependency, "
            f"{redis_clause}"
            "reduce risky rollout blast radius, and require owner approval before "
            f"any write action. Evidence citations: {citation_ids}. "
            f"Sources considered: {len(services)}."
        )
        return ModelResponse(text=text, model=self.name, tokens=max(1, len(text.split())), cost_usd=0.0)


class ModelGateway:
    def __init__(self, provider: ModelProvider | None = None, ledger: BudgetLedger | None = None) -> None:
        self.provider = provider or LocalDeterministicProvider()
        self.ledger = ledger

    def complete(self, packet: ExecutionPacket) -> ModelResponse:
        response = self.provider.complete(packet)
        if self.ledger is not None:
            self.ledger.spend(tokens=response.tokens, usd=response.cost_usd)
        return response
