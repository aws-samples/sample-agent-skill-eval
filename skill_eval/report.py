"""Report generation for skill evaluation."""

from __future__ import annotations

import json
import sys
from typing import TextIO

from skill_eval.explanations import get_explanation
from skill_eval.schemas import AuditReport, Finding, Severity


def format_text_report(report: AuditReport, verbose: bool = False, explain: bool = False, file: TextIO | None = None) -> None:
    """Print a human-readable text report."""
    if file is None:
        file = sys.stdout

    w = 58  # Report width
    
    print(f"\n{'═' * w}", file=file)
    print(f"  Agent Skill Security Audit Report", file=file)
    print(f"{'═' * w}", file=file)
    print(f"  Skill:  {report.skill_name}", file=file)
    print(f"  Path:   {report.skill_path}", file=file)
    print(f"  Score:  {report.score}/100 (Grade: {report.grade})", file=file)
    print(f"{'─' * w}", file=file)
    
    # Summary counts
    c = report.critical_count
    w_count = report.warning_count
    i = report.info_count
    
    parts = []
    if c > 0:
        parts.append(f"🔴 CRITICAL: {c}")
    else:
        parts.append(f"✅ CRITICAL: {c}")
    parts.append(f"⚠️  WARNING: {w_count}")
    parts.append(f"ℹ️  INFO: {i}")
    
    print(f"  {' │ '.join(parts)}", file=file)
    print(f"{'─' * w}", file=file)
    
    if report.passed:
        print(f"  Result: ✅ PASSED (no critical findings)", file=file)
    else:
        print(f"  Result: ❌ FAILED ({c} critical finding{'s' if c != 1 else ''})", file=file)
    print(f"{'═' * w}\n", file=file)
    
    # Group findings by severity
    grouped: dict[str, list[Finding]] = {}
    for f in report.findings:
        grouped.setdefault(f.severity.value, []).append(f)
    
    # Print findings in severity order
    for severity in [Severity.CRITICAL, Severity.WARNING, Severity.INFO]:
        items = grouped.get(severity.value, [])
        if not items:
            continue
        
        if severity == Severity.INFO and not verbose:
            print(f"  ℹ️  {len(items)} INFO finding{'s' if len(items) != 1 else ''} (use --verbose to see)", file=file)
            continue
        
        for finding in items:
            icon = {"CRITICAL": "🔴", "WARNING": "⚠️ ", "INFO": "ℹ️ "}.get(severity.value, "  ")
            print(f"  {icon} [{finding.code}] {finding.title}", file=file)
            
            if finding.file_path:
                loc = finding.file_path
                if finding.line_number:
                    loc += f":{finding.line_number}"
                print(f"     File: {loc}", file=file)
            
            print(f"     {finding.detail[:200]}", file=file)
            
            if finding.fix:
                print(f"     Fix: {finding.fix}", file=file)

            if explain:
                explanation = get_explanation(finding.code)
                if explanation:
                    print(f"     Why it matters: {explanation}", file=file)

            print(file=file)
    
    # Metadata
    if verbose and report.metadata:
        print(f"{'─' * w}", file=file)
        print(f"  Metadata:", file=file)
        for k, v in report.metadata.items():
            print(f"    {k}: {v}", file=file)
        print(file=file)


def format_json_report(report: AuditReport, file: TextIO | None = None) -> None:
    """Print a JSON report."""
    if file is None:
        file = sys.stdout
    print(json.dumps(report.to_dict(), indent=2), file=file)
