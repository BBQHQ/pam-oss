"""PAM configuration — environment-driven, cross-platform.

Values are read from a `.env` file in the project root or from process env vars.
Every value has a sensible default so PAM boots cleanly out of the box.
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

PAM_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PAM_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ─── Core ────────────────────────────────────
    pam_host: str = "0.0.0.0"
    pam_port: int = 8400
    pam_data_dir: Path = PAM_ROOT / "data"

    # ─── SSL (auto-generated on first boot if missing) ───
    ssl_cert_file: Path = PAM_ROOT / "certs" / "cert.pem"
    ssl_key_file: Path = PAM_ROOT / "certs" / "key.pem"
    ssl_auto_generate: bool = True

    # ─── Whisper ─────────────────────────────────
    whisper_dir: Path = PAM_ROOT / "whisper"
    whisper_model: str = "ggml-large-v3-turbo-q5_0.bin"
    whisper_backend: str = "auto"  # auto | cuda | metal | cpu | python
    whisper_host: str = "127.0.0.1"
    whisper_port: int = 8178
    whisper_threads: int = 4
    whisper_ttl_seconds: int = 300  # kill idle server after 5 min

    # ─── External binaries ───────────────────────
    claude_bin: str = "claude"
    gh_bin: str = "gh"

    # ─── Scheduling defaults (overridable via /settings) ───
    default_timezone: str = "America/New_York"
    default_briefing_hour: int = 7
    default_checkin_hour: int = 13
    default_habit_reset_hour: int = 4

    # ─── Optional integrations ───────────────────
    user_email: str = ""
    email_credentials_file: Path = PAM_ROOT / "data" / "email_credentials.json"
    google_credentials_file: Path = PAM_ROOT / "data" / "google_credentials.json"
    google_token_file: Path = PAM_ROOT / "data" / "google_token.json"

    # ─── GitHub owner for briefing commits section (optional) ───
    github_owner: str = ""

    # ─── Seed starter data on first boot ─────────
    seed_starter_data: bool = True


settings = Settings()

# ─── Backwards-compatible module-level exports ────
# Many services reference these constants directly. Keep the names stable.
PAM_HOST = settings.pam_host
PAM_PORT = settings.pam_port
DATA_DIR = settings.pam_data_dir
STAGING_DIR = DATA_DIR / "staging"

WHISPER_DIR = settings.whisper_dir / "Release"
WHISPER_SERVER_EXE = settings.whisper_dir / ("whisper-server.exe" if Path(WHISPER_DIR).drive else "whisper-server")
# Resolve the whisper server binary name cross-platform
import sys as _sys
WHISPER_SERVER_EXE = settings.whisper_dir / ("whisper-server.exe" if _sys.platform == "win32" else "whisper-server")
WHISPER_MODEL_PATH = settings.whisper_dir / "models" / settings.whisper_model
WHISPER_HOST = settings.whisper_host
WHISPER_PORT = settings.whisper_port
WHISPER_THREADS = settings.whisper_threads
WHISPER_TTL_SECONDS = settings.whisper_ttl_seconds

EMAIL_CREDENTIALS_FILE = settings.email_credentials_file
BRIEFING_HOUR = settings.default_briefing_hour
CHECKIN_HOUR = settings.default_checkin_hour

GOOGLE_CREDENTIALS_FILE = settings.google_credentials_file
GOOGLE_TOKEN_FILE = settings.google_token_file
CALENDAR_TIMEZONE = settings.default_timezone
USER_EMAIL = settings.user_email

CLAUDE_BIN = settings.claude_bin
GH_BIN = settings.gh_bin
GITHUB_OWNER = settings.github_owner

# Ensure data + staging dirs exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
STAGING_DIR.mkdir(parents=True, exist_ok=True)
