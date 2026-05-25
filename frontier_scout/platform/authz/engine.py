"""A tiny deterministic ReBAC evaluator used in retrieval and action paths."""

from __future__ import annotations

from pydantic import BaseModel

from ..core.errors import AuthorizationDenied


class RelationTuple(BaseModel):
    subject: str
    relation: str
    object: str


class AuthzEngine:
    def __init__(self, tuples: list[RelationTuple] | None = None) -> None:
        self._tuples = tuples or []

    def add(self, subject: str, relation: str, object_: str) -> None:
        self._tuples.append(RelationTuple(subject=subject, relation=relation, object=object_))

    def check(self, subject: str, relation: str, object_: str) -> bool:
        direct = RelationTuple(subject=subject, relation=relation, object=object_)
        if direct in self._tuples:
            return True
        if relation == "read" and RelationTuple(subject=subject, relation="owner", object=object_) in self._tuples:
            return True
        if object_.startswith("document:"):
            service = object_.split(":", 2)[1]
            return RelationTuple(subject=subject, relation=relation, object=f"service:{service}") in self._tuples
        if object_.startswith("tool:"):
            scope = object_.split(":", 1)[1]
            return RelationTuple(subject=subject, relation=f"tool:{scope}", object="platform") in self._tuples
        return False

    def require(self, subject: str, relation: str, object_: str) -> None:
        if not self.check(subject, relation, object_):
            raise AuthorizationDenied(f"{subject} cannot {relation} {object_}")

    def can_read_document(self, subject: str, document_id: str) -> bool:
        return self.check(subject, "read", f"document:{document_id}")

    def can_call_tool(self, subject: str, scope: str) -> bool:
        return self.check(subject, "call", f"tool:{scope}")

    def can_approve_action(self, subject: str, service: str) -> bool:
        return self.check(subject, "owner", f"service:{service}") or self.check(
            subject, "approver", f"service:{service}"
        )

    @property
    def tuples(self) -> list[RelationTuple]:
        return list(self._tuples)
