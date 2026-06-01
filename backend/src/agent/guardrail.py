from __future__ import annotations

from src.services.rbac import guard_evidence_blocks

__all__ = ["guard_evidence"]


def guard_evidence(
    evidence: list,
    *,
    role: str,
    payroll_access: bool = False,
    payroll_confirmed: bool = False,
) -> list:
    return guard_evidence_blocks(
        evidence,
        role=role,
        payroll_access=payroll_access,
        payroll_confirmed=payroll_confirmed,
    )
