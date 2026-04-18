# app/services/knowledge_service.py
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from services.tavily_service import _find_country_json

class KnowledgeService:
    @staticmethod
    @lru_cache(maxsize=64)
    def load_country(country_code: str) -> dict | None:
        path = _find_country_json(country_code)
        if path is None:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    @staticmethod
    def get_section(country_code: str, field_path: str) -> Any:
        data = KnowledgeService.load_country(country_code)
        if not data:
            return None
        node: Any = data
        for part in field_path.split("."):
            if not isinstance(node, dict):
                return None
            node = node.get(part)
            if node is None:
                return None
        return node