#!/usr/bin/env python3
"""Factory Bridge - Use Claude Code OAuth with Factory AI"""

import argparse
import logging
import sys
from factory_bridge.config import (
    DEFAULT_PROXY_PORT,
    FACTORY_CONFIG,
    CUSTOM_PROMPT_CONFIG,
)
from factory_bridge.auth import check_auth
from factory_bridge.cliproxy import setup_cliproxy, start_cliproxy, run_cliproxy_login
from factory_bridge.server import generate_factory_config, run_server


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def main():
    parser = argparse.ArgumentParser(description="Factory AI + Claude Code OAuth Proxy")
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PROXY_PORT,
        help=f"Proxy port (default: {DEFAULT_PROXY_PORT})",
    )
    parser.add_argument(
        "--login", action="store_true", help="Authenticate with Claude Code"
    )
    parser.add_argument("--setup", action="store_true", help="Setup CLIProxyAPI only")
    args = parser.parse_args()

    setup_cliproxy()

    if args.login:
        print("\nAuthenticating with Claude Code...")
        print("Browser will open for OAuth login\n")
        success = run_cliproxy_login()
        if success:
            print("\nAuthentication successful!")
        sys.exit(0 if success else 1)

    if args.setup:
        print("CLIProxyAPI setup complete")
        sys.exit(0)

    if not check_auth():
        print("\nNo authentication found.")
        print(f"Run: python {sys.argv[0]} --login\n")
        sys.exit(1)

    if not FACTORY_CONFIG.exists():
        generate_factory_config(args.port)

    if not start_cliproxy():
        sys.exit(1)

    if CUSTOM_PROMPT_CONFIG.exists():
        logging.info(f"Custom prompt config detected: {CUSTOM_PROMPT_CONFIG}")
    else:
        logging.info("No custom prompt config found, using Factory default prompts")

    run_server(args.port)


if __name__ == "__main__":
    main()
