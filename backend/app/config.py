"""Application configuration, read from environment variables (prefix LPR_).

On an installed server these live in /etc/lpr-importer/lpr-importer.env.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LPR_", env_file=None)

    database_url: str = "postgresql+psycopg://lprimporter@/lprimporter"
    secret_key: str = "change-me"
    # Public URL of the app, used for SSO redirects and links in mail.
    base_url: str = "http://localhost:8080"
    cookie_secure: bool = False
    session_hours: int = 12

    repo_dir: Path = REPO_ROOT
    state_dir: Path = Path("/var/lib/lpr-importer")
    frontend_dist: Path = REPO_ROOT / "frontend" / "dist"
    # Command that starts the privileged update unit; overridable for tests.
    update_command: str = "sudo -n /usr/bin/systemctl start --no-block lpr-importer-update.service"
    # Fake UniFi Access consoles for development and demos: "" (off), "empty" or "demo".
    access_mock: str = ""
    # Run background jobs in the request instead of a thread (tests).
    jobs_inline: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
