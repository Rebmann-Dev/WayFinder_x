from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

_FEATURES_PATH = Path(__file__).resolve().parents[2] / "config" / "features.json"


@dataclass
class Settings:
    # ── LLM ──────────────────────────────────────────────────────────────────
    app_title: str = "WayFinder: Your Travel Planning Assistant"
    model_name: str = "Qwen/Qwen2.5-1.5B-Instruct"
    max_new_tokens: int = 200
    agent_max_new_tokens: int = 512
    agent_max_steps: int = 6
    agent_temperature: float = 0.3

    # ── Feature flags ────────────────────────────────────────────────────────
    # Flight scraper: "off" | "stub" | "live"
    flight_scraper_mode: Literal["off", "stub", "live"] = "off"
    # Knowledge base version: "v1" (monolith JSONs) | "v2" (split + index)
    knowledge_base_version: Literal["v1", "v2"] = "v1"
    # Input pipeline: enables spell-check / NER / clarification layer
    input_pipeline_enabled: bool = False
    # Mobile API: enables FastAPI server alongside Streamlit
    mobile_api_enabled: bool = False
    # Memory logging: logs all queries to data/memory/
    memory_logging_enabled: bool = True

    def __post_init__(self) -> None:
        """Override defaults with values from config/features.json if present."""
        if _FEATURES_PATH.exists():
            try:
                overrides = json.loads(_FEATURES_PATH.read_text())
                for key, value in overrides.items():
                    if hasattr(self, key):
                        object.__setattr__(self, key, value)
            except Exception:
                pass  # never crash on bad features.json


settings = Settings()
