"""Lifecycle management for Agent Skills.

Provides:
- Skill fingerprinting (SHA-256 hashes of all files)
- Change detection against previous baselines
- Version tracking with labeled history
- CLI integration for lifecycle checks and auto-regression
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class VersionEntry:
    """One entry in the lifecycle version history."""
    timestamp: str
    label: str
    fingerprint: str
    file_hashes: dict[str, str] = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to a plain dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "VersionEntry":
        """Deserialize from a plain dict, ignoring extra keys."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def _get_history_path(skill_path: Path) -> Path:
    """Get the lifecycle history.json path for a skill."""
    return skill_path / "evals" / "lifecycle" / "history.json"


def _load_history(history_path: Path) -> dict:
    """Load lifecycle history from disk.

    Returns:
        Dict with ``versions`` key (list of version entries).
    """
    if history_path.is_file():
        try:
            data = json.loads(history_path.read_text())
            if isinstance(data, dict) and "versions" in data:
                return data
        except (json.JSONDecodeError, KeyError):
            pass
    return {"versions": []}


def _save_history(history_path: Path, history: dict) -> None:
    """Persist lifecycle history to disk."""
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(history, indent=2) + "\n")


def _collect_skill_files(skill_path: Path) -> list[Path]:
    """Collect all files under a skill directory, sorted for determinism.

    Skips hidden directories/files and common generated directories
    (``evals/baselines``, ``evals/lifecycle``, ``__pycache__``).
    """
    skip_dirs = {"__pycache__", ".git", "baselines", "lifecycle"}
    files: list[Path] = []
    for item in sorted(skill_path.rglob("*")):
        if item.is_dir():
            continue
        # Skip items inside directories we want to ignore
        parts = item.relative_to(skill_path).parts
        if any(p.startswith(".") or p in skip_dirs for p in parts[:-1]):
            continue
        # Skip hidden files
        if item.name.startswith("."):
            continue
        files.append(item)
    return files


def compute_skill_fingerprint(skill_path: str) -> dict:
    """Compute SHA-256 fingerprint of all files in a skill directory.

    Args:
        skill_path: Path to the skill directory.

    Returns:
        Dict with keys:
        - ``file_hashes``: mapping of relative path → SHA-256 hex digest
        - ``fingerprint``: combined SHA-256 over all individual hashes
    """
    path = Path(skill_path).resolve()
    if not path.is_dir():
        raise FileNotFoundError(f"Skill directory not found: {path}")

    files = _collect_skill_files(path)
    file_hashes: dict[str, str] = {}

    for fp in files:
        h = hashlib.sha256(fp.read_bytes()).hexdigest()
        rel = str(fp.relative_to(path))
        file_hashes[rel] = h

    # Combined fingerprint: hash of sorted (path, hash) pairs
    combined = hashlib.sha256()
    for rel_path in sorted(file_hashes.keys()):
        combined.update(f"{rel_path}:{file_hashes[rel_path]}".encode())

    return {
        "file_hashes": file_hashes,
        "fingerprint": combined.hexdigest(),
    }


def detect_changes(
    skill_path: str,
    baseline_path: Optional[str] = None,
) -> dict:
    """Detect changes between current skill state and a previous baseline.

    Args:
        skill_path: Path to the skill directory.
        baseline_path: Path to a history.json file. If ``None``, uses
            the default ``evals/lifecycle/history.json`` location.

    Returns:
        Dict with keys:
        - ``changed``: bool — whether any change was detected
        - ``added``: list of newly added relative file paths
        - ``modified``: list of modified relative file paths
        - ``deleted``: list of deleted relative file paths
        - ``current_fingerprint``: current combined fingerprint
        - ``baseline_fingerprint``: previous combined fingerprint (or ``None``)
    """
    path = Path(skill_path).resolve()
    current = compute_skill_fingerprint(str(path))

    hp = Path(baseline_path) if baseline_path else _get_history_path(path)
    history = _load_history(hp)

    if not history["versions"]:
        return {
            "changed": True,
            "added": sorted(current["file_hashes"].keys()),
            "modified": [],
            "deleted": [],
            "current_fingerprint": current["fingerprint"],
            "baseline_fingerprint": None,
        }

    latest = history["versions"][-1]
    baseline_hashes: dict[str, str] = latest.get("file_hashes", {})
    baseline_fp = latest.get("fingerprint", "")

    current_hashes = current["file_hashes"]
    all_keys = set(current_hashes.keys()) | set(baseline_hashes.keys())

    added: list[str] = []
    modified: list[str] = []
    deleted: list[str] = []

    for key in sorted(all_keys):
        in_current = key in current_hashes
        in_baseline = key in baseline_hashes
        if in_current and not in_baseline:
            added.append(key)
        elif not in_current and in_baseline:
            deleted.append(key)
        elif current_hashes[key] != baseline_hashes[key]:
            modified.append(key)

    has_changes = bool(added or modified or deleted)

    return {
        "changed": has_changes,
        "added": added,
        "modified": modified,
        "deleted": deleted,
        "current_fingerprint": current["fingerprint"],
        "baseline_fingerprint": baseline_fp,
    }


def check_lifecycle(
    skill_path: str,
    history_path: Optional[str] = None,
    format: str = "text",
) -> int:
    """Check skill lifecycle status against version history.

    Computes the current fingerprint and compares against the last recorded
    version in the history file.

    Args:
        skill_path: Path to the skill directory.
        history_path: Custom path to history.json. Defaults to
            ``<skill>/evals/lifecycle/history.json``.
        format: Output format — ``"text"`` or ``"json"``.

    Returns:
        Exit code:
        - 0 if no changes detected (or initial version recorded)
        - 1 if changes detected (regression suggested)
    """
    path = Path(skill_path).resolve()
    hp = Path(history_path) if history_path else _get_history_path(path)
    history = _load_history(hp)
    current = compute_skill_fingerprint(str(path))

    if not history["versions"]:
        # First run — record initial version
        entry = VersionEntry(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            label="initial",
            fingerprint=current["fingerprint"],
            file_hashes=current["file_hashes"],
            metadata={"skill_path": str(path)},
        )
        history["versions"].append(entry.to_dict())
        _save_history(hp, history)

        if format == "json":
            print(json.dumps({"status": "initial", "fingerprint": current["fingerprint"]}))
        else:
            print("Initial version recorded.")
        return 0

    latest = history["versions"][-1]
    baseline_fp = latest.get("fingerprint", "")

    if current["fingerprint"] == baseline_fp:
        if format == "json":
            print(json.dumps({"status": "unchanged", "fingerprint": current["fingerprint"]}))
        else:
            print("No changes detected.")
        return 0

    # Changes detected — compute diff summary
    changes = detect_changes(str(path), str(hp))

    if format == "json":
        print(json.dumps({
            "status": "changed",
            "added": changes["added"],
            "modified": changes["modified"],
            "deleted": changes["deleted"],
            "current_fingerprint": changes["current_fingerprint"],
            "baseline_fingerprint": changes["baseline_fingerprint"],
        }))
    else:
        print("Changes detected since last recorded version:")
        if changes["added"]:
            print(f"  Added ({len(changes['added'])}):")
            for f in changes["added"]:
                print(f"    + {f}")
        if changes["modified"]:
            print(f"  Modified ({len(changes['modified'])}):")
            for f in changes["modified"]:
                print(f"    ~ {f}")
        if changes["deleted"]:
            print(f"  Deleted ({len(changes['deleted'])}):")
            for f in changes["deleted"]:
                print(f"    - {f}")
        print("\nConsider running regression tests: skill-eval regression <skill_path>")

    return 1


def save_version(skill_path: str, label: Optional[str] = None) -> None:
    """Save the current skill fingerprint as a new version entry.

    Args:
        skill_path: Path to the skill directory.
        label: Optional human-readable version label (e.g. ``"v1.2"``).
            Auto-generated from timestamp if not provided.
    """
    path = Path(skill_path).resolve()
    hp = _get_history_path(path)
    history = _load_history(hp)
    current = compute_skill_fingerprint(str(path))

    if not label:
        label = time.strftime("v%Y%m%d-%H%M%S")

    entry = VersionEntry(
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        label=label,
        fingerprint=current["fingerprint"],
        file_hashes=current["file_hashes"],
        metadata={"skill_path": str(path), "file_count": len(current["file_hashes"])},
    )
    history["versions"].append(entry.to_dict())
    _save_history(hp, history)

    print(f"Version saved: {label} ({current['fingerprint'][:12]}...)")


def list_versions(skill_path: str) -> None:
    """Print the version history for a skill.

    Args:
        skill_path: Path to the skill directory.
    """
    path = Path(skill_path).resolve()
    hp = _get_history_path(path)
    history = _load_history(hp)

    if not history["versions"]:
        print("No version history found.")
        return

    print(f"Version history ({len(history['versions'])} entries):")
    print(f"{'─' * 58}")
    for i, v in enumerate(history["versions"]):
        fp_short = v.get("fingerprint", "?")[:12]
        ts = v.get("timestamp", "?")
        lbl = v.get("label", "?")
        n_files = len(v.get("file_hashes", {}))
        print(f"  {i + 1}. [{lbl}]  {ts}  {fp_short}...  ({n_files} files)")
