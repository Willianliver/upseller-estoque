"""Configuração lida de variáveis de ambiente (.env). Nunca loga credenciais."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    base_url: str = field(default_factory=lambda: os.getenv("UPSELLER_BASE_URL", "https://openapi.upseller.com"))
    client_id: str = field(default_factory=lambda: os.getenv("UPSELLER_CLIENT_ID", ""))
    api_token: str = field(default_factory=lambda: os.getenv("UPSELLER_API_TOKEN", ""), repr=False)
    language: str = field(default_factory=lambda: os.getenv("UPSELLER_LANGUAGE", "pt"))
    rate_limit_per_minute: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "60")))
    db_path: Path = field(default_factory=lambda: ROOT / os.getenv("DB_PATH", "data/estoque.db"))

    def validate(self) -> None:
        missing = [n for n, v in (("UPSELLER_CLIENT_ID", self.client_id), ("UPSELLER_API_TOKEN", self.api_token)) if not v]
        if missing:
            raise RuntimeError(f"Variáveis ausentes no .env: {', '.join(missing)}")
