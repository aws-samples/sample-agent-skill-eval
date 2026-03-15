"""Configuration file support for skill-eval.

Reads `.skilleval.yaml` (or `.skilleval.yml`) from the skill directory
or any parent directory, allowing users to customize audit behavior.

Supported configuration:

```yaml
# .skilleval.yaml
audit:
  # Ignore specific finding codes entirely
  ignore:
    - STR-008    # Directory name mismatch is fine for us
    - STR-017    # README alongside SKILL.md is intentional

  # Override severity for specific codes
  severity_overrides:
    SEC-002: WARNING    # Downgrade external URL from CRITICAL to WARNING
    STR-011: CRITICAL   # Upgrade short description to CRITICAL for our team

  # Additional domains to treat as safe (won't trigger SEC-002)
  safe_domains:
    - api.internal.example.com
    - wiki.company.com

  # Custom regex rules (experimental)
  custom_rules:
    - code: CUSTOM-001
      pattern: "TODO|FIXME|HACK"
      severity: INFO
      message: "Found TODO/FIXME/HACK comment"
      file_pattern: "*.py"

  # Minimum passing score (default: 0, set higher for stricter CI)
  min_score: 70
```
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Try to import yaml, fall back gracefully
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


@dataclass
class CustomRule:
    """A user-defined regex-based audit rule."""
    code: str
    pattern: str
    severity: str = "WARNING"
    message: str = ""
    file_pattern: str = "*"

    def __post_init__(self):
        self._compiled = re.compile(self.pattern)

    @property
    def regex(self) -> re.Pattern:
        return self._compiled


@dataclass
class AuditConfig:
    """Configuration for audit behavior."""
    ignore: set[str] = field(default_factory=set)
    severity_overrides: dict[str, str] = field(default_factory=dict)
    safe_domains: set[str] = field(default_factory=set)
    custom_rules: list[CustomRule] = field(default_factory=list)
    min_score: int = 0

    @classmethod
    def empty(cls) -> "AuditConfig":
        """Return an empty (default) configuration."""
        return cls()


def _find_config_file(start_path: Path) -> Optional[Path]:
    """Search for .skilleval.yaml/.yml from start_path up to filesystem root."""
    current = start_path.resolve()
    for _ in range(20):  # Safety limit on traversal depth
        for name in (".skilleval.yaml", ".skilleval.yml"):
            candidate = current / name
            if candidate.is_file():
                return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def load_config(skill_path: str | Path) -> AuditConfig:
    """Load audit configuration from .skilleval.yaml if present.

    Searches the skill directory and parent directories for the config file.
    Returns an empty config if no file is found or YAML is not available.

    Args:
        skill_path: Path to the skill directory.

    Returns:
        AuditConfig instance.
    """
    path = Path(skill_path).resolve()
    config_file = _find_config_file(path)

    if config_file is None:
        return AuditConfig.empty()

    if not HAS_YAML:
        import sys
        print(
            f"Warning: Found {config_file.name} but PyYAML is not installed. "
            "Install with: pip install pyyaml",
            file=sys.stderr,
        )
        return AuditConfig.empty()

    try:
        raw = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    except Exception:
        return AuditConfig.empty()

    if not isinstance(raw, dict):
        return AuditConfig.empty()

    audit = raw.get("audit", {})
    if not isinstance(audit, dict):
        return AuditConfig.empty()

    # Parse ignore list
    ignore_list = audit.get("ignore", [])
    ignore = set(ignore_list) if isinstance(ignore_list, list) else set()

    # Parse severity overrides
    overrides_raw = audit.get("severity_overrides", {})
    severity_overrides = {}
    if isinstance(overrides_raw, dict):
        for code, sev in overrides_raw.items():
            if isinstance(sev, str) and sev.upper() in ("CRITICAL", "WARNING", "INFO"):
                severity_overrides[str(code)] = sev.upper()

    # Parse safe domains
    domains_raw = audit.get("safe_domains", [])
    safe_domains = set(domains_raw) if isinstance(domains_raw, list) else set()

    # Parse custom rules
    custom_rules = []
    rules_raw = audit.get("custom_rules", [])
    if isinstance(rules_raw, list):
        for rule_dict in rules_raw:
            if isinstance(rule_dict, dict) and "code" in rule_dict and "pattern" in rule_dict:
                try:
                    custom_rules.append(CustomRule(
                        code=str(rule_dict["code"]),
                        pattern=str(rule_dict["pattern"]),
                        severity=str(rule_dict.get("severity", "WARNING")).upper(),
                        message=str(rule_dict.get("message", "")),
                        file_pattern=str(rule_dict.get("file_pattern", "*")),
                    ))
                except re.error:
                    pass  # Skip rules with invalid regex

    # Parse min_score
    min_score = audit.get("min_score", 0)
    if not isinstance(min_score, int):
        min_score = 0

    return AuditConfig(
        ignore=ignore,
        severity_overrides=severity_overrides,
        safe_domains=safe_domains,
        custom_rules=custom_rules,
        min_score=min_score,
    )


def apply_config(
    findings: list,
    config: AuditConfig,
) -> list:
    """Apply configuration to findings: ignore codes, override severities.

    Args:
        findings: List of Finding objects.
        config: AuditConfig to apply.

    Returns:
        Filtered and modified list of findings.
    """
    from skill_eval.schemas import Severity

    result = []
    for f in findings:
        # Skip ignored codes
        if f.code in config.ignore:
            continue

        # Override severity if configured
        if f.code in config.severity_overrides:
            new_sev = config.severity_overrides[f.code]
            f = type(f)(
                code=f.code,
                severity=Severity(new_sev),
                category=f.category,
                title=f.title,
                detail=f.detail,
                file_path=f.file_path,
                line_number=f.line_number,
                fix=f.fix,
            )

        result.append(f)

    return result
