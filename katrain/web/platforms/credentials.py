"""Encrypted credential storage for platform adapters.

Mandatory encryption — no fallback to plaintext.
Storage: ~/.katrain/platform_credentials.db (SQLite)
Encryption: AES-256-GCM via cryptography.fernet
Key derivation:
  - Server mode: from KaTrain user password via PBKDF2
  - Board mode: from hardware-bound ID (RK3588 CPU serial) + local salt
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from katrain.web.platforms.models import PlatformCredentials

logger = logging.getLogger("katrain_web")

_DB_PATH = Path.home() / ".katrain" / "platform_credentials.db"
_SALT_PATH = Path.home() / ".katrain" / ".platform_salt"

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS platform_credentials (
    user_id INTEGER NOT NULL,
    platform TEXT NOT NULL,
    username TEXT NOT NULL,
    auth_data_encrypted BLOB NOT NULL,
    created_at TEXT,
    updated_at TEXT,
    PRIMARY KEY (user_id, platform)
);
"""


def _get_salt() -> bytes:
    """Get or create a persistent random salt."""
    if _SALT_PATH.exists():
        return _SALT_PATH.read_bytes()
    _SALT_PATH.parent.mkdir(parents=True, exist_ok=True)
    salt = os.urandom(16)
    _SALT_PATH.write_bytes(salt)
    os.chmod(_SALT_PATH, 0o600)
    return salt


def _derive_fernet_key(secret: str) -> bytes:
    """Derive a Fernet-compatible key from a secret string via PBKDF2."""
    salt = _get_salt()
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480_000)
    raw_key = kdf.derive(secret.encode("utf-8"))
    return base64.urlsafe_b64encode(raw_key)


def _get_hardware_id() -> str:
    """Get hardware-bound identifier for board mode key derivation."""
    # Try RK3588 CPU serial from /proc/cpuinfo
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("Serial"):
                    return line.split(":")[-1].strip()
    except (OSError, IOError):
        pass
    # Fallback: machine-id (Linux) or hostname-based
    for path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
        try:
            return Path(path).read_text().strip()
        except (OSError, IOError):
            continue
    # Last resort: hostname hash (not ideal, but deterministic)
    import socket

    return hashlib.sha256(socket.gethostname().encode()).hexdigest()


class PlatformCredentialStore:
    """Encrypted credential store for platform login tokens."""

    def __init__(self, secret: Optional[str] = None, db_path: Optional[Path] = None):
        """Initialize the credential store.

        Args:
            secret: Encryption secret. If None, derives from hardware ID (board mode).
            db_path: Override DB path for testing.
        """
        if secret is None:
            secret = _get_hardware_id()
        self._fernet_key = _derive_fernet_key(secret)
        self._fernet = Fernet(self._fernet_key)
        self._db_path = db_path or _DB_PATH
        self._init_db()

    def _init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_INIT_SQL)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db_path))

    def save_credentials(self, user_id: int, credentials: PlatformCredentials) -> None:
        """Save or update credentials for a platform."""
        now = datetime.now(timezone.utc).isoformat()
        encrypted = self._fernet.encrypt(json.dumps(credentials.auth_data).encode("utf-8"))
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO platform_credentials (user_id, platform, username, auth_data_encrypted, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, platform) DO UPDATE SET
                    username = excluded.username,
                    auth_data_encrypted = excluded.auth_data_encrypted,
                    updated_at = excluded.updated_at
                """,
                (user_id, credentials.platform, credentials.username, encrypted, now, now),
            )
        logger.debug(f"Saved credentials for user {user_id} on {credentials.platform}")

    def load_credentials(self, user_id: int, platform: str) -> Optional[PlatformCredentials]:
        """Load credentials for a platform. Returns None if not found or decryption fails."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT platform, username, auth_data_encrypted FROM platform_credentials WHERE user_id = ? AND platform = ?",
                (user_id, platform),
            ).fetchone()
        if row is None:
            return None
        try:
            auth_data = json.loads(self._fernet.decrypt(row[2]))
            return PlatformCredentials(platform=row[0], username=row[1], auth_data=auth_data)
        except (InvalidToken, json.JSONDecodeError) as e:
            logger.error(f"Failed to decrypt credentials for user {user_id} on {platform}: {e}")
            return None

    def delete_credentials(self, user_id: int, platform: str) -> bool:
        """Delete credentials for a platform. Returns True if a row was deleted."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM platform_credentials WHERE user_id = ? AND platform = ?",
                (user_id, platform),
            )
        deleted = cursor.rowcount > 0
        if deleted:
            logger.debug(f"Deleted credentials for user {user_id} on {platform}")
        return deleted

    def list_platforms(self, user_id: int) -> list[dict]:
        """List all platforms with saved credentials for a user."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT platform, username, updated_at FROM platform_credentials WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        return [{"platform": r[0], "username": r[1], "updated_at": r[2]} for r in rows]
