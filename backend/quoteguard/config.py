"""Application configuration, loaded once from the environment (.env locally).

Secrets never leave this module except to the adapters that need them; the
`readiness()` helper reports only booleans and non-secret identifiers.
"""

from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(str, Enum):
    local = "local"
    test = "test"
    hosted = "hosted"


class PayPalMode(str, Enum):
    # Live mode is intentionally absent: this deliverable cannot move real money.
    sandbox = "sandbox"


def _env_file() -> str | None:
    explicit = os.environ.get("QUOTEGUARD_ENV_FILE")
    if explicit:
        return explicit
    for candidate in (Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"):
        if candidate.exists():
            return str(candidate)
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_env_file(), extra="ignore", case_sensitive=True)

    APP_ENV: AppEnv = AppEnv.local
    APP_BASE_URL: str = "http://localhost:5173"
    API_BASE_URL: str = "http://localhost:8250"
    DATABASE_URL: str = "postgresql+psycopg://quoteguard:quoteguard@localhost:5443/quoteguard_dev"
    SESSION_SECRET: str = ""
    APPROVAL_SIGNING_SECRET: str = ""
    CORS_ALLOWED_ORIGINS: str = "http://localhost:5173"
    DEFAULT_TIMEZONE: str = "Asia/Kolkata"
    STORAGE_PATH: str = "./storage"
    MAX_UPLOAD_MB: int = 10
    MAX_PDF_PAGES: int = 20

    AI_PROVIDER: str = "none"  # gemini | openai | openrouter | none
    AI_BASE_URL: str = ""
    AI_API_KEY: str = ""  # comma-separated keys are rotated on rate limits
    AI_MODEL: str = ""
    AI_TIMEOUT_SECONDS: float = 45
    AI_MAX_TOKENS: int = 4000
    AI_MAX_CALLS_PER_REQUEST: int = 24

    OCR_PROVIDER: str = ""
    OCR_API_KEY: str = ""
    OCR_MODEL: str = ""

    PAYPAL_MODE: PayPalMode = PayPalMode.sandbox
    PAYPAL_CLIENT_ID: str = ""
    PAYPAL_CLIENT_SECRET: str = ""
    PAYPAL_MERCHANT_ID: str = ""
    PAYPAL_WEBHOOK_ID: str = ""
    PAYMENT_CURRENCY: str = "USD"
    PAYPAL_TIMEOUT_SECONDS: float = 20

    APPROVAL_TTL_MINUTES: int = 60
    SESSION_TTL_HOURS: int = 12

    DEMO_MODE: bool = True
    DEMO_LAB_ENABLED: bool = True
    DEMO_ACCOUNT_USERNAME: str = ""
    DEMO_ACCOUNT_PASSWORD: str = ""
    DEMO_REQUESTER_EMAIL: str = ""
    DEMO_REQUESTER_PASSWORD: str = ""
    DEMO_APPROVER_EMAIL: str = ""
    DEMO_APPROVER_PASSWORD: str = ""
    ADMIN_EMAIL: str = ""
    ADMIN_PASSWORD: str = ""

    # Shown on the login page so judges can sign in; demo accounts only ever reach isolated demo workspaces.
    SHOW_JURY_LOGIN: bool = False
    # Optional PayPal *sandbox* buyer test account shown on the checkout screen (sandbox only, no real money).
    SANDBOX_BUYER_EMAIL: str = ""
    SANDBOX_BUYER_PASSWORD: str = ""

    MOCK_AI: bool = False
    MOCK_PAYPAL: bool = False

    LOG_LEVEL: str = "INFO"
    AG_GRID_LICENSE_KEY: str = ""
    CODE_REVISION: str = ""

    cookie_secure: bool = Field(default=False, alias="COOKIE_SECURE")

    @field_validator("PAYPAL_MODE", mode="before")
    @classmethod
    def _sandbox_only(cls, v: str) -> str:
        if str(v).lower() != "sandbox":
            raise ValueError("PAYPAL_MODE must be 'sandbox'; live mode is disabled in this deliverable")
        return "sandbox"

    @model_validator(mode="after")
    def _validate(self) -> "Settings":
        if self.APP_ENV == AppEnv.hosted:
            for name in ("SESSION_SECRET", "APPROVAL_SIGNING_SECRET"):
                if len(getattr(self, name)) < 32:
                    raise ValueError(f"{name} must be at least 32 characters in hosted mode")
            if self.SESSION_SECRET == self.APPROVAL_SIGNING_SECRET:
                raise ValueError("SESSION_SECRET and APPROVAL_SIGNING_SECRET must differ")
        if not self.SESSION_SECRET:
            self.SESSION_SECRET = "dev-session-secret-not-for-hosting-0000000000"
        if not self.APPROVAL_SIGNING_SECRET:
            self.APPROVAL_SIGNING_SECRET = "dev-approval-secret-not-for-hosting-111111111"
        return self

    # ---- derived, non-secret views -------------------------------------------------
    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def ai_keys(self) -> list[str]:
        return [k.strip() for k in self.AI_API_KEY.split(",") if k.strip()]

    @property
    def ai_configured(self) -> bool:
        return self.MOCK_AI or (self.AI_PROVIDER != "none" and bool(self.ai_keys) and bool(self.AI_MODEL) and bool(self.AI_BASE_URL))

    @property
    def paypal_credentials_present(self) -> bool:
        return bool(self.PAYPAL_CLIENT_ID and self.PAYPAL_CLIENT_SECRET)

    @property
    def paypal_adapter_kind(self) -> str:
        """Which payment adapter executes checkout.

        A requested real integration never silently falls back to the simulator:
        with MOCK_PAYPAL=false and no credentials, checkout is unavailable.
        """
        if self.MOCK_PAYPAL:
            return "simulated"
        return "sandbox" if self.paypal_credentials_present else "unconfigured"

    @property
    def paypal_api_base(self) -> str:
        return {PayPalMode.sandbox: "https://api-m.sandbox.paypal.com"}[self.PAYPAL_MODE]

    @property
    def storage_dir(self) -> Path:
        return Path(self.STORAGE_PATH).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()


def readiness(db_ok: bool) -> dict:
    s = get_settings()
    kind = s.paypal_adapter_kind
    return {
        "database": "connected" if db_ok else "unavailable",
        "app_env": s.APP_ENV.value,
        "ai": {
            "configured": s.ai_configured,
            "provider": "mock" if s.MOCK_AI else s.AI_PROVIDER,
            "model": "mock" if s.MOCK_AI else (s.AI_MODEL or None),
            "keys_loaded": len(s.ai_keys),
        },
        "ocr": {"configured": bool(s.OCR_PROVIDER), "provider": s.OCR_PROVIDER or None},
        "paypal": {
            "mode": s.PAYPAL_MODE.value,
            "adapter": kind,
            "credentials_present": s.paypal_credentials_present,
            "merchant_id_configured": bool(s.PAYPAL_MERCHANT_ID),
            "webhook_configured": bool(s.PAYPAL_WEBHOOK_ID),
            "live_mode_available": False,
            "currency": s.PAYMENT_CURRENCY,
        },
        "demo": {"demo_mode": s.DEMO_MODE, "demo_lab_enabled": s.DEMO_LAB_ENABLED},
        "limits": {"max_upload_mb": s.MAX_UPLOAD_MB, "max_pdf_pages": s.MAX_PDF_PAGES, "approval_ttl_minutes": s.APPROVAL_TTL_MINUTES},
        "timezone": s.DEFAULT_TIMEZONE,
    }
