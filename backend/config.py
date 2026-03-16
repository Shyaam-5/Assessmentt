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

        # --- Groq AI ---
        self.GROQ_API_URL: str = "https://api.groq.com/openai/v1"
        self.GROQ_API_KEYS: list[str] = self._load_groq_keys()

        # Backward-compatible aliases used by older scripts/modules.
        self.CEREBRAS_API_URL: str = self.GROQ_API_URL
        self.CEREBRAS_API_KEYS: list[str] = self.GROQ_API_KEYS

        # --- Server ---
        self.PORT: int = int(os.getenv("PORT", "8000"))

    # ---- helpers ----
    def _load_groq_keys(self) -> list[str]:
        keys: list[str] = []
        for var in ("GROQ_API_KEY", "groq_api_key"):
            v = os.getenv(var, "")
            if v.strip():
                keys.append(v.strip())
        for i in range(1, 5):
            v = os.getenv(f"GROQ_API_KEY_{i}", "")
            if v.strip():
                keys.append(v.strip())

        # Migration fallback: allow old env names if Groq vars are missing.
        if not keys:
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
