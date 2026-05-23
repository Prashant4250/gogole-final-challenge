from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CROWDFLOW_", extra="ignore")

    store_backend: str = Field(default="memory")
    redis_url: str = Field(default="redis://localhost:6379/0")
    publisher_backend: str = Field(default="noop")
    pubsub_topic: str = Field(default="")
    dashboard_default_tenant: str = Field(default="league-x")
    dashboard_default_stadium: str = Field(default="stadium-1")
    auth_backend: str = Field(default="sqlite")
    auth_db_path: str = Field(default="crowdflow_auth.db")
    gcp_project_id: str = Field(default="")
    firestore_collection_prefix: str = Field(default="crowdflow")
    google_suggest_enabled: bool = Field(default=True)


settings = Settings()