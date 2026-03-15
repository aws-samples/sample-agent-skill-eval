"""Scaffold generation for skill evaluations.

Generates template evals.json and eval_queries.json files from a skill's
SKILL.md frontmatter.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _parse_frontmatter(skill_path: str) -> dict[str, str]:
    """Read SKILL.md and extract name/description from YAML frontmatter.

    Returns dict with 'name' and 'description' keys (may be empty strings).
    Raises FileNotFoundError if SKILL.md does not exist.
    """
    skill_md = Path(skill_path) / "SKILL.md"
    if not skill_md.is_file():
        raise FileNotFoundError(f"SKILL.md not found in {skill_path}")

    content = skill_md.read_text()
    result: dict[str, str] = {"name": "", "description": ""}

    if not content.startswith("---"):
        return result

    try:
        end = content.index("---", 3)
        fm_text = content[3:end]
    except ValueError:
        return result

    for line in fm_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("name:"):
            result["name"] = stripped.split(":", 1)[1].strip().strip("\"'")
        elif stripped.startswith("description:"):
            result["description"] = stripped.split(":", 1)[1].strip().strip("\"'")

    return result


def generate_eval_scaffold(skill_path: str) -> int:
    """Generate evaluation scaffold files for a skill.

    Creates evals/evals.json and evals/eval_queries.json with template
    content based on the skill's SKILL.md frontmatter.

    Args:
        skill_path: Path to the skill directory.

    Returns:
        0 on success, 1 on error.
    """
    try:
        fm = _parse_frontmatter(skill_path)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    skill_name = fm["name"] or Path(skill_path).name
    description = fm["description"] or f"A skill named {skill_name}"

    evals_dir = Path(skill_path) / "evals"
    evals_dir.mkdir(parents=True, exist_ok=True)

    evals_file = evals_dir / "evals.json"
    queries_file = evals_dir / "eval_queries.json"

    created = []
    skipped = []

    # Generate evals.json
    if evals_file.exists():
        print(f"Warning: {evals_file} already exists, skipping", file=sys.stderr)
        skipped.append(str(evals_file))
    else:
        evals_data = [
            {
                "id": f"{skill_name}-eval-1",
                "prompt": f"Use the {skill_name} skill to {description}",
                "expected_output": "",
                "files": [],
                "assertions": [
                    f"output is relevant to: {description}",
                    "has at least 1 lines",
                ],
            },
            {
                "id": f"{skill_name}-eval-2",
                "prompt": f"Test the {skill_name} skill with a simple input",
                "expected_output": "",
                "files": [],
                "assertions": [
                    "does not contain 'error'",
                    f"output addresses the purpose of {skill_name}",
                ],
            },
        ]
        evals_file.write_text(json.dumps(evals_data, indent=2) + "\n")
        created.append(str(evals_file))

    # Generate eval_queries.json
    if queries_file.exists():
        print(f"Warning: {queries_file} already exists, skipping", file=sys.stderr)
        skipped.append(str(queries_file))
    else:
        queries_data = [
            {"query": f"Help me {description}", "should_trigger": True},
            {"query": f"I need to use {skill_name}", "should_trigger": True},
            {"query": "What is the weather today?", "should_trigger": False},
            {"query": "Write a haiku about cats", "should_trigger": False},
        ]
        queries_file.write_text(json.dumps(queries_data, indent=2) + "\n")
        created.append(str(queries_file))

    if created:
        print(f"Created: {', '.join(created)}")
    return 0
