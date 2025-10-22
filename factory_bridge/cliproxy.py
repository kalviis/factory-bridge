"""CLIProxyAPI management for Factory Bridge"""

import atexit
import signal
import subprocess
import sys
import json
import time
from factory_bridge.config import (
    PROXY_DIR,
    CLIPROXY_DIR,
    CLIPROXY_CONFIG,
    CLIPROXY_PORT,
    CLIPROXY_AUTH_DIR,
    CLIPROXY_COMMIT,
)

cliproxy_process = None


def cleanup():
    """Stop CLIProxyAPI on exit"""
    global cliproxy_process
    if cliproxy_process and cliproxy_process.poll() is None:
        cliproxy_process.terminate()
        try:
            cliproxy_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cliproxy_process.kill()


atexit.register(cleanup)
signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))


def patch_cliproxy():
    """Patch CLIProxyAPI to remove cache_control from Claude Code instructions"""
    instructions_file = (
        CLIPROXY_DIR / "internal" / "misc" / "claude_code_instructions.txt"
    )

    if not instructions_file.exists():
        return False

    content = instructions_file.read_text()

    # Check if already patched
    if "cache_control" not in content:
        return True

    # Remove cache_control from the instructions, handle it from our proxy instead
    try:
        instructions = json.loads(content)
        for block in instructions:
            if isinstance(block, dict) and "cache_control" in block:
                del block["cache_control"]
        instructions_file.write_text(json.dumps(instructions))
        print(
            "Patching CLIProxyAPI..."
        )
        return True
    except json.JSONDecodeError:
        print("Warning: Failed to parse Claude Code instructions")
        return False


def setup_cliproxy():
    """Clone and build CLIProxyAPI if needed"""
    PROXY_DIR.mkdir(parents=True, exist_ok=True)

    if not CLIPROXY_DIR.exists():
        print(f"Cloning CLIProxyAPI...")
        result = subprocess.run(
            [
                "git",
                "clone",
                "https://github.com/router-for-me/CLIProxyAPI.git",
                str(CLIPROXY_DIR),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"Error cloning CLIProxyAPI: {result.stderr}")
            sys.exit(1)

        # Checkout specific commit to avoid breaking changes
        result = subprocess.run(
            ["git", "checkout", CLIPROXY_COMMIT],
            cwd=CLIPROXY_DIR,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"Error checking out commit {CLIPROXY_COMMIT}: {result.stderr}")
            sys.exit(1)

        if not patch_cliproxy():
            print("Warning: Failed to patch CLIProxyAPI")

    binary = CLIPROXY_DIR / "cli-proxy-api"
    if not binary.exists():
        if CLIPROXY_DIR.exists() and not (CLIPROXY_DIR / "internal").exists():
            print("CLIProxyAPI directory exists but appears incomplete, re-cloning...")
            import shutil

            shutil.rmtree(CLIPROXY_DIR)
            setup_cliproxy()
            return

        # Ensure we're on the correct commit
        if CLIPROXY_DIR.exists():
            result = subprocess.run(
                ["git", "checkout", CLIPROXY_COMMIT],
                cwd=CLIPROXY_DIR,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                print(f"Warning: Could not checkout commit {CLIPROXY_COMMIT}")

        if not patch_cliproxy():
            print("Warning: Failed to patch CLIProxyAPI")

        print("Building CLIProxyAPI...")
        result = subprocess.run(
            ["go", "build", "-o", "cli-proxy-api", "./cmd/server"],
            cwd=CLIPROXY_DIR,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"Error building CLIProxyAPI: {result.stderr}")
            print("Make sure Go is installed: https://go.dev/doc/install")
            sys.exit(1)

    config_content = f"""port: {CLIPROXY_PORT}
auth-dir: "{CLIPROXY_AUTH_DIR}"
debug: false
logging-to-file: false
usage-statistics-enabled: false
request-retry: 3
remote-management:
  allow-remote: false
  secret-key: ""
auth:
  providers: []
"""

    CLIPROXY_CONFIG.write_text(config_content)


def start_cliproxy():
    """Start CLIProxyAPI in background"""
    global cliproxy_process

    if cliproxy_process and cliproxy_process.poll() is None:
        return True

    binary = CLIPROXY_DIR / "cli-proxy-api"
    cliproxy_process = subprocess.Popen(
        [str(binary), "--config", str(CLIPROXY_CONFIG)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    time.sleep(1)

    if cliproxy_process.poll() is not None:
        print("Error: CLIProxyAPI failed to start")
        return False

    return True


def run_cliproxy_login():
    """Run CLIProxyAPI login command"""
    binary = CLIPROXY_DIR / "cli-proxy-api"
    result = subprocess.run(
        [str(binary), "--config", str(CLIPROXY_CONFIG), "--claude-login"],
        cwd=CLIPROXY_DIR,
    )
    return result.returncode == 0
