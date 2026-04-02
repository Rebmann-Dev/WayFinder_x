from dataclasses import dataclass
from typing import Any

@dataclass
class SafetyRequest:
    latitude: float
    longitude: float
    country: str | None = None
    location_name: str | None = None

@dataclass
class SafetyResult:
    success: bool
    safety_score: float | None
    risk_band: str | None
    model_version: str
    latitude: float
    longitude: float
    country: str | None
    location_name: str | None
    details: dict[str, Any]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "safety_score": self.safety_score,
            "risk_band": self.risk_band,
            "model_version": self.model_version,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "country": self.country,
            "location_name": self.location_name,
            "details": self.details,
            "error": self.error,
        }