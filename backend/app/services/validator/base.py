"""
Base models and definitions for the validation engine.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class CheckResult(BaseModel):
    """
    Standardized result for an individual validation check.
    Supports boolean evaluation (`bool(result) == result.passed`).
    """

    check_name: str = Field(..., description="Name/identifier of the check performed")
    passed: bool = Field(..., description="Whether the check passed")
    detail: Optional[str] = Field(
        default=None, description="Detailed explanation if failed or warning"
    )
    errors: List[str] = Field(default_factory=list, description="List of specific error messages")
    status: Optional[str] = Field(
        default=None,
        description="Evaluation status (e.g. verified, failed, domain_error, unsupported, timeout, inconclusive)",
    )
    confidence: Optional[str] = Field(
        default=None,
        description="Confidence category (e.g. sympy_verified, rule_only)",
    )

    def __bool__(self) -> bool:
        return self.passed

    def to_dict(self) -> dict:
        """Convert to dictionary matching the ValidationReport checks schema."""
        res: dict = {
            "check": self.check_name,
            "passed": self.passed,
        }
        if self.detail is not None:
            res["detail"] = self.detail
        if self.status is not None:
            res["status"] = self.status
        if self.confidence is not None:
            res["confidence"] = self.confidence
        return res


class ValidationReport(BaseModel):
    """
    Consolidated report summarizing all validation layers:
    1. Syntax (VAL-01)
    2. Logic & Uniqueness (VAL-02)
    3. Formal Mathematical CAS Evaluation (VAL-03)
    4. Deterministic Rule-Based Fallback & Invariants (VAL-04)
    """

    passed: bool = Field(..., description="Whether all mandatory validation stages passed")
    status: str = Field(
        ...,
        description="Consolidated status: 'passed' (all verified), 'warning' (fallback / soft warnings), or 'failed' (invalid question)",
    )
    confidence: str = Field(
        default="rule_only",
        description="Overall mathematical confidence: 'sympy_verified' (CAS formal proof) or 'rule_only' (heuristic/rule fallback)",
    )
    checks: List[CheckResult] = Field(
        default_factory=list, description="List of individual validation check results"
    )
    errors: List[str] = Field(
        default_factory=list, description="Consolidated list of all error messages across checks"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="List of warnings (e.g. CAS unsupported or timeout fallback)",
    )
    execution_time_ms: float = Field(
        default=0.0, description="Total wall-clock execution time in milliseconds"
    )

    def __bool__(self) -> bool:
        return self.passed

    def to_dict(self) -> dict:
        """Convert to dictionary matching the ValidationReport JSON schema."""
        return {
            "passed": self.passed,
            "status": self.status,
            "confidence": self.confidence,
            "errors": self.errors,
            "warnings": self.warnings,
            "execution_time_ms": round(self.execution_time_ms, 2),
            "checks": [c.to_dict() for c in self.checks],
        }
