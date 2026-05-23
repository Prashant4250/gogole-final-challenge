from __future__ import annotations

import re
from typing import Iterable

import httpx

from app.config import settings

GOOGLE_SUGGEST_URL = "https://suggestqueries.google.com/complete/search"
DEFAULT_TIMEOUT_SECONDS = 2.5


class DiscoveryService:
    def __init__(self) -> None:
        self._default_tenant = settings.dashboard_default_tenant
        self._default_stadium = settings.dashboard_default_stadium

    def suggestions(
        self,
        *,
        kind: str,
        query: str,
        active_pairs: Iterable[tuple[str, str]],
        tenant_id: str | None = None,
        limit: int = 8,
    ) -> list[dict[str, str]]:
        cleaned_query = query.strip()
        local_items = self._local_suggestions(kind, cleaned_query, active_pairs, tenant_id)
        items_by_value: dict[str, dict[str, str]] = {item["value"]: item for item in local_items}

        if settings.google_suggest_enabled and cleaned_query:
            google_items = self._google_suggestions(kind, cleaned_query)
            for item in google_items:
                if item["value"] not in items_by_value:
                    items_by_value[item["value"]] = item

        return list(items_by_value.values())[: max(1, limit)]

    def _local_suggestions(
        self,
        kind: str,
        query: str,
        active_pairs: Iterable[tuple[str, str]],
        tenant_id: str | None,
    ) -> list[dict[str, str]]:
        normalized_query = query.lower()
        values: set[str] = set()

        if kind == "tenant":
            values.add(self._default_tenant)
            for active_tenant, _ in active_pairs:
                values.add(active_tenant)
        else:
            values.add(self._default_stadium)
            for active_tenant, active_stadium in active_pairs:
                if tenant_id and active_tenant != tenant_id:
                    continue
                values.add(active_stadium)

        result: list[dict[str, str]] = []
        for value in sorted(values):
            if normalized_query and normalized_query not in value.lower():
                continue
            result.append(
                {
                    "label": value,
                    "value": value,
                    "source": "local",
                }
            )
        return result

    def _google_suggestions(self, kind: str, query: str) -> list[dict[str, str]]:
        google_query = (
            f"{query} sports league tenant"
            if kind == "tenant"
            else f"{query} stadium venue"
        )
        try:
            response = httpx.get(
                GOOGLE_SUGGEST_URL,
                params={
                    "client": "firefox",
                    "q": google_query,
                },
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return []

        if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[1], list):
            return []

        items: list[dict[str, str]] = []
        for suggestion in payload[1]:
            if not isinstance(suggestion, str):
                continue
            value = self._normalize_google_suggestion(suggestion, kind)
            if not value:
                continue
            if not self._is_reasonable_suggestion(value):
                continue
            items.append(
                {
                    "label": suggestion,
                    "value": value,
                    "source": "google",
                }
            )
        return items

    def _normalize_google_suggestion(self, suggestion: str, kind: str) -> str:
        cleaned = suggestion.strip()
        if not cleaned:
            return ""

        if kind == "stadium":
            cleaned = re.sub(r"\s+stadium\s*$", "", cleaned, flags=re.IGNORECASE)

        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned

    def _is_reasonable_suggestion(self, value: str) -> bool:
        stripped = value.lstrip()
        if any(ord(char) < 32 for char in value):
            return False
        if len(value) > 120:
            return False
        if stripped.startswith(("=", "+", "-")):
            return False
        if re.match(r"^[=+\-]\s*\d", stripped):
            return False
        return True
