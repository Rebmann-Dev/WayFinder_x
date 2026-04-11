"""
schemas.py
Typed request/response schemas for WayFinder safety prediction.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SafetyRequest:
    latitude: float
    longitude: float
    country: str | None = None
    location_name: str | None = None
    travel_date: datetime.date | None = None
    include_lgbt: bool = True
    include_weather: bool = True
    include_ecuador: bool = True


@dataclass
class LGBTSafetyDimension:
    score: int                  # 1-5
    label: str
    legal_index: float | None
    confidence: str             # "high", "medium", "low"
    criminalized: bool
    death_penalty_risk: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "lgbt_safety_score": self.score,
            "lgbt_safety_label": self.label,
            "lgbt_legal_index": self.legal_index,
            "lgbt_confidence": self.confidence,
            "criminalized": self.criminalized,
            "death_penalty_risk": self.death_penalty_risk,
        }


@dataclass
class WeatherRiskDimension:
    score: int                  # 1-5
    label: str
    risks: list[dict[str, Any]]
    travel_month_assessment: str | None
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "weather_risk_score": self.score,
            "weather_risk_label": self.label,
            "weather_risks": self.risks,
            "travel_month_assessment": self.travel_month_assessment,
            "weather_source": self.source,
        }


@dataclass
class EcuadorRiskDimension:
    overall_risk: int           # 1-5
    wildlife_risk: int
    crime_risk: int
    province: str | None
    wildlife_threats: list[str]
    crime_notes: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ecuador_overall_risk": self.overall_risk,
            "ecuador_wildlife_risk": self.wildlife_risk,
            "ecuador_crime_risk": self.crime_risk,
            "province": self.province,
            "wildlife_threats": self.wildlife_threats,
            "crime_notes": self.crime_notes,
        }


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
    lgbt_dimension: LGBTSafetyDimension | None = None
    weather_dimension: WeatherRiskDimension | None = None
    ecuador_dimension: EcuadorRiskDimension | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
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
        if self.lgbt_dimension:
            d["lgbt_safety"] = self.lgbt_dimension.to_dict()
        if self.weather_dimension:
            d["weather_risk"] = self.weather_dimension.to_dict()
        if self.ecuador_dimension:
            d["ecuador_risk"] = self.ecuador_dimension.to_dict()
        return d
