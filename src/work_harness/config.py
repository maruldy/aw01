from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "LangGraph Work Harness"
    app_env: str = "development"
    admin_token: str = "local-admin"

    openai_api_key: str | None = None
    openai_api_base: str | None = None
    openai_model: str = "gpt-4o-mini"

    jira_base_url: str | None = None
    jira_api_token: str | None = None
    jira_username: str | None = None
    jira_projects: str = ""

    confluence_url: str | None = None
    confluence_api_token: str | None = None
    confluence_spaces: str = ""

    slack_bot_token: str | None = None
    slack_user_token: str | None = None
    slack_my_user_id: str | None = None
    slack_signing_secret: str | None = None

    github_base_url: str = "https://api.github.com"
    github_token: str | None = None
    github_repository: str | None = None
    github_webhook_secret: str | None = None

    webhook_base_url: str = "http://localhost:8000"
    jira_webhook_shared_secret: str | None = None
    confluence_webhook_secret: str | None = None

    knowledge_db_path: Path = Field(default=Path("./data/work_harness.db"))
    knowledge_chroma_path: Path = Field(default=Path("./data/chroma"))
    managed_workspace_root: Path = Field(default=Path("./.workspaces"))

    auto_backfill: bool = False
    backfill_months_back: int = 6

    daily_delta_scan_hour: int = 3
    weekly_digest_day: str = "mon"
    weekly_digest_hour: int = 9
