"""Security scanning for Agent Skills.

Checks:
- Secret detection (API keys, tokens, passwords, connection strings)
- External URL/endpoint inventory (data exfiltration risk surface)
- Subprocess/shell command analysis in scripts
- Unsafe dependency installation patterns (supply chain risk)
- Prompt injection surface analysis
- Unsafe deserialization (pickle, yaml.load, marshal, shelve)
- Dynamic import/code generation (importlib, __import__, compile, types)
- Base64 encoded payload detection
- MCP server reference detection
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from skill_eval.schemas import Finding, Severity, Category


# --- Secret detection patterns ---
# Based on common patterns from detect-secrets, truffleHog, gitleaks
# We focus on patterns likely to appear in skill files

SECRET_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    # API Keys (generic)
    ("Generic API Key assignment",
     re.compile(r"""(?:api[_-]?key|apikey|api[_-]?secret)\s*[:=]\s*['"]([a-zA-Z0-9_\-]{20,})['"]""", re.IGNORECASE),
     "Potential API key found in assignment"),
    
    # AWS
    ("AWS Access Key",
     re.compile(r"AKIA[0-9A-Z]{16}"),
     "AWS Access Key ID detected"),
    ("AWS Secret Key",
     re.compile(r"""(?:aws[_-]?secret[_-]?(?:access[_-]?)?key|secret[_-]?key)\s*[:=]\s*['"]([a-zA-Z0-9/+]{40})['"]""", re.IGNORECASE),
     "Potential AWS Secret Access Key"),
    
    # GitHub
    ("GitHub Token (classic)",
     re.compile(r"ghp_[a-zA-Z0-9]{36}"),
     "GitHub Personal Access Token detected"),
    ("GitHub Token (fine-grained)",
     re.compile(r"github_pat_[a-zA-Z0-9_]{82}"),
     "GitHub Fine-Grained Token detected"),
    ("GitHub OAuth",
     re.compile(r"gho_[a-zA-Z0-9]{36}"),
     "GitHub OAuth Token detected"),
    
    # OpenAI
    ("OpenAI API Key",
     re.compile(r"sk-[a-zA-Z0-9]{20,}T3BlbkFJ[a-zA-Z0-9]{20,}"),
     "OpenAI API key detected"),
    ("OpenAI API Key (proj)",
     re.compile(r"sk-proj-[a-zA-Z0-9_\-]{40,}"),
     "OpenAI project API key detected"),
    
    # Anthropic
    ("Anthropic API Key",
     re.compile(r"sk-ant-[a-zA-Z0-9_\-]{40,}"),
     "Anthropic API key detected"),
    
    # Slack
    ("Slack Token",
     re.compile(r"xox[bpors]-[0-9a-zA-Z\-]{10,}"),
     "Slack token detected"),
    ("Slack Webhook",
     re.compile(r"https://hooks\.slack\.com/services/T[a-zA-Z0-9_]+/B[a-zA-Z0-9_]+/[a-zA-Z0-9_]+"),
     "Slack webhook URL detected"),
    
    # Generic secrets
    ("Generic Password",
     re.compile(r"""(?:password|passwd|pwd)\s*[:=]\s*['"]([^'"]{8,})['"]""", re.IGNORECASE),
     "Potential password in assignment"),
    ("Generic Token",
     re.compile(r"""(?:token|bearer|auth[_-]?token)\s*[:=]\s*['"]([a-zA-Z0-9_\-\.]{20,})['"]""", re.IGNORECASE),
     "Potential token in assignment"),
    ("Generic Secret",
     re.compile(r"""(?:secret|client[_-]?secret)\s*[:=]\s*['"]([a-zA-Z0-9_\-]{16,})['"]""", re.IGNORECASE),
     "Potential secret in assignment"),
    
    # Connection strings
    ("Database Connection String",
     re.compile(r"(?:mongodb|postgres|mysql|redis)://[^\s'\"]+:[^\s'\"]+@[^\s'\"]+", re.IGNORECASE),
     "Database connection string with credentials detected"),
    
    # Private keys
    ("Private Key",
     re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
     "Private key detected"),
    
    # High entropy strings (simplified - long hex or base64 strings that look like secrets)
    ("Potential Base64 Secret",
     re.compile(r"""(?:key|secret|token|password|credential)\s*[:=]\s*['"]([A-Za-z0-9+/=]{40,})['"]""", re.IGNORECASE),
     "Long encoded string in secret-like variable"),
]

# --- Patterns that look like secrets but are usually safe ---
SECRET_ALLOWLIST = [
    re.compile(r"your[-_]?(?:api)?[-_]?key[-_]?here", re.IGNORECASE),
    re.compile(r"<your[-_]", re.IGNORECASE),
    re.compile(r"\$\{?\w+\}?"),       # Environment variable references
    re.compile(r"process\.env\.\w+"),  # Node.js env vars
    re.compile(r"os\.environ"),        # Python env vars
    re.compile(r"PLACEHOLDER", re.IGNORECASE),
    re.compile(r"xxx+", re.IGNORECASE),
    re.compile(r"CHANGEME", re.IGNORECASE),
]

# --- External URL patterns ---
URL_PATTERN = re.compile(r"https?://[^\s'\"\)>\]]+", re.IGNORECASE)

# Well-known safe domains (documentation, specs, standards)
SAFE_DOMAINS = {
    "github.com", "raw.githubusercontent.com",
    "docs.anthropic.com", "docs.claude.com", "anthropic.com",
    "agentskills.io",
    "docs.python.org", "pypi.org",
    "developer.mozilla.org", "mdn.io",
    "owasp.org",
    "stackoverflow.com",
    "wikipedia.org",
    "example.com", "example.org",
    "localhost", "127.0.0.1",
}

# --- Subprocess / shell patterns ---
SUBPROCESS_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    ("subprocess.run/call/Popen",
     re.compile(r"subprocess\.(run|call|Popen|check_output|check_call)\s*\("),
     "Subprocess execution detected"),
    ("os.system",
     re.compile(r"os\.system\s*\("),
     "os.system execution detected"),
    ("os.popen",
     re.compile(r"os\.popen\s*\("),
     "os.popen execution detected"),
    ("shell=True",
     re.compile(r"shell\s*=\s*True"),
     "shell=True is dangerous — allows shell injection"),
    ("eval/exec",
     re.compile(r"(?:^|\s)(?:eval|exec)\s*\("),
     "eval/exec detected — can execute arbitrary code"),
    # Note: backtick pattern removed — causes massive false positives in Python
    # f-strings and markdown. Shell backtick execution is rare in skill scripts.
]

# --- Unsafe install patterns ---
INSTALL_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    ("pip install",
     re.compile(r"pip3?\s+install\s+(?!-r\s)", re.IGNORECASE),
     "Direct pip install — dependency not pinned in requirements"),
    ("npm install",
     re.compile(r"npm\s+install\s+", re.IGNORECASE),
     "npm install detected"),
    ("curl | sh",
     re.compile(r"curl\s+.*\|\s*(?:bash|sh|zsh)", re.IGNORECASE),
     "curl-pipe-shell pattern — extremely dangerous supply chain risk"),
    ("wget | sh",
     re.compile(r"wget\s+.*\|\s*(?:bash|sh|zsh)", re.IGNORECASE),
     "wget-pipe-shell pattern — extremely dangerous supply chain risk"),
]

# --- Injection surface patterns ---
# Patterns in SKILL.md instructions that might make the skill vulnerable to prompt injection
INJECTION_SURFACE_PATTERNS: list[tuple[str, re.Pattern, str, str]] = [
    ("Unbounded user input handling",
     re.compile(r"(?:read|accept|take|use|process)\s+(?:any|all|whatever|user)\s+(?:input|content|data|text)", re.IGNORECASE),
     "Skill instructs agent to process arbitrary user input without validation",
     "Add input validation or scope restrictions"),
    ("Execute user-provided code/commands",
     re.compile(r"(?:run|execute|eval)\s+(?:the\s+)?(?:user|their|provided|given)\s+(?:code|command|script|query)", re.IGNORECASE),
     "Skill instructs agent to execute user-provided code",
     "Never execute user input directly; validate and sandbox"),
    ("Write to arbitrary paths",
     re.compile(r"(?:write|save|create)\s+(?:to|at|in)\s+(?:any|the\s+specified|user|given)\s+(?:path|location|directory|file)", re.IGNORECASE),
     "Skill allows writing to user-specified paths without restrictions",
     "Restrict write paths to a workspace directory"),
]

# --- Unsafe deserialization patterns (SEC-006) ---
DESERIALIZATION_PATTERNS: list[tuple[str, re.Pattern, str, str]] = [
    ("pickle.load/loads",
     re.compile(r"(?:c?[Pp]ickle)\.(?:load|loads)\s*\("),
     "pickle deserialization detected — can execute arbitrary code",
     "CRITICAL"),
    ("marshal.loads",
     re.compile(r"marshal\.loads?\s*\("),
     "marshal deserialization detected — can execute arbitrary code",
     "CRITICAL"),
    ("shelve.open",
     re.compile(r"shelve\.open\s*\("),
     "shelve.open uses pickle internally — can execute arbitrary code",
     "CRITICAL"),
    ("yaml.load without SafeLoader",
     re.compile(r"yaml\.load\s*\("),
     "yaml.load without SafeLoader can execute arbitrary code",
     "WARNING"),
]

# yaml.safe_load is the safe alternative — no flag needed
YAML_SAFE_PATTERN = re.compile(r"yaml\.safe_load\s*\(")
YAML_SAFE_LOADER_PATTERN = re.compile(r"Loader\s*=\s*(?:yaml\.)?SafeLoader")

# --- Dynamic import / code generation patterns (SEC-007) ---
DYNAMIC_IMPORT_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    ("importlib.import_module",
     re.compile(r"importlib\.import_module\s*\("),
     "Dynamic module import detected"),
    ("__import__",
     re.compile(r"__import__\s*\("),
     "Dynamic import via __import__ detected"),
    ("compile()",
     re.compile(r"(?<!\w)compile\s*\(\s*['\"]"),
     "Code compilation via compile() detected"),
    ("types.FunctionType",
     re.compile(r"types\.FunctionType\s*\("),
     "Dynamic function creation via types.FunctionType"),
    ("types.CodeType",
     re.compile(r"types\.CodeType\s*\("),
     "Dynamic code object creation via types.CodeType"),
]

# --- Base64 encoded payload patterns (SEC-008) ---
BASE64_DECODE_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    ("base64.b64decode",
     re.compile(r"base64\.b64decode\s*\("),
     "Base64 decoding detected"),
    ("base64.decodebytes",
     re.compile(r"base64\.decodebytes\s*\("),
     "Base64 decodebytes detected"),
    ("atob()",
     re.compile(r"(?<!\w)atob\s*\("),
     "JavaScript atob() base64 decoding detected"),
]

# Pattern for long base64 strings (>100 chars of base64 alphabet)
LONG_BASE64_STRING = re.compile(r"""['"]([A-Za-z0-9+/=]{100,})['"]""")

# Pattern for eval/exec near base64 (on same line or adjacent)
EVAL_EXEC_PATTERN = re.compile(r"(?:eval|exec)\s*\(", re.IGNORECASE)

# --- MCP server reference patterns (SEC-009) ---
MCP_CONFIG_PATTERNS: list[tuple[str, re.Pattern, str, str]] = [
    ("mcpServers config block",
     re.compile(r"""(?:["']?mcpServers["']?|["']?mcp_servers["']?)\s*[:=]""", re.IGNORECASE),
     "MCP server configuration block detected — could connect to external servers",
     "WARNING"),
    ("npx -y external package",
     re.compile(r"npx\s+-y\s+@?[a-zA-Z0-9_\-]+(?:/[a-zA-Z0-9_\-]+)?"),
     "npx -y auto-installs and runs a package — supply chain risk for MCP servers",
     "CRITICAL"),
    ("MCP/SSE endpoint URL",
     re.compile(r"https?://[^\s'\"]+/(?:mcp|sse)(?:[/\s'\"]|$)", re.IGNORECASE),
     "Reference to external MCP/SSE endpoint detected",
     "WARNING"),
]


def _scan_file_for_secrets(file_path: Path, content: str) -> list[Finding]:
    """Scan a single file for secret patterns."""
    findings = []
    
    for line_num, line in enumerate(content.split("\n"), 1):
        for pattern_name, pattern, description in SECRET_PATTERNS:
            match = pattern.search(line)
            if match:
                # Check against allowlist
                matched_text = match.group(0)
                if any(allow.search(matched_text) for allow in SECRET_ALLOWLIST):
                    continue
                # Also check the full line for allowlist patterns
                if any(allow.search(line) for allow in SECRET_ALLOWLIST):
                    continue
                
                findings.append(Finding(
                    code="SEC-001",
                    severity=Severity.CRITICAL,
                    category=Category.SECURITY,
                    title=f"Secret detected: {pattern_name}",
                    detail=f"{description}. Line: {line.strip()[:100]}{'...' if len(line.strip()) > 100 else ''}",
                    file_path=str(file_path),
                    line_number=line_num,
                    fix="Remove the secret. Use environment variables or a secrets manager instead.",
                ))
    
    return findings


def _scan_file_for_urls(file_path: Path, content: str) -> list[Finding]:
    """Scan a file for external URLs."""
    findings = []
    seen_urls = set()
    
    for line_num, line in enumerate(content.split("\n"), 1):
        for match in URL_PATTERN.finditer(line):
            url = match.group(0).rstrip(".,;:)]}'\"")
            if url in seen_urls:
                continue
            seen_urls.add(url)
            
            # Extract domain
            domain_match = re.match(r"https?://([^/:]+)", url)
            if not domain_match:
                continue
            domain = domain_match.group(1).lower()
            
            # Skip safe domains (exact match or proper subdomain)
            if any(domain == safe or domain.endswith("." + safe) for safe in SAFE_DOMAINS):
                continue
            
            # Check if it's in a script (higher risk) vs documentation/comments (lower risk)
            is_script = file_path.suffix in (".py", ".sh", ".js", ".ts")
            
            # In scripts, check if the URL is in a comment line
            line_stripped = line.strip()
            is_comment = (line_stripped.startswith("#") or line_stripped.startswith("//") or 
                         line_stripped.startswith("*") or line_stripped.startswith("\"\"\""))
            
            if is_script and not is_comment:
                severity = Severity.WARNING
            else:
                severity = Severity.INFO
            
            findings.append(Finding(
                code="SEC-002",
                severity=severity,
                category=Category.SECURITY,
                title=f"External URL: {domain}",
                detail=f"URL: {url[:120]}{'...' if len(url) > 120 else ''}",
                file_path=str(file_path),
                line_number=line_num,
                fix="Document why this external endpoint is necessary. External calls are a data exfiltration risk.",
            ))
    
    return findings


def _scan_file_for_subprocess(file_path: Path, content: str) -> list[Finding]:
    """Scan script files for subprocess execution patterns."""
    findings = []
    
    if file_path.suffix not in (".py", ".sh", ".js", ".ts", ".bash"):
        return findings
    
    for line_num, line in enumerate(content.split("\n"), 1):
        for pattern_name, pattern, description in SUBPROCESS_PATTERNS:
            if pattern.search(line):
                # shell=True is always a warning; others are INFO
                severity = Severity.WARNING if "shell" in pattern_name.lower() or "eval" in pattern_name.lower() else Severity.INFO
                
                findings.append(Finding(
                    code="SEC-003",
                    severity=severity,
                    category=Category.SECURITY,
                    title=f"Subprocess pattern: {pattern_name}",
                    detail=f"{description}. Line: {line.strip()[:100]}",
                    file_path=str(file_path),
                    line_number=line_num,
                    fix="Ensure inputs are validated before passing to subprocess. Avoid shell=True.",
                ))
    
    return findings


def _scan_file_for_installs(file_path: Path, content: str) -> list[Finding]:
    """Scan for unsafe dependency installation patterns.

    Only scans script files and shell files — skips documentation (.md) files
    where install commands are instructions for the user, not executable code.
    curl|bash and wget|bash are still flagged in all files due to extreme risk.
    """
    findings = []

    # Skip documentation files for non-critical patterns (pip/npm in docs are user instructions)
    is_doc = file_path.suffix in (".md", ".txt", ".rst")

    for line_num, line in enumerate(content.split("\n"), 1):
        for pattern_name, pattern, description in INSTALL_PATTERNS:
            if pattern.search(line):
                is_pipe_shell = "curl" in pattern_name.lower() or "wget" in pattern_name.lower()
                # Skip pip/npm in documentation files (user instructions, not executable code)
                if is_doc and not is_pipe_shell:
                    continue
                severity = Severity.CRITICAL if is_pipe_shell else Severity.WARNING

                findings.append(Finding(
                    code="SEC-004",
                    severity=severity,
                    category=Category.SECURITY,
                    title=f"Unsafe install: {pattern_name}",
                    detail=f"{description}. Line: {line.strip()[:100]}",
                    file_path=str(file_path),
                    line_number=line_num,
                    fix="Pin dependencies in a requirements file. Never pipe curl output to shell.",
                ))
    
    return findings


def _scan_file_for_deserialization(file_path: Path, content: str) -> list[Finding]:
    """Scan script files for unsafe deserialization patterns (SEC-006)."""
    findings = []

    if file_path.suffix not in (".py", ".sh", ".js", ".ts", ".bash"):
        return findings

    for line_num, line in enumerate(content.split("\n"), 1):
        for pattern_name, pattern, description, sev_str in DESERIALIZATION_PATTERNS:
            if pattern.search(line):
                # Special case: yaml.load is OK if SafeLoader is on the same line
                if "yaml.load" in pattern_name:
                    if YAML_SAFE_LOADER_PATTERN.search(line):
                        continue
                    # Also skip if it's actually yaml.safe_load
                    if YAML_SAFE_PATTERN.search(line):
                        continue

                severity = Severity.CRITICAL if sev_str == "CRITICAL" else Severity.WARNING

                findings.append(Finding(
                    code="SEC-006",
                    severity=severity,
                    category=Category.SECURITY,
                    title=f"Unsafe deserialization: {pattern_name}",
                    detail=f"{description}. Line: {line.strip()[:100]}",
                    file_path=str(file_path),
                    line_number=line_num,
                    fix="Use safe alternatives: yaml.safe_load(), json.loads(), or validate input before deserialization.",
                ))

    return findings


def _scan_file_for_dynamic_imports(file_path: Path, content: str) -> list[Finding]:
    """Scan script files for dynamic import/code generation patterns (SEC-007)."""
    findings = []

    if file_path.suffix not in (".py", ".sh", ".js", ".ts", ".bash"):
        return findings

    for line_num, line in enumerate(content.split("\n"), 1):
        for pattern_name, pattern, description in DYNAMIC_IMPORT_PATTERNS:
            if pattern.search(line):
                findings.append(Finding(
                    code="SEC-007",
                    severity=Severity.WARNING,
                    category=Category.SECURITY,
                    title=f"Dynamic import/codegen: {pattern_name}",
                    detail=f"{description}. Line: {line.strip()[:100]}",
                    file_path=str(file_path),
                    line_number=line_num,
                    fix="Avoid dynamic imports; use explicit imports. Dynamic code generation is a code injection risk.",
                ))

    return findings


def _scan_file_for_base64_payloads(file_path: Path, content: str) -> list[Finding]:
    """Scan files for base64 encoded payload patterns (SEC-008)."""
    findings = []

    if file_path.suffix not in (".py", ".sh", ".js", ".ts", ".bash"):
        return findings

    lines = content.split("\n")
    for line_num, line in enumerate(lines, 1):
        # Check for base64 decode function calls
        for pattern_name, pattern, description in BASE64_DECODE_PATTERNS:
            if pattern.search(line):
                # Check if eval/exec is on the same line — CRITICAL
                if EVAL_EXEC_PATTERN.search(line):
                    severity = Severity.CRITICAL
                    detail = f"{description} Combined with eval/exec — likely malicious payload. Line: {line.strip()[:100]}"
                else:
                    severity = Severity.WARNING
                    detail = f"{description}. Line: {line.strip()[:100]}"

                findings.append(Finding(
                    code="SEC-008",
                    severity=severity,
                    category=Category.SECURITY,
                    title=f"Base64 payload: {pattern_name}",
                    detail=detail,
                    file_path=str(file_path),
                    line_number=line_num,
                    fix="Avoid decoding and executing base64 payloads. Use plain-text code for transparency.",
                ))

        # Check for long base64 strings combined with eval/exec
        if LONG_BASE64_STRING.search(line):
            # Look for eval/exec on the same line or within 3 lines
            context_start = max(0, line_num - 2)
            context_end = min(len(lines), line_num + 2)
            context = "\n".join(lines[context_start:context_end])
            if EVAL_EXEC_PATTERN.search(context):
                findings.append(Finding(
                    code="SEC-008",
                    severity=Severity.CRITICAL,
                    category=Category.SECURITY,
                    title="Base64 payload: long encoded string with eval/exec",
                    detail=f"Long base64 string near eval/exec — likely obfuscated malicious payload. Line: {line.strip()[:100]}",
                    file_path=str(file_path),
                    line_number=line_num,
                    fix="Remove obfuscated payloads. All code should be human-readable.",
                ))

    return findings


def _scan_file_for_mcp_references(file_path: Path, content: str) -> list[Finding]:
    """Scan files for MCP server references (SEC-009)."""
    findings = []

    for line_num, line in enumerate(content.split("\n"), 1):
        for pattern_name, pattern, description, sev_str in MCP_CONFIG_PATTERNS:
            if pattern.search(line):
                severity = Severity.CRITICAL if sev_str == "CRITICAL" else Severity.WARNING

                findings.append(Finding(
                    code="SEC-009",
                    severity=severity,
                    category=Category.SECURITY,
                    title=f"MCP server reference: {pattern_name}",
                    detail=f"{description}. Line: {line.strip()[:100]}",
                    file_path=str(file_path),
                    line_number=line_num,
                    fix="Verify MCP server references are trusted. External MCP servers can be an attack vector.",
                ))

    return findings


def _scan_skill_md_for_eval_exec(skill_md: Path, content: str) -> list[Finding]:
    """Scan SKILL.md code blocks for eval()/exec() instructions (SEC-005 enhancement)."""
    findings = []
    in_code_block = False
    code_block_lang = ""

    for line_num, line in enumerate(content.split("\n"), 1):
        stripped = line.strip()

        # Track code block boundaries
        if stripped.startswith("```"):
            if in_code_block:
                in_code_block = False
                code_block_lang = ""
            else:
                in_code_block = True
                code_block_lang = stripped[3:].strip().lower()
            continue

        if in_code_block and EVAL_EXEC_PATTERN.search(line):
            findings.append(Finding(
                code="SEC-005",
                severity=Severity.WARNING,
                category=Category.SECURITY,
                title="Injection surface: eval/exec in SKILL.md code block",
                detail=f"SKILL.md code block contains eval/exec — instructs agent to run dangerous code. Line: {stripped[:100]}",
                file_path=str(skill_md),
                line_number=line_num,
                fix="Remove eval/exec from SKILL.md code examples. Use safe alternatives.",
            ))

    return findings


def _scan_skill_md_for_injection(skill_md: Path, content: str) -> list[Finding]:
    """Scan SKILL.md body for injection surface patterns."""
    findings = []
    
    for line_num, line in enumerate(content.split("\n"), 1):
        for pattern_name, pattern, description, fix in INJECTION_SURFACE_PATTERNS:
            if pattern.search(line):
                findings.append(Finding(
                    code="SEC-005",
                    severity=Severity.WARNING,
                    category=Category.SECURITY,
                    title=f"Injection surface: {pattern_name}",
                    detail=f"{description}. Line: {line.strip()[:100]}",
                    file_path=str(skill_md),
                    line_number=line_num,
                    fix=fix,
                ))
    
    return findings


def scan_security(skill_path: str | Path) -> list[Finding]:
    """Run all security scans on a skill directory.
    
    Args:
        skill_path: Path to the skill directory
        
    Returns:
        List of security findings
    """
    skill_path = Path(skill_path)
    findings: list[Finding] = []
    
    if not skill_path.is_dir():
        return findings
    
    # Directories to skip (build artifacts, environments, caches)
    skip_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__",
                 ".pytest_cache", ".mypy_cache", ".ruff_cache",
                 "egg-info", ".egg-info", "dist", "build", ".tox"}
    
    # Scan all text files in the skill directory
    text_extensions = {".md", ".py", ".sh", ".js", ".ts", ".json", ".yaml", ".yml", 
                       ".toml", ".txt", ".bash", ".zsh", ".env", ".cfg", ".ini", ".conf"}
    
    for file_path in skill_path.rglob("*"):
        if not file_path.is_file():
            continue
        # Skip ignored directories
        if any(skip in file_path.parts for skip in skip_dirs):
            continue
        # Skip files that end with egg-info pattern
        if any(p.endswith(".egg-info") for p in file_path.parts):
            continue
        if file_path.name.startswith(".") and file_path.suffix != ".env":
            continue
        # Skip binary files and very large files
        if file_path.suffix.lower() not in text_extensions and file_path.suffix != "":
            continue
        if file_path.stat().st_size > 1_000_000:  # Skip files > 1MB
            continue
        
        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue
        
        # Run all scanners
        findings.extend(_scan_file_for_secrets(file_path, content))
        findings.extend(_scan_file_for_urls(file_path, content))
        findings.extend(_scan_file_for_subprocess(file_path, content))
        findings.extend(_scan_file_for_installs(file_path, content))
        findings.extend(_scan_file_for_deserialization(file_path, content))
        findings.extend(_scan_file_for_dynamic_imports(file_path, content))
        findings.extend(_scan_file_for_base64_payloads(file_path, content))
        findings.extend(_scan_file_for_mcp_references(file_path, content))
    
    # Scan SKILL.md specifically for injection surfaces and eval/exec in code blocks
    skill_md = skill_path / "SKILL.md"
    if skill_md.is_file():
        try:
            content = skill_md.read_text(encoding="utf-8")
            findings.extend(_scan_skill_md_for_injection(skill_md, content))
            findings.extend(_scan_skill_md_for_eval_exec(skill_md, content))
        except Exception:
            pass
    
    return findings
