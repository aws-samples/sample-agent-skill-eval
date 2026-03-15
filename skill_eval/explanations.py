"""Educational explanations for audit finding codes."""

from __future__ import annotations

# Maps finding code (or prefix) to an educational explanation.
# Exact codes are checked first, then prefix matching is used.
RULE_EXPLANATIONS: dict[str, str] = {
    "SEC-001": (
        "Hardcoded secrets in skill files can be extracted by anyone who reads the skill. "
        "Attackers can use leaked API keys to access your services, incur charges, or steal data."
    ),
    "SEC-002": (
        "External URLs in skill code are potential data exfiltration channels. A malicious skill "
        "could send your files, environment variables, or conversation history to an attacker-controlled server."
    ),
    "SEC-003": (
        "Shell command execution gives the skill full system access. A skill with "
        "subprocess.run(shell=True) can run ANY command \u2014 install malware, read private files, "
        "or modify system settings."
    ),
    "SEC-004": (
        "Piping curl to bash or installing unpinned packages means the skill pulls code from the "
        "internet at runtime. An attacker who compromises the URL serves malicious code to everyone."
    ),
    "SEC-005": (
        "Instructions that reference user input in executable contexts enable prompt injection. "
        "An attacker can craft input that makes the agent follow the skill\u2019s hidden instructions."
    ),
    "SEC-006": (
        "pickle.load(), yaml.load(), and similar deserializers execute arbitrary code embedded "
        "in the data. A malicious pickle file can run any Python code when loaded."
    ),
    "SEC-007": (
        "Dynamic imports like importlib.import_module() and __import__() can load any module at "
        "runtime, bypassing static analysis. This is a common technique to hide malicious behavior."
    ),
    "SEC-008": (
        "Base64 encoding is used to obfuscate malicious payloads. Legitimate code is readable; "
        "encoded payloads are hiding something."
    ),
    "SEC-009": (
        "MCP servers are external services that an agent connects to. A malicious MCP server can "
        "intercept all agent communications, inject instructions, or exfiltrate data."
    ),
}

# Prefix-based explanations for code families
_PREFIX_EXPLANATIONS: dict[str, str] = {
    "STR": (
        "Proper structure ensures the skill is discoverable, parseable, and follows community "
        "conventions. Missing frontmatter or invalid names make the skill harder to audit and integrate."
    ),
    "PERM": (
        "Excessive permissions give the skill more power than it needs. The principle of least "
        "privilege means a weather skill should NOT need Bash(*) access \u2014 it only needs to run curl."
    ),
}


def get_explanation(code: str) -> str | None:
    """Return the educational explanation for a finding code.

    Checks exact code first, then falls back to prefix matching.
    Returns None if no explanation is available.
    """
    if code in RULE_EXPLANATIONS:
        return RULE_EXPLANATIONS[code]

    prefix = code.split("-")[0] if "-" in code else code
    return _PREFIX_EXPLANATIONS.get(prefix)
