"""HTML report generator for skill-eval.

Renders unified evaluation results as a standalone HTML file.
No external dependencies (Jinja2, etc.) — uses Python string formatting.
"""

from __future__ import annotations

import html
import json
from datetime import datetime
from typing import Optional


def _esc(text: str) -> str:
    """HTML-escape a string."""
    return html.escape(str(text))


def _grade_color(grade: str) -> str:
    """Return CSS color for a letter grade."""
    return {
        "A": "#22c55e",  # green
        "B": "#3b82f6",  # blue
        "C": "#eab308",  # yellow
        "D": "#f97316",  # orange
        "F": "#ef4444",  # red
    }.get(grade, "#94a3b8")


def _pct(value: float) -> str:
    """Format a 0-1 float as percentage string."""
    return f"{value * 100:.1f}%"


def _cost_fmt(cost: float) -> str:
    """Format dollar cost."""
    if cost < 0.01:
        return f"${cost:.4f}"
    return f"${cost:.2f}"


def _bar_html(value: float, width: int = 200) -> str:
    """Render a horizontal progress bar."""
    pct = max(0, min(100, value * 100))
    if pct >= 90:
        color = "#22c55e"
    elif pct >= 70:
        color = "#3b82f6"
    elif pct >= 50:
        color = "#eab308"
    else:
        color = "#ef4444"
    return (
        f'<div style="background:#1e293b;border-radius:4px;width:{width}px;height:20px;display:inline-block;vertical-align:middle">'
        f'<div style="background:{color};border-radius:4px;width:{pct:.1f}%;height:100%"></div>'
        f'</div>'
    )


def generate_html_report(report_data: dict) -> str:
    """Generate a standalone HTML report from unified report JSON.

    Args:
        report_data: Dict from unified_report (or loaded from report.json).

    Returns:
        Complete HTML string.
    """
    skill_name = _esc(report_data.get("skill_name", "Unknown"))
    skill_path = _esc(report_data.get("skill_path", ""))
    timestamp = report_data.get("timestamp", "")
    overall_score = report_data.get("overall_score", 0)
    overall_grade = report_data.get("overall_grade", "?")
    passed = report_data.get("passed", False)
    sections = report_data.get("sections", {})

    # Format timestamp
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        ts_display = dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        ts_display = timestamp

    # Build section HTML
    audit_html = _render_audit(sections.get("audit", {}))
    functional_html = _render_functional(sections.get("functional", {}))
    trigger_html = _render_trigger(sections.get("trigger", {}))

    grade_color = _grade_color(overall_grade)
    status_text = "PASSED" if passed else "FAILED"
    status_color = "#22c55e" if passed else "#ef4444"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Skill Eval Report — {skill_name}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0f172a;
    color: #e2e8f0;
    padding: 2rem;
    max-width: 900px;
    margin: 0 auto;
  }}
  h1 {{ color: #f8fafc; margin-bottom: 0.25rem; }}
  h2 {{
    color: #94a3b8;
    font-size: 1.1rem;
    margin-top: 2rem;
    margin-bottom: 0.75rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid #334155;
  }}
  .meta {{ color: #64748b; font-size: 0.85rem; margin-bottom: 1.5rem; }}
  .hero {{
    display: flex;
    align-items: center;
    gap: 1.5rem;
    margin-bottom: 2rem;
    padding: 1.5rem;
    background: #1e293b;
    border-radius: 12px;
    border: 1px solid #334155;
  }}
  .grade-circle {{
    width: 80px; height: 80px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 2rem;
    font-weight: bold;
    color: #0f172a;
    flex-shrink: 0;
  }}
  .hero-details {{ flex: 1; }}
  .hero-score {{ font-size: 1.5rem; font-weight: bold; color: #f8fafc; }}
  .hero-status {{ font-size: 0.9rem; margin-top: 0.25rem; }}
  .card {{
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 1.25rem;
    margin-bottom: 1rem;
  }}
  .card-title {{
    font-weight: 600;
    color: #f8fafc;
    margin-bottom: 0.75rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
  }}
  th, td {{
    text-align: left;
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid #334155;
  }}
  th {{ color: #94a3b8; font-weight: 500; }}
  td {{ color: #e2e8f0; }}
  .badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.8rem;
    font-weight: 600;
  }}
  .badge-critical {{ background: #7f1d1d; color: #fca5a5; }}
  .badge-warning {{ background: #713f12; color: #fde047; }}
  .badge-info {{ background: #1e3a5f; color: #93c5fd; }}
  .badge-pass {{ background: #14532d; color: #86efac; }}
  .badge-fail {{ background: #7f1d1d; color: #fca5a5; }}
  .metric-row {{
    display: flex;
    justify-content: space-between;
    padding: 0.4rem 0;
    border-bottom: 1px solid #1e293b;
  }}
  .metric-label {{ color: #94a3b8; }}
  .metric-value {{ color: #f8fafc; font-weight: 500; }}
  .footer {{
    margin-top: 2rem;
    padding-top: 1rem;
    border-top: 1px solid #334155;
    color: #475569;
    font-size: 0.8rem;
    text-align: center;
  }}
  .skipped {{ color: #64748b; font-style: italic; }}
  .error {{ color: #ef4444; }}
</style>
</head>
<body>

<h1>🔍 Skill Evaluation Report</h1>
<div class="meta">{skill_name} &mdash; {ts_display}</div>

<div class="hero">
  <div class="grade-circle" style="background:{grade_color}">{overall_grade}</div>
  <div class="hero-details">
    <div class="hero-score">Overall: {_pct(overall_score)}</div>
    <div class="hero-status" style="color:{status_color}">{status_text}</div>
    <div style="color:#64748b;font-size:0.8rem;margin-top:0.25rem">{skill_path}</div>
  </div>
</div>

{audit_html}
{functional_html}
{trigger_html}

<div class="footer">
  Generated by <strong>skill-eval</strong> &mdash;
  <a href="https://github.com/aws-samples/sample-agent-skill-eval" style="color:#3b82f6">GitHub</a>
</div>

</body>
</html>"""


def _render_audit(audit: dict) -> str:
    """Render audit section HTML."""
    if not audit or "error" in audit:
        err = _esc(audit.get("error", "Not run"))
        return f'<h2>🛡️ Security Audit</h2><div class="card error">Error: {err}</div>'
    if "skipped" in audit:
        return '<h2>🛡️ Security Audit</h2><div class="card skipped">Skipped</div>'

    score = audit.get("score", 0)
    grade = audit.get("grade", "?")
    critical = audit.get("critical", 0)
    warning = audit.get("warning", 0)
    info = audit.get("info", 0)
    gc = _grade_color(grade)

    findings_html = ""
    findings = audit.get("findings", [])
    if findings:
        rows = ""
        for f in findings:
            sev = f.get("severity", "INFO")
            badge_cls = {"CRITICAL": "badge-critical", "WARNING": "badge-warning"}.get(sev, "badge-info")
            rows += f"""<tr>
                <td><span class="badge {badge_cls}">{_esc(sev)}</span></td>
                <td>{_esc(f.get('code', ''))}</td>
                <td>{_esc(f.get('title', f.get('message', '')))}</td>
                <td>{_esc(f.get('file_path', '') or '')}</td>
            </tr>"""
        findings_html = f"""
        <table>
            <thead><tr><th>Severity</th><th>Code</th><th>Finding</th><th>File</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>"""

    return f"""<h2>🛡️ Security Audit</h2>
<div class="card">
  <div class="card-title">
    Score: {score}/100
    <span class="badge" style="background:{gc};color:#0f172a">{grade}</span>
  </div>
  <div class="metric-row">
    <span class="metric-label">Critical</span>
    <span class="metric-value" style="color:{'#ef4444' if critical else '#22c55e'}">{critical}</span>
  </div>
  <div class="metric-row">
    <span class="metric-label">Warning</span>
    <span class="metric-value" style="color:{'#eab308' if warning else '#22c55e'}">{warning}</span>
  </div>
  <div class="metric-row">
    <span class="metric-label">Info</span>
    <span class="metric-value">{info}</span>
  </div>
  {findings_html}
</div>"""


def _render_functional(func: dict) -> str:
    """Render functional evaluation section HTML."""
    if not func or "error" in func:
        err = _esc(func.get("error", "Not run"))
        return f'<h2>⚡ Functional Evaluation</h2><div class="card error">Error: {err}</div>'
    if "skipped" in func:
        reason = _esc(func.get("reason", ""))
        return f'<h2>⚡ Functional Evaluation</h2><div class="card skipped">Skipped — {reason}</div>'

    overall = func.get("overall", 0)
    grade = func.get("grade", "?")
    passed = func.get("passed", False)
    gc = _grade_color(grade)

    scores_html = ""
    scores = func.get("scores", {})
    if scores:
        rows = ""
        for key in ["outcome", "process", "style", "efficiency", "overall"]:
            val = scores.get(key, 0)
            bold = " font-weight:600;" if key == "overall" else ""
            rows += f"""<div class="metric-row">
                <span class="metric-label" style="{bold}">{key.title()}</span>
                <span class="metric-value" style="{bold}">{val:.2f} {_bar_html(val, 150)}</span>
            </div>"""
        scores_html = rows

    # Cost efficiency
    ce_html = ""
    ce = func.get("cost_efficiency")
    if ce:
        emoji = ce.get("emoji", "")
        cls = ce.get("classification", "")
        desc = _esc(ce.get("description", ""))
        qd = ce.get("quality_delta", 0)
        cd = ce.get("cost_delta_pct", 0)
        ce_html = f"""
        <div style="margin-top:0.75rem;padding:0.75rem;background:#0f172a;border-radius:6px">
            <div style="font-weight:500;margin-bottom:0.25rem">{emoji} {cls}</div>
            <div style="color:#94a3b8;font-size:0.85rem">{desc}</div>
            <div style="color:#94a3b8;font-size:0.85rem">Quality: {'+' if qd>=0 else ''}{qd:.2f} | Cost: {'+' if cd>=0 else ''}{cd:.1f}%</div>
        </div>"""

    # Estimated cost
    cost_html = ""
    ec = func.get("estimated_cost")
    if ec and ec.get("total_cost", 0) > 0:
        model = _esc(ec.get("model", "sonnet"))
        cost_html = f"""
        <div style="margin-top:0.75rem;padding:0.75rem;background:#0f172a;border-radius:6px">
            <div style="font-weight:500;margin-bottom:0.25rem">💰 Estimated Cost ({model} pricing)</div>
            <div class="metric-row">
                <span class="metric-label">Total</span>
                <span class="metric-value">{_cost_fmt(ec['total_cost'])}</span>
            </div>"""
        wc = ec.get("with_skill_per_run", {})
        woc = ec.get("without_skill_per_run", {})
        if wc and woc:
            cost_html += f"""
            <div class="metric-row">
                <span class="metric-label">With skill (per run)</span>
                <span class="metric-value">{_cost_fmt(wc['total_cost'])}</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">Without skill (per run)</span>
                <span class="metric-value">{_cost_fmt(woc['total_cost'])}</span>
            </div>"""
        cost_html += "</div>"

    status = '<span class="badge badge-pass">PASSED</span>' if passed else '<span class="badge badge-fail">FAILED</span>'

    return f"""<h2>⚡ Functional Evaluation</h2>
<div class="card">
  <div class="card-title">
    Score: {overall:.2f}
    <span class="badge" style="background:{gc};color:#0f172a">{grade}</span>
    {status}
  </div>
  {scores_html}
  {ce_html}
  {cost_html}
</div>"""


def _render_trigger(trigger: dict) -> str:
    """Render trigger evaluation section HTML."""
    if not trigger or "error" in trigger:
        err = _esc(trigger.get("error", "Not run"))
        return f'<h2>🎯 Trigger Reliability</h2><div class="card error">Error: {err}</div>'
    if "skipped" in trigger:
        reason = _esc(trigger.get("reason", ""))
        return f'<h2>🎯 Trigger Reliability</h2><div class="card skipped">Skipped — {reason}</div>'

    pass_rate = trigger.get("pass_rate", 0)
    grade = trigger.get("grade", "?")
    passed = trigger.get("passed", False)
    total = trigger.get("total_queries", 0)
    gc = _grade_color(grade)

    status = '<span class="badge badge-pass">PASSED</span>' if passed else '<span class="badge badge-fail">FAILED</span>'

    # Query results if available
    queries_html = ""
    query_results = trigger.get("query_results", [])
    if query_results:
        rows = ""
        for qr in query_results:
            q_passed = qr.get("passed", False)
            badge = '<span class="badge badge-pass">PASS</span>' if q_passed else '<span class="badge badge-fail">FAIL</span>'
            expected = "trigger" if qr.get("should_trigger") else "no-trigger"
            rate = qr.get("trigger_rate", 0)
            query_text = _esc(qr.get("query", "")[:60])
            rows += f"""<tr>
                <td>{badge}</td>
                <td>{query_text}</td>
                <td>{expected}</td>
                <td>{rate:.0%}</td>
            </tr>"""
        queries_html = f"""
        <table>
            <thead><tr><th>Result</th><th>Query</th><th>Expected</th><th>Rate</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>"""

    return f"""<h2>🎯 Trigger Reliability</h2>
<div class="card">
  <div class="card-title">
    Pass Rate: {_pct(pass_rate)}
    <span class="badge" style="background:{gc};color:#0f172a">{grade}</span>
    {status}
  </div>
  <div class="metric-row">
    <span class="metric-label">Total Queries</span>
    <span class="metric-value">{total}</span>
  </div>
  {queries_html}
</div>"""
