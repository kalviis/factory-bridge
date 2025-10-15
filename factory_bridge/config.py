"""Configuration and constants for Factory Bridge"""

from pathlib import Path

DEFAULT_PROXY_PORT = 8318
CLIPROXY_PORT = 8319

PROJECT_DIR = Path(__file__).parent.parent
PROXY_DIR = Path.home() / ".droid-proxy"
CLIPROXY_DIR = PROXY_DIR / "CLIProxyAPI"
CLIPROXY_CONFIG = PROXY_DIR / "cliproxy-config.yaml"
CLIPROXY_AUTH_DIR = Path.home() / ".cli-proxy-api"
FACTORY_CONFIG = Path.home() / ".factory" / "config.json"
CUSTOM_PROMPT_CONFIG = PROJECT_DIR / "prompt-config.json"

CLAUDE_MODELS = [
    "claude-sonnet-4-5-20250929",
    "claude-sonnet-4-20250514",
    "claude-3-5-haiku-20241022",
]
