from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from app.models import ChatHistoryItem, UserPreferences, UserProfile, UserStateResponse


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuthService:
    def __init__(self, db_path: str, default_tenant: str, default_stadium: str) -> None:
        self._db_path = Path(db_path)
        self._default_tenant = default_tenant
        self._default_stadium = default_stadium
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id INTEGER PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    stadium_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );
                """
            )
            connection.commit()

    def _hash_password(self, password: str, salt: str | None = None) -> str:
        salt_value = salt or secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt_value.encode("utf-8"),
            150_000,
        ).hex()
        return f"{salt_value}${digest}"

    def _verify_password(self, password: str, stored_hash: str) -> bool:
        salt, digest = stored_hash.split("$", maxsplit=1)
        return secrets.compare_digest(self._hash_password(password, salt), f"{salt}${digest}")

    def _row_to_user(self, row: sqlite3.Row) -> UserProfile:
        return UserProfile(id=row["id"], email=row["email"], full_name=row["full_name"])

    def signup(self, email: str, password: str, full_name: str) -> tuple[str, UserProfile]:
        normalized_email = email.strip().lower()
        with self._connect() as connection:
            cursor = connection.cursor()
            existing = cursor.execute(
                "SELECT id FROM users WHERE email = ?",
                (normalized_email,),
            ).fetchone()
            if existing:
                raise HTTPException(status_code=409, detail="Email is already registered.")

            password_hash = self._hash_password(password)
            cursor.execute(
                "INSERT INTO users(email, password_hash, full_name, created_at) VALUES (?, ?, ?, ?)",
                (normalized_email, password_hash, full_name.strip(), utc_now()),
            )
            user_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO user_preferences(user_id, tenant_id, stadium_id, updated_at) VALUES (?, ?, ?, ?)",
                (user_id, self._default_tenant, self._default_stadium, utc_now()),
            )
            connection.commit()

        return self.login(normalized_email, password)

    def login(self, email: str, password: str) -> tuple[str, UserProfile]:
        normalized_email = email.strip().lower()
        with self._connect() as connection:
            cursor = connection.cursor()
            row = cursor.execute(
                "SELECT id, email, full_name, password_hash FROM users WHERE email = ?",
                (normalized_email,),
            ).fetchone()
            if not row or not self._verify_password(password, row["password_hash"]):
                raise HTTPException(status_code=401, detail="Invalid email or password.")

            token = secrets.token_urlsafe(32)
            cursor.execute(
                "INSERT INTO sessions(token, user_id, created_at) VALUES (?, ?, ?)",
                (token, row["id"], utc_now()),
            )
            connection.commit()
            return token, self._row_to_user(row)

    def authenticate(self, token: str) -> UserProfile:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT users.id, users.email, users.full_name
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token = ?
                """,
                (token,),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=401, detail="Invalid or expired session.")
            return self._row_to_user(row)

    def get_user_state(self, user_id: int) -> UserStateResponse:
        with self._connect() as connection:
            user_row = connection.execute(
                "SELECT id, email, full_name FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            pref_row = connection.execute(
                "SELECT tenant_id, stadium_id FROM user_preferences WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            history_rows = connection.execute(
                "SELECT role, message, created_at FROM chat_history WHERE user_id = ? ORDER BY id ASC LIMIT 30",
                (user_id,),
            ).fetchall()

        preferences = UserPreferences(
            tenant_id=pref_row["tenant_id"] if pref_row else self._default_tenant,
            stadium_id=pref_row["stadium_id"] if pref_row else self._default_stadium,
        )
        history = [
            ChatHistoryItem(
                role=row["role"],
                message=row["message"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in history_rows
        ]
        return UserStateResponse(
            user=self._row_to_user(user_row),
            preferences=preferences,
            chat_history=history,
        )

    def update_preferences(self, user_id: int, tenant_id: str, stadium_id: str) -> UserPreferences:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO user_preferences(user_id, tenant_id, stadium_id, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    tenant_id = excluded.tenant_id,
                    stadium_id = excluded.stadium_id,
                    updated_at = excluded.updated_at
                """,
                (user_id, tenant_id, stadium_id, utc_now()),
            )
            connection.commit()
        return UserPreferences(tenant_id=tenant_id, stadium_id=stadium_id)

    def save_chat_exchange(self, user_id: int, question: str, answer: str) -> None:
        with self._connect() as connection:
            connection.executemany(
                "INSERT INTO chat_history(user_id, role, message, created_at) VALUES (?, ?, ?, ?)",
                [
                    (user_id, "user", question, utc_now()),
                    (user_id, "assistant", answer, utc_now()),
                ],
            )
            connection.commit()