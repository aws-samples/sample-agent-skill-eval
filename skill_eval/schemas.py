"""Data structures for skill evaluation findings and reports."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    """Finding severity levels."""
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


class Category(str, Enum):
    """Finding categories."""
    STRUCTURE = "STRUCTURE"       # agentskills.io spec compliance
    SECURITY = "SECURITY"         # Secrets, injection, exfil
    PERMISSION = "PERMISSION"     # allowed-tools analysis
    QUALITY = "QUALITY"           # Best practices, style


@dataclass
class Finding:
    """A single evaluation finding."""
    code: str                     # e.g., "SEC-001", "STR-003"
    severity: Severity
    category: Category
    title: str                    # Short description
    detail: str                   # Full explanation
    file_path: Optional[str] = None   # File where the issue was found
    line_number: Optional[int] = None # Line number (1-indexed)
    fix: Optional[str] = None    # Suggested remediation

    def to_dict(self) -> dict:
        d = asdict(self)
        d["severity"] = self.severity.value
        d["category"] = self.category.value
        return d


@dataclass
class AuditReport:
    """Complete audit report for a skill."""
    skill_name: str
    skill_path: str
    score: int                    # 0-100
    grade: str                    # A/B/C/D/F
    findings: list[Finding] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)  # Extra info (file count, line count, etc.)

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.CRITICAL)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.WARNING)

    @property
    def info_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.INFO)

    @property
    def passed(self) -> bool:
        """No critical findings."""
        return self.critical_count == 0

    def to_dict(self) -> dict:
        return {
            "skill_name": self.skill_name,
            "skill_path": self.skill_path,
            "score": self.score,
            "grade": self.grade,
            "passed": self.passed,
            "summary": {
                "critical": self.critical_count,
                "warning": self.warning_count,
                "info": self.info_count,
                "total": len(self.findings),
            },
            "findings": [f.to_dict() for f in self.findings],
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


def calculate_grade(score: int) -> str:
    """Convert numeric score to letter grade."""
    if score >= 90:
        return "A"
    elif score >= 80:
        return "B"
    elif score >= 70:
        return "C"
    elif score >= 60:
        return "D"
    else:
        return "F"


def calculate_score(findings: list[Finding]) -> int:
    """Calculate score from findings. Start at 100, deduct per finding."""
    score = 100
    for f in findings:
        if f.severity == Severity.CRITICAL:
            score -= 25
        elif f.severity == Severity.WARNING:
            score -= 10
        elif f.severity == Severity.INFO:
            score -= 2
    return max(0, score)
