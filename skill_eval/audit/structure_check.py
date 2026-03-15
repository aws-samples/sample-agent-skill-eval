"""Structure validation against agentskills.io specification.

Checks:
- SKILL.md exists and has valid YAML frontmatter
- name field: required, 1-64 chars, lowercase+hyphens, matches directory name
- description field: required, 1-1024 chars, non-empty
- Optional fields: license, compatibility (max 500 chars), metadata, allowed-tools
- Directory structure conventions
- Progressive disclosure (SKILL.md size, reference file sizes)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from skill_eval.schemas import Finding, Severity, Category


# --- Name validation ---

_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
_CONSECUTIVE_HYPHENS = re.compile(r"--")
_MAX_NAME_LEN = 64
_MAX_DESC_LEN = 1024
_MAX_COMPAT_LEN = 500
_RECOMMENDED_MAX_LINES = 500
_RECOMMENDED_MAX_BODY_TOKENS_APPROX = 5000  # ~4 chars per token


def _parse_frontmatter(content: str) -> tuple[Optional[dict], Optional[str], int]:
    """Parse YAML frontmatter from SKILL.md content.
    
    Returns (frontmatter_dict, error_message, body_start_line).
    If parsing fails, returns (None, error_msg, 0).
    """
    lines = content.split("\n")
    
    # Find opening ---
    if not lines or lines[0].strip() != "---":
        return None, "SKILL.md does not start with YAML frontmatter (---)", 0

    # Find closing ---
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return None, "YAML frontmatter is not closed (missing second ---)", 0

    # Parse YAML
    yaml_text = "\n".join(lines[1:end_idx])
    try:
        # Use a simple YAML parser that doesn't require PyYAML
        fm = _simple_yaml_parse(yaml_text)
        return fm, None, end_idx + 1
    except Exception as e:
        return None, f"Failed to parse YAML frontmatter: {e}", 0


def _simple_yaml_parse(text: str) -> dict:
    """Minimal YAML parser for frontmatter (handles flat key-value and nested maps).
    
    Supports:
    - key: value
    - key: "quoted value"
    - key: 'quoted value'
    - key: |  (block scalar - joins lines)
    - nested maps (metadata:)
    - space-delimited strings (allowed-tools)
    
    Does NOT support: arrays, complex nesting, anchors, etc.
    For production use, consider PyYAML, but we want zero dependencies.
    """
    result = {}
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        # Check indent level
        indent = len(line) - len(line.lstrip())
        
        match = re.match(r"^(\S[\w-]*)\s*:\s*(.*)", stripped)
        if not match:
            i += 1
            continue

        key = match.group(1)
        value = match.group(2).strip()

        if value == "" or value == "|":
            # Could be nested map or block scalar
            # Look ahead for indented content
            nested_lines = []
            j = i + 1
            while j < len(lines):
                next_line = lines[j]
                if next_line.strip() == "" or (len(next_line) - len(next_line.lstrip()) > indent):
                    nested_lines.append(next_line)
                    j += 1
                else:
                    break
            
            if nested_lines:
                # Check if it's a nested map (key: value pairs)
                is_map = any(re.match(r"^\s+\S[\w-]*\s*:", nl) for nl in nested_lines if nl.strip())
                if is_map:
                    nested = {}
                    for nl in nested_lines:
                        nl_stripped = nl.strip()
                        nm = re.match(r"^(\S[\w-]*)\s*:\s*(.*)", nl_stripped)
                        if nm:
                            nk = nm.group(1)
                            nv = nm.group(2).strip().strip("'\"")
                            nested[nk] = nv
                    result[key] = nested
                else:
                    # Block scalar - join lines
                    result[key] = " ".join(nl.strip() for nl in nested_lines if nl.strip())
            else:
                result[key] = ""
            i = j
        else:
            # Strip quotes
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            result[key] = value
            i += 1

    return result


def check_structure(skill_path: str | Path) -> tuple[list[Finding], Optional[dict], int]:
    """Run all structure checks on a skill directory.

    Args:
        skill_path: Path to the skill directory

    Returns:
        Tuple of (findings, frontmatter_dict_or_None, body_start_line).
        On early failure (missing dir/file/frontmatter), frontmatter is None and body_start is 0.
    """
    skill_path = Path(skill_path)
    findings: list[Finding] = []
    
    # --- Check 1: Directory exists ---
    if not skill_path.is_dir():
        findings.append(Finding(
            code="STR-001",
            severity=Severity.CRITICAL,
            category=Category.STRUCTURE,
            title="Skill path is not a directory",
            detail=f"Expected a directory at '{skill_path}', but it doesn't exist or isn't a directory.",
            file_path=str(skill_path),
        ))
        return findings, None, 0  # Can't continue without the directory

    dir_name = skill_path.name

    # --- Check 2: SKILL.md exists ---
    skill_md = skill_path / "SKILL.md"
    if not skill_md.is_file():
        findings.append(Finding(
            code="STR-002",
            severity=Severity.CRITICAL,
            category=Category.STRUCTURE,
            title="Missing SKILL.md",
            detail="Every skill must have a SKILL.md file at its root. This is the only required file.",
            file_path=str(skill_md),
            fix="Create a SKILL.md with YAML frontmatter (name, description) and markdown instructions.",
        ))
        return findings, None, 0  # Can't continue without SKILL.md

    # --- Read and parse SKILL.md ---
    try:
        content = skill_md.read_text(encoding="utf-8")
    except Exception as e:
        findings.append(Finding(
            code="STR-003",
            severity=Severity.CRITICAL,
            category=Category.STRUCTURE,
            title="Cannot read SKILL.md",
            detail=f"Failed to read SKILL.md: {e}",
            file_path=str(skill_md),
        ))
        return findings, None, 0

    frontmatter, error, body_start = _parse_frontmatter(content)

    if error:
        findings.append(Finding(
            code="STR-004",
            severity=Severity.CRITICAL,
            category=Category.STRUCTURE,
            title="Invalid frontmatter",
            detail=error,
            file_path=str(skill_md),
            line_number=1,
            fix="SKILL.md must start with --- followed by YAML key-value pairs and a closing ---.",
        ))
        return findings, None, 0

    # --- Check 3: name field ---
    name = frontmatter.get("name")
    if not name:
        findings.append(Finding(
            code="STR-005",
            severity=Severity.CRITICAL,
            category=Category.STRUCTURE,
            title="Missing required 'name' field",
            detail="The 'name' field is required in SKILL.md frontmatter.",
            file_path=str(skill_md),
            line_number=1,
            fix="Add 'name: your-skill-name' to the frontmatter.",
        ))
    elif isinstance(name, str):
        # Validate name format
        if len(name) > _MAX_NAME_LEN:
            findings.append(Finding(
                code="STR-006",
                severity=Severity.WARNING,
                category=Category.STRUCTURE,
                title=f"Name too long ({len(name)} chars, max {_MAX_NAME_LEN})",
                detail=f"The name '{name}' exceeds the {_MAX_NAME_LEN}-character limit.",
                file_path=str(skill_md),
                fix=f"Shorten the name to {_MAX_NAME_LEN} characters or fewer.",
            ))

        if not _NAME_RE.match(name):
            issues = []
            if name != name.lower():
                issues.append("contains uppercase characters")
            if name.startswith("-") or name.endswith("-"):
                issues.append("starts or ends with a hyphen")
            if not re.match(r"^[a-z0-9-]+$", name):
                issues.append("contains characters other than lowercase letters, numbers, and hyphens")
            if _CONSECUTIVE_HYPHENS.search(name):
                issues.append("contains consecutive hyphens (--)")
            
            detail = f"The name '{name}' is invalid: {'; '.join(issues)}." if issues else f"The name '{name}' doesn't match the required pattern."
            findings.append(Finding(
                code="STR-007",
                severity=Severity.WARNING,
                category=Category.STRUCTURE,
                title="Invalid name format",
                detail=detail,
                file_path=str(skill_md),
                fix="Name must be 1-64 lowercase alphanumeric characters and hyphens, not starting/ending with hyphen.",
            ))

        # Check name matches directory name
        if name != dir_name:
            findings.append(Finding(
                code="STR-008",
                severity=Severity.INFO,
                category=Category.STRUCTURE,
                title="Name doesn't match directory",
                detail=f"Frontmatter name '{name}' doesn't match directory name '{dir_name}'.",
                file_path=str(skill_md),
                fix=f"Either rename the directory to '{name}/' or change the name field to '{dir_name}'.",
            ))

    # --- Check 4: description field ---
    desc = frontmatter.get("description")
    if not desc:
        findings.append(Finding(
            code="STR-009",
            severity=Severity.CRITICAL,
            category=Category.STRUCTURE,
            title="Missing required 'description' field",
            detail="The 'description' field is required in SKILL.md frontmatter. It's the primary trigger signal.",
            file_path=str(skill_md),
            line_number=1,
            fix="Add 'description: What it does and when to use it' to the frontmatter.",
        ))
    elif isinstance(desc, str):
        if len(desc) > _MAX_DESC_LEN:
            findings.append(Finding(
                code="STR-010",
                severity=Severity.WARNING,
                category=Category.STRUCTURE,
                title=f"Description too long ({len(desc)} chars, max {_MAX_DESC_LEN})",
                detail=f"The description exceeds the {_MAX_DESC_LEN}-character limit.",
                file_path=str(skill_md),
                fix=f"Shorten the description to {_MAX_DESC_LEN} characters. Move details to the body.",
            ))
        
        if len(desc) < 20:
            findings.append(Finding(
                code="STR-011",
                severity=Severity.WARNING,
                category=Category.STRUCTURE,
                title="Description too short",
                detail=f"The description '{desc}' is very short ({len(desc)} chars). It should describe what the skill does AND when to use it.",
                file_path=str(skill_md),
                fix="Include both what the skill does and specific trigger contexts/phrases.",
            ))

    # --- Check 5: compatibility field ---
    compat = frontmatter.get("compatibility")
    if compat and isinstance(compat, str) and len(compat) > _MAX_COMPAT_LEN:
        findings.append(Finding(
            code="STR-012",
            severity=Severity.WARNING,
            category=Category.STRUCTURE,
            title=f"Compatibility field too long ({len(compat)} chars, max {_MAX_COMPAT_LEN})",
            detail=f"The compatibility field exceeds {_MAX_COMPAT_LEN} characters.",
            file_path=str(skill_md),
        ))

    # --- Check 6: metadata field type ---
    metadata = frontmatter.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        # Try to parse as inline JSON (common in OpenClaw skills)
        if isinstance(metadata, str):
            try:
                import json
                parsed = json.loads(metadata)
                if isinstance(parsed, dict):
                    metadata = parsed  # Valid inline JSON map, accept it
                else:
                    findings.append(Finding(
                        code="STR-013",
                        severity=Severity.WARNING,
                        category=Category.STRUCTURE,
                        title="metadata field should be a mapping",
                        detail=f"The metadata field should be a YAML mapping (key: value pairs). Parsed JSON is {type(parsed).__name__}.",
                        file_path=str(skill_md),
                    ))
            except (json.JSONDecodeError, Exception):
                findings.append(Finding(
                    code="STR-013",
                    severity=Severity.WARNING,
                    category=Category.STRUCTURE,
                    title="metadata field should be a mapping",
                    detail=f"The metadata field should be a YAML mapping (key: value pairs), got string that isn't valid JSON.",
                    file_path=str(skill_md),
                ))
        else:
            findings.append(Finding(
                code="STR-013",
                severity=Severity.WARNING,
                category=Category.STRUCTURE,
                title="metadata field should be a mapping",
                detail=f"The metadata field should be a YAML mapping (key: value pairs), got {type(metadata).__name__}.",
                file_path=str(skill_md),
            ))

    # --- Check 7: Progressive disclosure - SKILL.md size ---
    lines = content.split("\n")
    body_lines = lines[body_start:] if body_start > 0 else lines
    body_text = "\n".join(body_lines)
    total_lines = len(lines)

    if total_lines > _RECOMMENDED_MAX_LINES:
        findings.append(Finding(
            code="STR-014",
            severity=Severity.INFO,
            category=Category.STRUCTURE,
            title=f"SKILL.md exceeds recommended {_RECOMMENDED_MAX_LINES} lines ({total_lines} lines)",
            detail=f"The spec recommends keeping SKILL.md under {_RECOMMENDED_MAX_LINES} lines for efficient context usage.",
            file_path=str(skill_md),
            fix="Move detailed reference material to separate files in references/ or scripts/.",
        ))

    # Approximate token count (rough: ~4 chars per token for English)
    approx_tokens = len(body_text) // 4
    if approx_tokens > _RECOMMENDED_MAX_BODY_TOKENS_APPROX:
        findings.append(Finding(
            code="STR-015",
            severity=Severity.INFO,
            category=Category.STRUCTURE,
            title=f"SKILL.md body is large (~{approx_tokens} tokens, recommended <{_RECOMMENDED_MAX_BODY_TOKENS_APPROX})",
            detail="Large SKILL.md files consume significant context when activated. The spec recommends <5000 tokens for the instructions body.",
            file_path=str(skill_md),
            fix="Use progressive disclosure: move detailed content to references/ files loaded on demand.",
        ))

    # --- Check 8: README.md conflict ---
    readme = skill_path / "README.md"
    if readme.is_file():
        findings.append(Finding(
            code="STR-016",
            severity=Severity.INFO,
            category=Category.STRUCTURE,
            title="README.md present alongside SKILL.md",
            detail="Some agents may confuse README.md with SKILL.md. The skill entry point should be SKILL.md only.",
            file_path=str(readme),
            fix="Consider removing README.md or clearly differentiating it from SKILL.md.",
        ))

    # --- Check 9: Standard directories ---
    known_dirs = {"scripts", "references", "assets", "evals", "agents"}
    actual_dirs = {d.name for d in skill_path.iterdir() if d.is_dir() and not d.name.startswith(".")}
    unknown_dirs = actual_dirs - known_dirs
    # Not a finding, just metadata — unusual dirs aren't necessarily wrong

    # --- Check 10: Scripts have no extension or are executable ---
    scripts_dir = skill_path / "scripts"
    if scripts_dir.is_dir():
        for script_file in scripts_dir.rglob("*"):
            if script_file.is_file() and script_file.suffix in (".py", ".sh", ".js", ".ts"):
                # Check for shebang
                try:
                    first_line = script_file.read_text(encoding="utf-8").split("\n")[0]
                    if script_file.suffix in (".py", ".sh") and not first_line.startswith("#!"):
                        findings.append(Finding(
                            code="STR-017",
                            severity=Severity.INFO,
                            category=Category.QUALITY,
                            title=f"Script missing shebang line",
                            detail=f"'{script_file.name}' lacks a shebang (e.g., #!/usr/bin/env python3). Agents may not know how to execute it.",
                            file_path=str(script_file),
                            line_number=1,
                            fix=f"Add '#!/usr/bin/env python3' (or appropriate) as the first line.",
                        ))
                except Exception:
                    pass

    return findings, frontmatter, body_start
