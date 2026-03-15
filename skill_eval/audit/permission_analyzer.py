"""Permission analysis for Agent Skills.

Analyzes the `allowed-tools` frontmatter field and skill instructions
to assess permission scope and over-privilege risks.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from skill_eval.schemas import Finding, Severity, Category


# Tool categories and their risk levels
TOOL_RISK_LEVELS = {
    # High risk - can execute arbitrary code or access filesystem broadly
    "Bash": "high",
    "Bash(*)": "high",
    "Shell": "high",
    "Terminal": "high",
    "Execute": "high",
    
    # Medium risk - file operations
    "Write": "medium",
    "Edit": "medium",
    "MultiEdit": "medium",
    "FileWrite": "medium",
    
    # Low risk - read-only operations
    "Read": "low",
    "ReadFile": "low",
    "Search": "low",
    "Grep": "low",
    "Glob": "low",
    "List": "low",
    "ListDir": "low",
    
    # Network operations
    "WebSearch": "medium",
    "WebFetch": "medium",
    "HttpRequest": "high",
    
    # Agent operations
    "Task": "medium",     # Can spawn sub-agents
    "TodoRead": "low",
    "TodoWrite": "low",
}

# Patterns that indicate specific Bash tool scoping
BASH_SCOPED_PATTERN = re.compile(r"Bash\(([^)]+)\)")


def analyze_permissions(
    skill_path: str | Path,
    frontmatter: Optional[dict] = None,
    skill_content: Optional[str] = None,
) -> list[Finding]:
    """Analyze permission scope from allowed-tools and skill instructions.
    
    Args:
        skill_path: Path to the skill directory
        frontmatter: Pre-parsed frontmatter dict (optional, will parse if not provided)
        skill_content: SKILL.md content (optional, will read if not provided)
        
    Returns:
        List of permission-related findings
    """
    skill_path = Path(skill_path)
    findings: list[Finding] = []
    skill_md = skill_path / "SKILL.md"
    
    # Read SKILL.md if content not provided
    if skill_content is None:
        if skill_md.is_file():
            try:
                skill_content = skill_md.read_text(encoding="utf-8")
            except Exception:
                return findings
        else:
            return findings
    
    # Parse frontmatter if not provided
    if frontmatter is None:
        from skill_eval.audit.structure_check import _parse_frontmatter
        frontmatter, error, _ = _parse_frontmatter(skill_content)
        if error or frontmatter is None:
            return findings
    
    # --- Check 1: allowed-tools field ---
    allowed_tools_raw = frontmatter.get("allowed-tools", "")
    
    if allowed_tools_raw:
        tools = allowed_tools_raw.split() if isinstance(allowed_tools_raw, str) else []
        
        high_risk_tools = []
        unscoped_bash = False
        
        for tool in tools:
            # Check for unscoped Bash
            if tool in ("Bash", "Bash(*)", "Shell", "Terminal"):
                unscoped_bash = True
                high_risk_tools.append(tool)
            elif tool.startswith("Bash(") and tool.endswith(")"):
                # Scoped Bash - extract the scope
                scope_match = BASH_SCOPED_PATTERN.match(tool)
                if scope_match:
                    scope = scope_match.group(1)
                    # Check if scope is effectively unrestricted
                    if scope == "*" or scope == "**":
                        unscoped_bash = True
                        high_risk_tools.append(tool)
                    # Scoped Bash is acceptable
            else:
                # Check against known risk levels
                risk = TOOL_RISK_LEVELS.get(tool, "unknown")
                if risk == "high":
                    high_risk_tools.append(tool)
        
        if unscoped_bash:
            findings.append(Finding(
                code="PERM-001",
                severity=Severity.WARNING,
                category=Category.PERMISSION,
                title="Unrestricted Bash/Shell access",
                detail=f"allowed-tools includes unrestricted shell access: {', '.join(high_risk_tools)}. "
                       f"This allows the skill to execute arbitrary system commands.",
                file_path=str(skill_md),
                fix="Scope Bash to specific commands, e.g., 'Bash(python3:*) Bash(git:*)' instead of 'Bash(*)'.",
            ))
        elif high_risk_tools:
            findings.append(Finding(
                code="PERM-002",
                severity=Severity.INFO,
                category=Category.PERMISSION,
                title=f"High-risk tools declared: {', '.join(high_risk_tools)}",
                detail=f"The skill declares high-risk tools in allowed-tools. Ensure these are necessary for the skill's function.",
                file_path=str(skill_md),
            ))
        
        # Check for excessive number of tools
        if len(tools) > 15:
            findings.append(Finding(
                code="PERM-003",
                severity=Severity.INFO,
                category=Category.PERMISSION,
                title=f"Large number of allowed-tools ({len(tools)})",
                detail="Many declared tools may indicate over-privilege. Skills should request only the tools they need.",
                file_path=str(skill_md),
                fix="Review each tool and remove any not required for the skill's core function.",
            ))
    
    # --- Check 2: Instructions that imply broad permissions ---
    _check_implicit_permissions(skill_content, skill_md, findings)
    
    # --- Check 3: File access patterns ---
    _check_file_access_patterns(skill_content, skill_md, findings)
    
    return findings


def _check_implicit_permissions(content: str, skill_md: Path, findings: list[Finding]) -> None:
    """Check SKILL.md body for instructions that imply broad permissions."""
    
    patterns = [
        # Sensitive file access
        (re.compile(r"(?:read|access|open|cat)\s+(?:~/|/etc/|/home/|\$HOME/|~/)\.(?:ssh|gnupg|aws|kube)", re.IGNORECASE),
         "References sensitive directory access",
         "Skill instructs agent to access sensitive directories (~/.ssh, ~/.aws, etc.)",
         Severity.WARNING),
        
        # Root/sudo access
        (re.compile(r"(?:sudo|as\s+root|with\s+root|root\s+access)", re.IGNORECASE),
         "References root/sudo access",
         "Skill instructs operations requiring root privileges",
         Severity.WARNING),
        
        # Network listener
        (re.compile(r"(?:listen|bind|serve)\s+(?:on\s+)?(?:port|0\.0\.0\.0|all\s+interfaces)", re.IGNORECASE),
         "Starts network listener",
         "Skill instructs agent to start a network listener, which could expose the machine",
         Severity.INFO),
        
        # Credential access
        (re.compile(r"(?:read|access|use|get)\s+(?:the\s+)?(?:credentials?|password|token|key)\s+(?:from|in|at)", re.IGNORECASE),
         "Accesses stored credentials",
         "Skill instructs agent to read credentials from storage",
         Severity.INFO),
    ]
    
    for line_num, line in enumerate(content.split("\n"), 1):
        for pattern, title, detail, severity in patterns:
            if pattern.search(line):
                findings.append(Finding(
                    code="PERM-004",
                    severity=severity,
                    category=Category.PERMISSION,
                    title=title,
                    detail=f"{detail}. Line: {line.strip()[:100]}",
                    file_path=str(skill_md),
                    line_number=line_num,
                ))


def _check_file_access_patterns(content: str, skill_md: Path, findings: list[Finding]) -> None:
    """Check for instructions that access files outside normal workspace."""
    
    # Look for absolute paths outside of workspace
    abs_path_pattern = re.compile(r"(?:^|\s)/(?:etc|var|tmp|usr|opt|home|root)/\S+")
    home_escape_pattern = re.compile(r"(?:~/|~\\|\$HOME/)\.(?!claude|config)", re.IGNORECASE)
    
    for line_num, line in enumerate(content.split("\n"), 1):
        # Check for system paths in instructions (not in comments or code blocks)
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("//"):
            continue
        
        if abs_path_pattern.search(stripped):
            # Exclude common safe references
            if any(safe in stripped.lower() for safe in ["example", "e.g.", "such as", "like /etc"]):
                continue
            findings.append(Finding(
                code="PERM-005",
                severity=Severity.INFO,
                category=Category.PERMISSION,
                title="References absolute system path",
                detail=f"Skill references an absolute system path. Line: {stripped[:100]}",
                file_path=str(skill_md),
                line_number=line_num,
                fix="Skills should operate within the workspace directory. Avoid absolute system paths.",
            ))
