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

        # --- Groq AI (for environment scan) ---
        self.GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
        self.GROQ_MODEL: str = os.getenv("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
        self.GROQ_FALLBACK_MODEL: str = os.getenv("GROQ_FALLBACK_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

        # --- Server ---
        self.PORT: int = int(os.getenv("PORT", "8000"))
        self.SERVER_LAN_IP: str = os.getenv("SERVER_LAN_IP", "localhost")
        self.FRONTEND_URL: str = os.getenv("FRONTEND_URL", "")

        # --- Environment Scan (prescan) settings ---
        self.PRESCAN_SECRET_KEY: str = os.getenv("PRESCAN_SECRET_KEY", os.getenv("SECRET_KEY", "change-me-prescan-secret-key"))
        self.FRAME_INTERVAL_MS: int = int(os.getenv("FRAME_INTERVAL_MS", "1500"))
        self.MIN_FRAMES_PER_ANGLE: int = int(os.getenv("MIN_FRAMES_PER_ANGLE", "5"))
        self.MAX_SCAN_DURATION_S: int = int(os.getenv("MAX_SCAN_DURATION_S", "180"))
        self.MIN_TOTAL_FRAMES: int = int(os.getenv("MIN_TOTAL_FRAMES", "20"))
        self.MIN_SCAN_DURATION_S: int = int(os.getenv("MIN_SCAN_DURATION_S", "30"))

    def get_mobile_scan_url(self, session_token: str) -> str:
        """Return the frontend URL for mobile scan."""
        base = self.FRONTEND_URL.rstrip("/") if self.FRONTEND_URL else f"http://{self.SERVER_LAN_IP}:{self.PORT}"
        return f"{base}/scan/mobile?token={session_token}"

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
