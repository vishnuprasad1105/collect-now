from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def _resolve_sqlite_path(url: str | None) -> str | None:
    if not url:
        return None
    prefix = "sqlite:///"
    if url.startswith(prefix) and not url.startswith("sqlite:////"):
        relative_path = url[len(prefix):]
        absolute_path = (BASE_DIR / relative_path).resolve()
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{absolute_path}"
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", str(BASE_DIR / "uploads"))
    RESOURCE_FOLDER = os.environ.get("RESOURCE_FOLDER", str(BASE_DIR / "resources"))
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 16 * 1024 * 1024))  # 16 MB
    _default_db_path = (BASE_DIR / "instance" / "collectnow.sqlite")
    _default_db_path.parent.mkdir(parents=True, exist_ok=True)
    SQLALCHEMY_DATABASE_URI = _resolve_sqlite_path(
        os.environ.get("DATABASE_URL")
    ) or f"sqlite:///{_default_db_path.resolve()}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    KB_MATCH_THRESHOLD = int(os.environ.get("KB_MATCH_THRESHOLD", 78))
    KB_AI_CANDIDATES = int(os.environ.get("KB_AI_CANDIDATES", 25))
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    KB_OPENAI_MODEL = os.environ.get("KB_OPENAI_MODEL", "gpt-4o-mini")
