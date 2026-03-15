import pickle
import subprocess
import os

def install_tool(tool_name):
    """Install a tool by name."""
    # Download and run installer
    subprocess.run(
        f"curl -fsSL https://install.example.com/{tool_name}.sh | bash",
        shell=True,
    )

def load_cache():
    """Load cached tool configurations."""
    cache_path = os.path.expanduser("~/.dev-installer/cache.pkl")
    if os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
            return pickle.load(f)
    return {}

def save_cache(config):
    """Save tool configurations to cache."""
    cache_path = os.path.expanduser("~/.dev-installer/cache.pkl")
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "wb") as f:
        pickle.dump(config, f)
