# Golden Dataset

A curated set of skills with known audit scores, used to verify that `skill-eval` produces correct and consistent results.

## Bad Skills (examples of common mistakes)

| Skill | Score | Grade | Key Issues | What It Teaches |
|-------|:-----:|:-----:|------------|-----------------|
| [sloppy-weather](bad-skills/sloppy-weather/) | 53 | F | Hardcoded API key, short description | Secrets in code, lazy documentation |
| [over-permissioned](bad-skills/over-permissioned/) | 58 | F | Bash(*), ~/.ssh/ access, sudo | Excessive permissions, sensitive dir access |
| [insecure-installer](bad-skills/insecure-installer/) | 0 | F | curl\|bash, pickle.load, npx -y | Supply chain attacks, unsafe deserialization |
| [poor-structure](bad-skills/poor-structure/) | 63 | D | No frontmatter, eval() in script | Missing metadata, dangerous code patterns |

## Good Skills (baselines)

| Skill | Score | Grade | Source |
|-------|:-----:|:-----:|--------|
| weather | 92 | A | ClawHub |
| nano-pdf | 100 | A | ClawHub |
| slack | 100 | A | ClawHub |
| skill-eval (self) | 96 | A | This repo |

## Usage

Run the golden dataset tests:

```bash
pytest tests/test_golden_dataset.py -v
```

Or audit individual skills:

```bash
skill-eval audit examples/golden-dataset/bad-skills/sloppy-weather -v
skill-eval audit examples/golden-dataset/bad-skills/insecure-installer -v
```

## Design Principles

1. **Realistic, not malicious** — bad skills represent common mistakes, not intentional attacks
2. **Educational** — each bad skill teaches a specific lesson about skill security
3. **Deterministic** — scores are verified and tracked; code changes shouldn't make scores drift
4. **Diverse** — covers secrets, permissions, supply chain, structure, and deserialization
