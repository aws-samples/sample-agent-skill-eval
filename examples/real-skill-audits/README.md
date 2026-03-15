# Real Skill Audits: Interpreting Reports with Judgment

Not every finding means "do not install." This guide shows audit results for three real ClawHub skills and explains how to read the findings in context.

## 1. Weather Skill — Score 92/100 (Grade A)

```bash
$ skill-eval audit clawhub-skills/weather/

══════════════════════════════════════════════════════════
  Agent Skill Security Audit Report
══════════════════════════════════════════════════════════
  Skill:  weather
  Path:   clawhub-skills/weather
  Score:  92/100 (Grade: A)
──────────────────────────────────────────────────────────
  CRITICAL: 0 │ WARNING: 0 │ INFO: 4
──────────────────────────────────────────────────────────
  Result: PASSED (no critical findings)
══════════════════════════════════════════════════════════

  [SEC-002] External URL: wttr.in
     File: SKILL.md:4
     URL: https://wttr.in/:help

  [SEC-002] External URL: api.open-meteo.com
     File: SKILL.md:44
     URL: https://api.open-meteo.com/v1/forecast?...

  [SEC-002] External URL: open-meteo.com
     File: SKILL.md:49
     URL: https://open-meteo.com/en/docs

  [PERM-005] References absolute system path
     File: SKILL.md:38
     Line: curl -s "wttr.in/Berlin.png" -o /tmp/weather.png
```

**What the findings mean:** All four INFO findings are expected and harmless:

- **SEC-002 (External URLs):** The weather skill *needs* to call `wttr.in` and `open-meteo.com` — that's its entire purpose. These are well-known public weather APIs with no authentication required. The `open-meteo.com/en/docs` link is just documentation.
- **PERM-005 (Absolute path):** The `/tmp/` reference is a common temp directory for saving a weather PNG. This is a documentation example, not a security risk.

**Verdict: Safe to install.** The 4 INFO findings are inherent to what the skill does. No action needed.

---

## 2. Slack Skill — Score 100/100 (Grade A)

```bash
$ skill-eval audit clawhub-skills/slack/

══════════════════════════════════════════════════════════
  Agent Skill Security Audit Report
══════════════════════════════════════════════════════════
  Skill:  slack
  Path:   clawhub-skills/slack
  Score:  100/100 (Grade: A)
──────────────────────────────────────────────────────────
  CRITICAL: 0 │ WARNING: 0 │ INFO: 0
──────────────────────────────────────────────────────────
  Result: PASSED (no critical findings)
══════════════════════════════════════════════════════════
```

**What the findings mean:** Zero findings. The Slack skill is a pure SKILL.md with JSON action examples — no scripts, no external URLs, no elevated permissions. It delegates all Slack API calls to the Clawdbot `slack` tool, which handles authentication separately.

**Verdict: Safe to install.** Clean audit with no caveats.

---

## 3. nano-pdf Skill — Score 100/100 (Grade A)

```bash
$ skill-eval audit clawhub-skills/nano-pdf/

══════════════════════════════════════════════════════════
  Agent Skill Security Audit Report
══════════════════════════════════════════════════════════
  Skill:  nano-pdf
  Path:   clawhub-skills/nano-pdf
  Score:  100/100 (Grade: A)
──────────────────────────────────────────────────────────
  CRITICAL: 0 │ WARNING: 0 │ INFO: 0
──────────────────────────────────────────────────────────
  Result: PASSED (no critical findings)
══════════════════════════════════════════════════════════
```

**What the findings mean:** Another clean audit. The nano-pdf skill is minimal — it wraps the `nano-pdf` CLI binary with a usage example. No hardcoded secrets, no shell patterns, no external URLs beyond the pypi.org homepage (which is on the safe-domain allowlist).

**Verdict: Safe to install.** The skill requires the `nano-pdf` binary to be installed separately, but that's a runtime dependency, not a security concern flagged by the audit.

---

## How to Read Audit Reports

### Decision framework

| Scenario | Action |
|----------|--------|
| Score 90+, 0 criticals | Safe to install. Review INFO findings for context. |
| Score 70-89, 0 criticals | Review WARNING findings. Most are acceptable with justification. |
| Score 60-69 | Carefully review all findings. Some may need fixes. |
| Score <60 or any criticals | Do not install without fixes. See [F to A guide](../f-to-a-improvement/). |

### Common false positives

- **SEC-002 on API skills:** A weather/translation/search skill *must* call external URLs. These are expected.
- **PERM-005 on `/tmp/`:** Writing temp files to `/tmp/` is standard practice, not a security hole.
- **STR-014 (long SKILL.md):** Some skills need detailed instructions. Length alone isn't a problem.

### Real red flags to watch for

- **SEC-001 (any severity):** Hardcoded secrets are never acceptable.
- **SEC-004 (curl|bash):** Always a supply chain risk — no exceptions.
- **SEC-009 with `npx -y`:** Auto-installing and running npm packages is dangerous.
- **PERM-001 (Bash(\*)):** Unrestricted shell access should have a strong justification.
- **SEC-008 + eval/exec:** Base64-encoded payloads executed at runtime are almost always malicious.
