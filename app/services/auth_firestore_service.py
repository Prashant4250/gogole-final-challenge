from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import HTTPException
from google.cloud import firestore

from app.models import ChatHistoryItem, UserPreferences, UserProfile, UserStateResponse


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FirestoreAuthService:
    def __init__(
        self,
        project_id: str,
        default_tenant: str,
        default_stadium: str,
        collection_prefix: str = "crowdflow",
    ) -> None:
        if not project_id:
            raise ValueError("CROWDFLOW_GCP_PROJECT_ID is required when auth backend is firestore.")

        self._client = firestore.Client(project=project_id)
        self._default_tenant = default_tenant
        self._default_stadium = default_stadium

        self._users = self._client.collection(f"{collection_prefix}_users")
        self._email_index = self._client.collection(f"{collection_prefix}_email_index")
        self._sessions = self._client.collection(f"{collection_prefix}_sessions")
        self._meta = self._client.collection(f"{collection_prefix}_meta")

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
        salt, _ = stored_hash.split("$", maxsplit=1)
        return secrets.compare_digest(self._hash_password(password, salt), stored_hash)

    def _next_user_id(self) -> int:
        counter_ref = self._meta.document("counters")

        @firestore.transactional
        def allocate(transaction: firestore.Transaction) -> int:
            snapshot = counter_ref.get(transaction=transaction)
            next_user_id = int(snapshot.get("next_user_id") or 1) if snapshot.exists else 1
            transaction.set(counter_ref, {"next_user_id": next_user_id + 1}, merge=True)
            return next_user_id

        return allocate(self._client.transaction())

    def _email_key(self, normalized_email: str) -> str:
        return normalized_email.replace("/", "_slash_")

    def _row_to_user(self, user_doc: dict, user_id: int) -> UserProfile:
        return UserProfile(id=user_id, email=user_doc["email"], full_name=user_doc["full_name"])

    def signup(self, email: str, password: str, full_name: str) -> tuple[str, UserProfile]:
        normalized_email = email.strip().lower()
        email_ref = self._email_index.document(self._email_key(normalized_email))

        user_id = self._next_user_id()
        user_ref = self._users.document(str(user_id))
        now = utc_now()

        @firestore.transactional
        def create_user(transaction: firestore.Transaction) -> None:
            if email_ref.get(transaction=transaction).exists:
                raise HTTPException(status_code=409, detail="Email is already registered.")

            transaction.set(
                user_ref,
                {
                    "id": user_id,
                    "email": normalized_email,
                    "password_hash": self._hash_password(password),
                    "full_name": full_name.strip(),
                    "created_at": now,
                    "preferences": {
                        "tenant_id": self._default_tenant,
                        "stadium_id": self._default_stadium,
                        "updated_at": now,
                    },
                },
            )
            transaction.set(email_ref, {"user_id": user_id, "email": normalized_email})

        create_user(self._client.transaction())
        return self.login(normalized_email, password)

    def login(self, email: str, password: str) -> tuple[str, UserProfile]:
        normalized_email = email.strip().lower()
        email_doc = self._email_index.document(self._email_key(normalized_email)).get()
        if not email_doc.exists:
            raise HTTPException(status_code=401, detail="Invalid email or password.")

        user_id = int(email_doc.get("user_id"))
        user_snapshot = self._users.document(str(user_id)).get()
        if not user_snapshot.exists:
            raise HTTPException(status_code=401, detail="Invalid email or password.")

        user = user_snapshot.to_dict() or {}
        if not self._verify_password(password, user.get("password_hash", "")):
            raise HTTPException(status_code=401, detail="Invalid email or password.")

        token = secrets.token_urlsafe(32)
        self._sessions.document(token).set({"user_id": user_id, "created_at": utc_now()})
        return token, self._row_to_user(user, user_id)

    def authenticate(self, token: str) -> UserProfile:
        session_snapshot = self._sessions.document(token).get()
        if not session_snapshot.exists:
            raise HTTPException(status_code=401, detail="Invalid or expired session.")

        user_id = int(session_snapshot.get("user_id"))
        user_snapshot = self._users.document(str(user_id)).get()
        if not user_snapshot.exists:
            raise HTTPException(status_code=401, detail="Invalid or expired session.")

        user = user_snapshot.to_dict() or {}
        return self._row_to_user(user, user_id)

    def get_user_state(self, user_id: int) -> UserStateResponse:
        user_snapshot = self._users.document(str(user_id)).get()
        if not user_snapshot.exists:
            raise HTTPException(status_code=404, detail="User not found.")

        user = user_snapshot.to_dict() or {}
        prefs = user.get("preferences") or {}

        history_ref = self._users.document(str(user_id)).collection("chat_history")
        history_docs = list(history_ref.order_by("created_at").limit(30).stream())
        history = [
            ChatHistoryItem(
                role=item.get("role", "assistant"),
                message=item.get("message", ""),
                created_at=datetime.fromisoformat(item.get("created_at", utc_now())),
            )
            for item in (doc.to_dict() or {} for doc in history_docs)
        ]

        return UserStateResponse(
            user=self._row_to_user(user, user_id),
            preferences=UserPreferences(
                tenant_id=prefs.get("tenant_id", self._default_tenant),
                stadium_id=prefs.get("stadium_id", self._default_stadium),
            ),
            chat_history=history,
        )

    def update_preferences(self, user_id: int, tenant_id: str, stadium_id: str) -> UserPreferences:
        user_ref = self._users.document(str(user_id))
        if not user_ref.get().exists:
            raise HTTPException(status_code=404, detail="User not found.")

        user_ref.set(
            {
                "preferences": {
                    "tenant_id": tenant_id,
                    "stadium_id": stadium_id,
                    "updated_at": utc_now(),
                }
            },
            merge=True,
        )
        return UserPreferences(tenant_id=tenant_id, stadium_id=stadium_id)

    def save_chat_exchange(self, user_id: int, question: str, answer: str) -> None:
        history_ref = self._users.document(str(user_id)).collection("chat_history")
        history_ref.add({"role": "user", "message": question, "created_at": utc_now()})
        history_ref.add({"role": "assistant", "message": answer, "created_at": utc_now()})
