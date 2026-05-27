from __future__ import annotations

from src.services.rbac import guard_evidence_blocks

__all__ = ["guard_evidence"]


def guard_evidence(evidence: list, *, role: str) -> list:
    return guard_evidence_blocks(evidence, role=role)
