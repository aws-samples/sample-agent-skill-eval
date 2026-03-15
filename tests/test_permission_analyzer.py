"""Tests for permission_analyzer module."""

import pytest
from pathlib import Path

from skill_eval.audit.permission_analyzer import analyze_permissions
from skill_eval.schemas import Severity


FIXTURES = Path(__file__).parent / "fixtures"


class TestPermissionAnalysis:
    """Test allowed-tools permission analysis."""

    def test_unscoped_bash_flagged(self):
        frontmatter = {"allowed-tools": "Bash(*) Read Write"}
        findings = analyze_permissions(FIXTURES / "bad-skill", frontmatter=frontmatter)
        perm_findings = [f for f in findings if f.code == "PERM-001"]
        assert len(perm_findings) > 0, "Unscoped Bash should be flagged"

    def test_scoped_bash_ok(self):
        frontmatter = {"allowed-tools": "Bash(python3:*) Bash(git:*) Read"}
        findings = analyze_permissions(FIXTURES / "good-skill", frontmatter=frontmatter)
        perm001 = [f for f in findings if f.code == "PERM-001"]
        assert len(perm001) == 0, "Scoped Bash should not be flagged as unrestricted"

    def test_many_tools_flagged(self):
        tools = " ".join([f"Tool{i}" for i in range(20)])
        frontmatter = {"allowed-tools": tools}
        findings = analyze_permissions(FIXTURES / "good-skill", frontmatter=frontmatter)
        perm003 = [f for f in findings if f.code == "PERM-003"]
        assert len(perm003) > 0, "Many tools should trigger PERM-003"

    def test_no_allowed_tools_ok(self):
        frontmatter = {"name": "test", "description": "Test skill"}
        findings = analyze_permissions(FIXTURES / "good-skill", frontmatter=frontmatter)
        perm_findings = [f for f in findings if f.code.startswith("PERM-00")]
        # Should not flag anything for missing allowed-tools (it's optional)
        assert all(f.code not in ("PERM-001", "PERM-002", "PERM-003") for f in perm_findings)

    def test_bad_skill_has_permission_findings(self):
        """Test with bad-skill fixture which has Bash(*) in frontmatter."""
        findings = analyze_permissions(FIXTURES / "bad-skill")
        assert len(findings) > 0, "Bad skill should have permission findings"

    def test_sensitive_directory_access(self):
        """Test detection of instructions referencing sensitive dirs."""
        frontmatter = {"name": "test", "description": "Test"}
        content = "---\nname: test\ndescription: Test\n---\n\nRead the credentials from ~/.ssh/id_rsa\n"
        findings = analyze_permissions(
            FIXTURES / "good-skill", 
            frontmatter=frontmatter,
            skill_content=content,
        )
        perm004 = [f for f in findings if f.code == "PERM-004"]
        assert len(perm004) > 0, "Should flag access to ~/.ssh"

    def test_sudo_access(self):
        content = "---\nname: test\ndescription: Test\n---\n\nUse sudo to install the package\n"
        findings = analyze_permissions(
            FIXTURES / "good-skill",
            frontmatter={"name": "test", "description": "Test"},
            skill_content=content,
        )
        perm004 = [f for f in findings if f.code == "PERM-004"]
        assert len(perm004) > 0, "Should flag sudo usage"

    def test_shell_terminal_flagged_as_unrestricted(self):
        """Shell and Terminal tool names should be treated as unscoped like Bash."""
        for tool_name in ("Shell", "Terminal"):
            frontmatter = {"allowed-tools": f"{tool_name} Read"}
            findings = analyze_permissions(FIXTURES / "good-skill", frontmatter=frontmatter)
            perm001 = [f for f in findings if f.code == "PERM-001"]
            assert len(perm001) > 0, f"{tool_name} should trigger PERM-001"

    def test_bare_bash_flagged(self):
        """'Bash' without parens should be flagged as unrestricted."""
        frontmatter = {"allowed-tools": "Bash Read Write"}
        findings = analyze_permissions(FIXTURES / "good-skill", frontmatter=frontmatter)
        perm001 = [f for f in findings if f.code == "PERM-001"]
        assert len(perm001) > 0, "Bare 'Bash' should be flagged as unrestricted"

    def test_absolute_path_reference(self):
        content = "---\nname: test\ndescription: Test\n---\n\nRead the config from /etc/nginx/nginx.conf\n"
        findings = analyze_permissions(
            FIXTURES / "good-skill",
            frontmatter={"name": "test", "description": "Test"},
            skill_content=content,
        )
        perm005 = [f for f in findings if f.code == "PERM-005"]
        assert len(perm005) > 0, "Should flag absolute system path reference"
