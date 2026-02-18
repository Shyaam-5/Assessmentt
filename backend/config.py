"""Application configuration loaded from environment variables."""

import os
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application settings parsed from environment."""

    def __init__(self):
        # --- Database ---
        self.DATABASE_URL: str = os.getenv("DATABASE_URL", "")
        db = urlparse(self.DATABASE_URL)
        self.DB_HOST: str = db.hostname or "localhost"
        self.DB_PORT: int = int(db.port or 4000)
        self.DB_USER: str = db.username or "root"
        self.DB_PASSWORD: str = db.password or ""
        self.DB_NAME: str = (db.path or "/test").lstrip("/")

        # --- Cerebras AI ---
        self.CEREBRAS_API_URL: str = "https://api.cerebras.ai/v1/chat/completions"
        self.CEREBRAS_API_KEYS: list[str] = self._load_cerebras_keys()

        # --- Server ---
        self.PORT: int = int(os.getenv("PORT", "8000"))

    # ---- helpers ----
    def _load_cerebras_keys(self) -> list[str]:
        keys: list[str] = []
        for var in ("CEREBRAS_API_KEY", "cereberas_api_key"):
            v = os.getenv(var, "")
            if v.strip():
                keys.append(v.strip())
        for i in range(1, 5):
            v = os.getenv(f"CEREBRAS_API_KEY_{i}", "")
            if v.strip():
                keys.append(v.strip())
        # deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for k in keys:
            if k not in seen:
                seen.add(k)
                unique.append(k)
        return unique


settings = Settings()
