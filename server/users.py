"""
VPS Archive Lens - Multi-User Management Engine
Handles user provisioning, token validation, secure comparison, and persistence.
"""

import os
import json
import secrets
import hmac
import logging
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger("archiver.users")


@dataclass
class UserRecord:
    username: str
    token: str
    role: str = "user"  # "admin" or "user"
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "UserRecord":
        return cls(
            username=data.get("username", ""),
            token=data.get("token", ""),
            role=data.get("role", "user"),
            created_at=data.get("created_at", "")
        )


class UserManager:
    """
    Manages multi-user authentication credentials with persistent JSON storage
    and automatic fallback to environment variables (USER_TOKENS or API_TOKEN).
    """

    def __init__(self, storage_dir: Optional[Path] = None):
        if storage_dir:
            self.storage_dir = Path(storage_dir).resolve()
        else:
            env_dir = os.getenv("STORAGE_DIR")
            if env_dir:
                self.storage_dir = Path(env_dir).resolve()
            elif Path("/home/hermes/personal-archiver/snapshots").exists():
                self.storage_dir = Path("/home/hermes/personal-archiver/snapshots")
            else:
                self.storage_dir = (Path(__file__).resolve().parent.parent / "snapshots").resolve()
        self.users_file = self.storage_dir / "users.json"
        self._lock = threading.RLock()
        self._users: Dict[str, UserRecord] = {}
        self._token_to_user: Dict[str, UserRecord] = {}
        self._last_mtime: float = 0.0

        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.reload()

    def _generate_token(self, prefix: str = "lens_") -> str:
        return f"{prefix}{secrets.token_urlsafe(24)}"

    def reload(self) -> None:
        """Loads users from users.json if present; otherwise initializes from environment."""
        with self._lock:
            loaded_from_file = False
            if self.users_file.is_file():
                try:
                    mtime = self.users_file.stat().st_mtime
                    with open(self.users_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    users: Dict[str, UserRecord] = {}
                    tokens: Dict[str, UserRecord] = {}
                    for username, udata in data.items():
                        udata["username"] = username
                        rec = UserRecord.from_dict(udata)
                        if rec.username and rec.token:
                            users[rec.username] = rec
                            tokens[rec.token] = rec
                    
                    self._users = users
                    self._token_to_user = tokens
                    self._last_mtime = mtime
                    loaded_from_file = True
                except Exception as e:
                    logger.error(f"Failed to read users.json: {e}. Falling back to environment.")

            if not loaded_from_file:
                self._seed_from_env()

    def _seed_from_env(self) -> None:
        """Seeds users from USER_TOKENS or legacy API_TOKEN environment variables."""
        users: Dict[str, UserRecord] = {}
        tokens: Dict[str, UserRecord] = {}
        now_iso = datetime.now(timezone.utc).isoformat()

        # Check USER_TOKENS format: "admin:secret123:admin,friend:secret456:user" or "admin:secret123,friend"
        env_user_tokens = os.getenv("USER_TOKENS", "").strip()
        if env_user_tokens:
            entries = [e.strip() for e in env_user_tokens.split(",") if e.strip()]
            for idx, entry in enumerate(entries):
                if ":" in entry:
                    parts = [p.strip() for p in entry.split(":")]
                    if len(parts) >= 3:
                        name, tok, r = parts[0], parts[1], parts[2]
                        role = "admin" if r.lower() == "admin" else "user"
                    elif len(parts) == 2:
                        name, tok = parts[0], parts[1]
                        role = "admin" if (idx == 0 or name.lower() == "admin") else "user"
                    else:
                        name = parts[0]
                        tok = self._generate_token()
                        role = "admin" if (idx == 0 or name.lower() == "admin") else "user"
                else:
                    name = entry.strip()
                    tok = self._generate_token()
                    role = "admin" if (idx == 0 or name.lower() == "admin") else "user"

                if name and tok:
                    clean_name = name.lower()
                    rec = UserRecord(username=clean_name, token=tok, role=role, created_at=now_iso)
                    users[clean_name] = rec
                    tokens[tok] = rec

        # Check legacy API_TOKEN (single or comma-separated tokens)
        legacy_api_token = os.getenv("API_TOKEN", "").strip()
        if legacy_api_token and not users:
            token_list = [t.strip() for t in legacy_api_token.split(",") if t.strip()]
            for idx, tok in enumerate(token_list):
                name = "admin" if idx == 0 else f"user_{idx + 1}"
                role = "admin" if idx == 0 else "user"
                rec = UserRecord(username=name, token=tok, role=role, created_at=now_iso)
                users[name] = rec
                tokens[tok] = rec

        self._users = users
        self._token_to_user = tokens
        if users and not self.users_file.is_file():
            try:
                self._save_to_disk()
            except Exception as e:
                logger.warning(f"Could not persist seeded users to {self.users_file}: {e}")

    def _sync_if_file_changed(self) -> None:
        """Checks if users.json was modified externally (e.g. via CLI tool)."""
        if self.users_file.is_file():
            try:
                curr_mtime = self.users_file.stat().st_mtime
                if curr_mtime > self._last_mtime:
                    self.reload()
            except Exception:
                pass

    def _save_to_disk(self) -> None:
        """Persists current user dictionary to users.json atomically."""
        temp_file = self.users_file.with_suffix(".tmp")
        payload = {}
        for username, rec in self._users.items():
            d = rec.to_dict()
            d.pop("username", None)
            payload[username] = d

        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        temp_file.replace(self.users_file)
        self._last_mtime = self.users_file.stat().st_mtime

    def authenticate(self, token: Optional[str]) -> Optional[UserRecord]:
        """
        Validates token using constant-time comparison against known tokens.
        Returns UserRecord if valid, None otherwise.
        """
        if not token:
            return None

        self._sync_if_file_changed()
        tok = token.strip()

        # If no users configured at all, anyone is allowed as anonymous
        if not self._token_to_user:
            return UserRecord(username="anonymous", token="", role="admin")

        # Fast constant-time lookup
        for known_token, user in self._token_to_user.items():
            if hmac.compare_digest(tok, known_token):
                return user
        return None

    def add_user(self, username: str, role: str = "user", custom_token: Optional[str] = None, overwrite: bool = False) -> UserRecord:
        """Creates or updates a user and saves to disk."""
        clean_name = username.strip().lower()
        if not clean_name or len(clean_name) < 2:
            raise ValueError("Username must be at least 2 characters long.")
        if not clean_name.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Username may only contain letters, numbers, hyphens, and underscores.")

        with self._lock:
            self._sync_if_file_changed()
            if not overwrite and clean_name in self._users:
                raise ValueError(f"User '{clean_name}' already exists.")

            token = custom_token.strip() if custom_token else self._generate_token()
            role = "admin" if role.lower() == "admin" else "user"
            now_iso = datetime.now(timezone.utc).isoformat()

            rec = UserRecord(username=clean_name, token=token, role=role, created_at=now_iso)
            self._users[clean_name] = rec
            self._token_to_user[token] = rec
            self._save_to_disk()
            logger.info(f"User '{clean_name}' ({role}) created/updated successfully.")
            return rec

    def revoke_user(self, username: str) -> bool:
        """Revokes a user's token and access."""
        clean_name = username.strip().lower()
        with self._lock:
            self._sync_if_file_changed()
            if clean_name not in self._users:
                return False
            rec = self._users.pop(clean_name)
            self._token_to_user.pop(rec.token, None)
            self._save_to_disk()
            logger.info(f"User '{clean_name}' revoked.")
            return True

    def list_users(self) -> List[UserRecord]:
        """Returns all registered users."""
        self._sync_if_file_changed()
        return list(self._users.values())

    def get_user(self, username: str) -> Optional[UserRecord]:
        """Fetches a user record by username."""
        self._sync_if_file_changed()
        return self._users.get(username.strip().lower())

    def get_user_by_token(self, token: Optional[str]) -> Optional[UserRecord]:
        """Alias for authenticate(token)."""
        return self.authenticate(token)

    def get_user_by_username(self, username: str) -> Optional[UserRecord]:
        """Alias for get_user(username)."""
        return self.get_user(username)

    def has_users(self) -> bool:
        """Returns True if any users exist."""
        self._sync_if_file_changed()
        return bool(self._users)
