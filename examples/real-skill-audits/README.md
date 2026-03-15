# Real-World Skill Audits

Audit results from running `skill-eval audit` against publicly available Agent Skills.
These demonstrate that the framework works on real, production-quality skills — not
just our own test fixtures.

## Anthropic Official Skills

Source: [github.com/anthropics/skills](https://github.com/anthropics/skills)

Audited on 2026-03-15. All 17 skills scanned with default settings (scoped to
SKILL.md + scripts/ + agents/).

| Skill | Score | Grade | Critical | Warning | Info | Notes |
|-------|-------|-------|----------|---------|------|-------|
| algorithmic-art | 98 | A | 0 | 0 | 1 | Clean — 1 info only |
| brand-guidelines | 100 | A | 0 | 0 | 0 | Perfect score |
| canvas-design | 100 | A | 0 | 0 | 0 | Perfect score |
| claude-api | 100 | A | 0 | 0 | 0 | Perfect score |
| doc-coauthoring | 98 | A | 0 | 0 | 1 | Clean — 1 info only |
| frontend-design | 100 | A | 0 | 0 | 0 | Perfect score |
| internal-comms | 100 | A | 0 | 0 | 0 | Perfect score |
| slack-gif-creator | 100 | A | 0 | 0 | 0 | Perfect score |
| theme-factory | 100 | A | 0 | 0 | 0 | Perfect score |
| skill-creator | 60 | D | 0 | 4 | 0 | Warnings from example code in SKILL.md |
| webapp-testing | 76 | C | 0 | 2 | 2 | SEC-002 + SEC-004 from Playwright setup |
| mcp-builder | 72 | C | 0 | 2 | 3 | npm install patterns |
| pdf | 84 | B | 0 | 1 | 2 | Minor SEC-002 |
| web-artifacts-builder | 38 | F | 0 | 6 | 1 | 5× SEC-004 (npm install), 1× SEC-002 |
| docx | 0 | F | 0 | 34 | 23 | 34× SEC-002 (XML namespace URLs) |
| pptx | 0 | F | 0 | 34 | 23 | Same as docx — XML namespaces |
| xlsx | 0 | F | 0 | 34 | 23 | Same as docx — XML namespaces |

### Distribution

```
A: 9 skills (53%)  — Clean, well-structured
B: 1 skill  (6%)   — Minor issues
C: 2 skills (12%)  — Moderate issues
D: 1 skill  (6%)   — Significant issues
F: 4 skills (24%)  — Critical or many issues
```

### Key Insights

**1. Most Anthropic skills score A — as expected.**
9 out of 17 (53%) scored 100/A or 98/A. These are knowledge-only skills with no
scripts, no external URLs, and clean SKILL.md files. They demonstrate what "good"
looks like.

**2. Document generation skills (docx/pptx/xlsx) score 0/F — but aren't actually dangerous.**
These skills contain XML template code with dozens of `schemas.openxmlformats.org`
and `schemas.microsoft.com` URLs. These are harmless XML namespace declarations, not
data exfiltration. But the SEC-002 rule flags all external URLs.

**This is the perfect use case for `.skilleval.yaml`:**

```yaml
# .skilleval.yaml for document generation skills
audit:
  safe_domains:
    - schemas.openxmlformats.org
    - schemas.microsoft.com
    - www.w3.org
    - openoffice.org
```

With this config, docx/pptx/xlsx would score significantly higher.

**3. skill-creator scores 60/D because it contains example code.**
The skill-creator's SKILL.md contains examples of both good and bad skill code
(as teaching material). The audit correctly flags the example `subprocess.run()`
and `eval()` patterns — but these are in documentation, not executable code.

**4. web-artifacts-builder scores 38/F due to 5 `npm install` warnings.**
The skill instructs the agent to run `npm install` to set up React/Next.js projects.
SEC-004 correctly flags these as supply chain risks. Whether this is acceptable
depends on the skill's purpose — for a web builder, npm install is expected behavior.

### Takeaway

The audit catches real issues (SEC-004 supply chain risks in web-artifacts-builder)
while also revealing false positives on benign patterns (XML namespaces in docx).
The `.skilleval.yaml` configuration feature exists precisely for this — teams can
whitelist known-safe domains and adjust severity for their use case.

## How to Reproduce

```bash
# Clone Anthropic's skills repo
git clone --depth 1 https://github.com/anthropics/skills.git /tmp/anthropic-skills

# Audit all skills
for skill in /tmp/anthropic-skills/skills/*/; do
    skill-eval audit "$skill" --quiet
done

# Detailed audit for a specific skill
skill-eval audit /tmp/anthropic-skills/skills/web-artifacts-builder/ --verbose
```
