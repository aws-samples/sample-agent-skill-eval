"""CLI entry point for agent skill evaluation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from skill_eval.schemas import AuditReport, Finding, calculate_score, calculate_grade
from skill_eval.audit.structure_check import check_structure
from skill_eval.audit.security_scan import scan_security, SAFE_DOMAINS
from skill_eval.audit.permission_analyzer import analyze_permissions
from skill_eval.report import format_text_report, format_json_report


def run_audit(
    skill_path: str,
    verbose: bool = False,
    ignore_codes: set[str] | None = None,
    extra_safe_domains: set[str] | None = None,
) -> AuditReport:
    """Run a full security audit on a skill directory.

    Args:
        skill_path: Path to the skill directory
        verbose: Include INFO-level findings in output
        ignore_codes: Set of finding codes to suppress (e.g., {"STR-017", "SEC-002"})
        extra_safe_domains: Additional domains to treat as safe

    Returns:
        AuditReport with all findings
    """
    path = Path(skill_path).resolve()

    # Temporarily extend safe domains if provided
    added_domains: set[str] = set()
    if extra_safe_domains:
        for d in extra_safe_domains:
            if d not in SAFE_DOMAINS:
                SAFE_DOMAINS.add(d)
                added_domains.add(d)

    try:
        all_findings: list[Finding] = []
        frontmatter = None

        # 1. Structure check
        structure_findings, frontmatter, body_start = check_structure(path)
        all_findings.extend(structure_findings)

        # 2. Security scan
        security_findings = scan_security(path)
        all_findings.extend(security_findings)

        # 3. Permission analysis
        permission_findings = analyze_permissions(path, frontmatter=frontmatter)
        all_findings.extend(permission_findings)

        # Filter out ignored codes
        if ignore_codes:
            all_findings = [f for f in all_findings if f.code not in ignore_codes]

        # Calculate score and grade
        score = calculate_score(all_findings)
        grade = calculate_grade(score)

        skill_name = frontmatter.get("name", path.name) if frontmatter else path.name

        report = AuditReport(
            skill_name=skill_name,
            skill_path=str(path),
            score=score,
            grade=grade,
            findings=all_findings,
            metadata={
                "structure_findings": sum(1 for f in all_findings if f.code.startswith("STR")),
                "security_findings": sum(1 for f in all_findings if f.code.startswith("SEC")),
                "permission_findings": sum(1 for f in all_findings if f.code.startswith("PERM")),
            },
        )
        return report
    finally:
        # Restore safe domains
        for d in added_domains:
            SAFE_DOMAINS.discard(d)


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="skill-eval",
        description="Agent Skill Security & Quality Evaluation",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # audit command
    audit_parser = subparsers.add_parser("audit", help="Run security audit on a skill")
    audit_parser.add_argument("skill_path", nargs="+",
                              help="Path(s) to skill directory(ies)")
    audit_parser.add_argument("--format", choices=["text", "json"], default="text",
                              help="Output format (default: text)")
    audit_parser.add_argument("--verbose", "-v", action="store_true",
                              help="Show INFO-level findings")
    audit_parser.add_argument("--fail-on-warning", action="store_true",
                              help="Exit with code 1 if any warnings found (for CI)")
    audit_parser.add_argument("--ignore", type=str, default="",
                              help="Comma-separated finding codes to suppress (e.g., STR-017,SEC-002)")
    audit_parser.add_argument("--allowlist", type=str, default="",
                              help="Comma-separated domains to treat as safe (e.g., api.yahoo.com,wttr.in)")
    audit_parser.add_argument("--quiet", "-q", action="store_true",
                              help="One-line summary only")
    audit_parser.add_argument("--explain", action="store_true",
                              help="Show educational context for each finding")

    # init command
    init_parser = subparsers.add_parser("init",
                                         help="Generate evaluation scaffold for a skill")
    init_parser.add_argument("skill_path", help="Path to the skill directory")

    # snapshot command (Phase 2)
    snapshot_parser = subparsers.add_parser("snapshot",
                                            help="Save current audit results as a baseline")
    snapshot_parser.add_argument("skill_path", help="Path to the skill directory")
    snapshot_parser.add_argument("--version", type=str, default=None,
                                 help="Version label (default: auto from metadata)")

    # regression command (Phase 2)
    regression_parser = subparsers.add_parser("regression",
                                               help="Check for regressions against baseline")
    regression_parser.add_argument("skill_path", help="Path to the skill directory")
    regression_parser.add_argument("--baseline", type=str, default=None,
                                    help="Path to baseline results (default: evals/baselines/latest/)")
    regression_parser.add_argument("--format", choices=["text", "json"], default="text")

    # functional command (Phase 3)
    functional_parser = subparsers.add_parser("functional",
                                               help="Run functional quality evaluation")
    functional_parser.add_argument("skill_path", help="Path to the skill directory")
    functional_parser.add_argument("--evals", type=str, default=None,
                                    help="Path to evals.json (default: <skill>/evals/evals.json)")
    functional_parser.add_argument("--runs", type=int, default=1,
                                    help="Number of runs per eval case (default: 1)")
    functional_parser.add_argument("--format", choices=["text", "json"], default="text")
    functional_parser.add_argument("--output", type=str, default=None,
                                    help="Path to write benchmark.json")
    functional_parser.add_argument("--dry-run", action="store_true",
                                    help="Load and validate evals without executing")
    functional_parser.add_argument("--timeout", type=int, default=120,
                                    help="Timeout per claude invocation in seconds (default: 120)")
    functional_parser.add_argument("--agent", type=str, default="claude",
                                    help="Agent runner to use (default: claude)")

    # trigger command (Phase 3)
    trigger_parser = subparsers.add_parser("trigger",
                                            help="Run trigger reliability evaluation")
    trigger_parser.add_argument("skill_path", help="Path to the skill directory")
    trigger_parser.add_argument("--queries", type=str, default=None,
                                 help="Path to eval_queries.json (default: <skill>/evals/eval_queries.json)")
    trigger_parser.add_argument("--runs", type=int, default=3,
                                 help="Number of runs per query (default: 3)")
    trigger_parser.add_argument("--format", choices=["text", "json"], default="text")
    trigger_parser.add_argument("--output", type=str, default=None,
                                 help="Path to write trigger report")
    trigger_parser.add_argument("--timeout", type=int, default=60,
                                 help="Timeout per claude invocation in seconds (default: 60)")
    trigger_parser.add_argument("--dry-run", action="store_true",
                                 help="Load and validate queries without executing")
    trigger_parser.add_argument("--agent", type=str, default="claude",
                                 help="Agent runner to use (default: claude)")

    # report command (unified report)
    report_parser = subparsers.add_parser("report",
                                           help="Run unified evaluation report (audit + functional + trigger)")
    report_parser.add_argument("skill_path", help="Path to the skill directory")
    report_parser.add_argument("--format", choices=["text", "json"], default="text",
                                help="Output format (default: text)")
    report_parser.add_argument("--output", type=str, default=None,
                                help="Path to write report file (default: <skill>/evals/report.json)")
    report_parser.add_argument("--skip-audit", action="store_true",
                                help="Skip audit phase")
    report_parser.add_argument("--skip-functional", action="store_true",
                                help="Skip functional evaluation phase")
    report_parser.add_argument("--skip-trigger", action="store_true",
                                help="Skip trigger evaluation phase")
    report_parser.add_argument("--dry-run", action="store_true",
                                help="Validate inputs without executing agent calls")
    report_parser.add_argument("--timeout", type=int, default=120,
                                help="Timeout per agent invocation in seconds (default: 120)")
    report_parser.add_argument("--agent", type=str, default="claude",
                                help="Agent runner to use (default: claude)")

    # compare command
    compare_parser = subparsers.add_parser("compare",
                                            help="Side-by-side skill comparison")
    compare_parser.add_argument("skill_a", help="Path to skill A directory")
    compare_parser.add_argument("skill_b", help="Path to skill B directory")
    compare_parser.add_argument("--evals", type=str, default=None,
                                 help="Path to evals.json (default: skill_a's evals/evals.json)")
    compare_parser.add_argument("--runs", type=int, default=1,
                                 help="Number of runs per eval case (default: 1)")
    compare_parser.add_argument("--format", choices=["text", "json"], default="text")
    compare_parser.add_argument("--output", type=str, default=None,
                                 help="Path to write comparison report")
    compare_parser.add_argument("--dry-run", action="store_true",
                                 help="Load and validate evals without executing")
    compare_parser.add_argument("--timeout", type=int, default=120,
                                 help="Timeout per claude invocation in seconds (default: 120)")
    compare_parser.add_argument("--agent", type=str, default="claude",
                                 help="Agent runner to use (default: claude)")

    # lifecycle command
    lifecycle_parser = subparsers.add_parser("lifecycle",
                                              help="Check skill version and detect changes")
    lifecycle_parser.add_argument("skill_path", help="Path to the skill directory")
    lifecycle_parser.add_argument("--save", action="store_true",
                                  help="Save current version fingerprint")
    lifecycle_parser.add_argument("--label", type=str, default=None,
                                  help="Version label when saving (e.g., v1.2)")
    lifecycle_parser.add_argument("--history", action="store_true",
                                  help="Show version history")
    lifecycle_parser.add_argument("--auto-regression", action="store_true",
                                  help="Automatically run regression if changes detected")
    lifecycle_parser.add_argument("--format", choices=["text", "json"], default="text",
                                  help="Output format (default: text)")

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "audit":
        ignore_codes = set(c.strip() for c in args.ignore.split(",") if c.strip()) if args.ignore else None
        extra_domains = set(d.strip() for d in args.allowlist.split(",") if d.strip()) if args.allowlist else None

        worst_exit = 0
        reports = []

        for skill_path in args.skill_path:
            report = run_audit(skill_path, verbose=args.verbose,
                               ignore_codes=ignore_codes, extra_safe_domains=extra_domains)
            reports.append(report)

            if args.quiet:
                status = "PASSED" if report.passed else "FAILED"
                print(f"{status} {report.score}/{report.grade} {report.skill_name} ({report.skill_path})")
            elif args.format == "json":
                format_json_report(report)
            else:
                format_text_report(report, verbose=args.verbose, explain=args.explain)

            if report.critical_count > 0:
                worst_exit = max(worst_exit, 2)
            elif args.fail_on_warning and report.warning_count > 0:
                worst_exit = max(worst_exit, 1)

        return worst_exit

    elif args.command == "init":
        from skill_eval.init import generate_eval_scaffold
        return generate_eval_scaffold(args.skill_path)

    elif args.command == "snapshot":
        from skill_eval.regression import save_snapshot
        return save_snapshot(args.skill_path, version=args.version)

    elif args.command == "regression":
        from skill_eval.regression import check_regression
        return check_regression(args.skill_path, baseline_path=args.baseline,
                                format=args.format)

    elif args.command == "functional":
        from skill_eval.functional import run_functional_eval
        return run_functional_eval(
            args.skill_path,
            evals_path=args.evals,
            runs_per_eval=args.runs,
            format=args.format,
            output_path=args.output,
            dry_run=args.dry_run,
            timeout=args.timeout,
            agent=args.agent,
        )

    elif args.command == "trigger":
        from skill_eval.trigger import run_trigger_eval
        return run_trigger_eval(
            args.skill_path,
            queries_path=args.queries,
            runs_per_query=args.runs,
            format=args.format,
            output_path=args.output,
            timeout=args.timeout,
            dry_run=args.dry_run,
            agent=args.agent,
        )

    elif args.command == "report":
        from skill_eval.unified_report import run_unified_report
        return run_unified_report(
            args.skill_path,
            format=args.format,
            output_path=args.output,
            include_audit=not args.skip_audit,
            include_functional=not args.skip_functional,
            include_trigger=not args.skip_trigger,
            dry_run=args.dry_run,
            timeout=args.timeout,
            agent=args.agent,
        )

    elif args.command == "compare":
        from skill_eval.compare import run_compare
        return run_compare(
            args.skill_a,
            args.skill_b,
            evals_path=args.evals,
            runs_per_eval=args.runs,
            format=args.format,
            output_path=args.output,
            dry_run=args.dry_run,
            timeout=args.timeout,
            agent=args.agent,
        )

    elif args.command == "lifecycle":
        from skill_eval.lifecycle import check_lifecycle, save_version, list_versions
        if args.history:
            list_versions(args.skill_path)
            return 0
        elif args.save:
            save_version(args.skill_path, label=args.label)
            return 0
        else:
            rc = check_lifecycle(args.skill_path, format=args.format)
            if rc == 1 and args.auto_regression:
                print("\nAuto-regression: running regression check...")
                from skill_eval.regression import check_regression
                return check_regression(args.skill_path, format=args.format)
            return rc

    return 0


if __name__ == "__main__":
    sys.exit(main())
