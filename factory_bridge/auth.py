"""Authentication handling for Factory Bridge"""

import logging
from factory_bridge.config import CLIPROXY_AUTH_DIR


def check_auth():
    """Check if OAuth tokens exist"""
    if not CLIPROXY_AUTH_DIR.exists():
        logging.warning(f"Auth directory does not exist: {CLIPROXY_AUTH_DIR}")
        return False

    auth_files = list(CLIPROXY_AUTH_DIR.glob("*.json"))
    if auth_files:
        logging.info(f"Found {len(auth_files)} auth file(s)")
        return True
    else:
        logging.warning("No auth files found")
        return False
