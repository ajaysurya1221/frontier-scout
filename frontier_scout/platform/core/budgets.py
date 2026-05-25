"""Cost and loop budget accounting."""

from __future__ import annotations

from pydantic import BaseModel


class Budget(BaseModel):
    max_steps: int = 12
    max_retries: int = 1
    max_tokens: int = 12000
    max_usd: float = 0.25


class BudgetLedger(BaseModel):
    budget: Budget
    steps: int = 0
    retries: int = 0
    tokens: int = 0
    usd: float = 0.0

    def spend(self, *, tokens: int = 0, usd: float = 0.0, step: bool = True) -> None:
        if step:
            self.steps += 1
        self.tokens += tokens
        self.usd += usd
        if self.steps > self.budget.max_steps:
            raise RuntimeError("step budget exceeded")
        if self.tokens > self.budget.max_tokens:
            raise RuntimeError("token budget exceeded")
        if self.usd > self.budget.max_usd:
            raise RuntimeError("dollar budget exceeded")

    def retry(self) -> None:
        self.retries += 1
        if self.retries > self.budget.max_retries:
            raise RuntimeError("retry budget exceeded")

