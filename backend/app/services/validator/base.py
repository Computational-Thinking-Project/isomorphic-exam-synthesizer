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
        description="Evaluation status (e.g. verified, failed, domain_error, unsupported, timeout)",
    )
    confidence: Optional[str] = Field(
        default=None,
        description="Confidence category (e.g. sympy_verified, rule_only)",
    )

    def __bool__(self) -> bool:
        return self.passed

    def to_dict(self) -> dict:
        """Convert to dictionary matching the ValidationReport checks schema."""
        res = {
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
