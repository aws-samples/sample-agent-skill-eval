# Security Checklist — OWASP LLM Top 10 Mapping for Agent Skills

This document maps the [OWASP Top 10 for LLM Applications](https://owasp.org/www-project-top-10-for-large-language-model-applications/) to Agent Skill-specific risks and how `skill-eval` detects them.

## LLM01: Prompt Injection

**Risk in Agent Skills**: A skill's SKILL.md instructions could be overridden by malicious user input. If the skill instructs the agent to "process whatever the user provides" without validation, an attacker can inject instructions.

**What skill-eval checks**:
- SEC-005: Patterns in SKILL.md that accept unbounded user input
- SEC-005: Instructions to execute user-provided code/commands
- SEC-005: Instructions to write to arbitrary user-specified paths

**What skill-eval doesn't check** (limitations):
- Whether the LLM actually follows injection attempts (requires dynamic testing)
- Obfuscated injection patterns
- Multi-turn injection chains

## LLM02: Insecure Output Handling

**Risk in Agent Skills**: A skill may instruct the agent to pass LLM output directly to dangerous functions (eval, exec, shell commands) without validation.

**What skill-eval checks**:
- SEC-003: `eval()`, `exec()`, `os.system()`, `subprocess.run()` with `shell=True` in scripts
- SEC-003: Direct subprocess execution patterns

## LLM03: Training Data Poisoning

**Risk in Agent Skills**: A skill from an untrusted marketplace may contain instructions designed to subtly alter agent behavior over time.

**What skill-eval checks**:
- Structure compliance validates the skill follows the standard format
- Permission analysis flags over-privileged tool requests

**Not directly detectable** by static analysis — requires behavioral testing.

## LLM04: Model Denial of Service

**Risk in Agent Skills**: A skill could instruct the agent to perform extremely expensive operations (huge file processing, infinite loops).

**What skill-eval checks**:
- STR-014/STR-015: Oversized SKILL.md files that consume excessive context

**Partially covered** — explicit DoS patterns in scripts are not scanned.

## LLM05: Supply Chain Vulnerabilities

**Risk in Agent Skills**: Skills may install unvetted dependencies, download executables, or reference compromised external resources.

**What skill-eval checks**:
- SEC-004: `curl | bash`, `wget | sh` patterns (CRITICAL severity)
- SEC-004: Unpinned `pip install`, `npm install`
- SEC-002: External URL inventory in scripts and instructions
- SEC-002: Categorizes URLs by risk (scripts = WARNING, docs = INFO)

**Recommended**: Pin all dependencies in requirements files. Audit external URLs.

## LLM06: Sensitive Information Disclosure

**Risk in Agent Skills**: Skills may contain or inadvertently expose API keys, tokens, passwords, or private keys.

**What skill-eval checks**:
- SEC-001: AWS access keys (AKIA pattern)
- SEC-001: GitHub tokens (ghp_, github_pat_)
- SEC-001: OpenAI/Anthropic API keys
- SEC-001: Slack tokens and webhooks
- SEC-001: Generic password/token/secret assignments
- SEC-001: Database connection strings with credentials
- SEC-001: Private key headers (RSA, EC, DSA, OPENSSH)
- SEC-001: High-entropy encoded strings in secret-like variables

**Allowlist**: Placeholders (your-api-key-here, CHANGEME, xxx), environment variable references, and process.env patterns are excluded.

## LLM07: Insecure Plugin Design

**Risk in Agent Skills**: Over-privileged skills that request more tool access than needed, or skills that don't validate inputs.

**What skill-eval checks**:
- PERM-001: Unrestricted Bash/Shell access (`Bash(*)`)
- PERM-002: High-risk tool declarations
- PERM-003: Excessive number of declared tools (>15)
- PERM-004: Instructions referencing sensitive directories (~/.ssh, ~/.aws)
- PERM-004: Instructions requiring sudo/root access
- PERM-005: Absolute system path references outside workspace

**Recommendation**: Use scoped Bash (e.g., `Bash(python3:*) Bash(git:*)`) instead of `Bash(*)`.

## LLM08: Excessive Agency

**Risk in Agent Skills**: Skills that instruct the agent to take autonomous actions without human confirmation (sending emails, making purchases, modifying system files).

**What skill-eval checks**:
- PERM-004: Detection of credential access patterns
- PERM-004: Network listener instructions
- PERM-005: System path modifications

**Partially covered** — detecting "excessive agency" in natural language instructions requires semantic understanding beyond regex matching.

## LLM09: Overreliance

**Risk in Agent Skills**: Skills that generate outputs without verification steps, leading users to trust unvalidated results.

**Not directly checked** by skill-eval. This is a behavioral quality issue best caught by Anthropic skill-creator's eval framework.

## LLM10: Model Theft

**Risk in Agent Skills**: Not directly applicable to Agent Skills. Model theft targets the model weights/parameters, not the skill layer.

---

## Additional Skill-Specific Risks (Not in OWASP Top 10)

### Data Exfiltration via Skills
A malicious skill could instruct the agent to read sensitive local files and send them to an external endpoint.

**What skill-eval checks**:
- SEC-002: Complete inventory of external URLs in all skill files
- SEC-003: Subprocess patterns that could pipe data externally
- PERM-004: References to sensitive directories

### Skill Supply Chain (Marketplace Risk)
Installing skills from marketplaces is functionally equivalent to running untrusted code.

**Mitigation**: Run `skill-eval audit` before installing any third-party skill. Look for:
- Grade B or above
- Zero CRITICAL findings
- All external URLs documented and justified
- Scoped tool permissions (no `Bash(*)`)

---

## References

- [OWASP Top 10 for LLM Applications v2025](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
- [Agent Skills Specification](https://agentskills.io/specification)
- [garak — LLM Vulnerability Scanner](https://github.com/leondz/garak)
- [Anthropic: Equipping Agents for the Real World](https://anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
