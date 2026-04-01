from __future__ import annotations

import math
from typing import Any

from models.safety import SafetyPredictor, SafetyRequest, SafetyResult


class SafetyService:
    def __init__(self) -> None:
        self._predictor = SafetyPredictor()

    def assess_location(
        self,
        latitude: float,
        longitude: float,
        country: str | None = None,
        location_name: str | None = None,
    ) -> dict[str, Any]:
        error = self._validate(latitude, longitude)
        if error:
            result = SafetyResult(
                success=False,
                safety_score=None,
                risk_band=None,
                model_version="v6",
                latitude=latitude,
                longitude=longitude,
                country=country,
                location_name=location_name,
                details={},
                error=error,
            )
            return result.to_dict()

        req = SafetyRequest(
            latitude=float(latitude),
            longitude=float(longitude),
            country=country.strip() if isinstance(country, str) and country.strip() else None,
            location_name=location_name.strip() if isinstance(location_name, str) and location_name.strip() else None,
        )

        pred = self._predictor.predict_score(
            latitude=req.latitude,
            longitude=req.longitude,
            country=req.country,
        )

        score = float(pred["safety_score"])
        band = self._score_to_band(score)

        result = SafetyResult(
            success=True,
            safety_score=round(score, 2),
            risk_band=band,
            model_version=str(pred.get("model_version", "v6")),
            latitude=req.latitude,
            longitude=req.longitude,
            country=req.country,
            location_name=req.location_name,
            details={
                "feature_count": pred.get("feature_count"),
            },
            error=None,
        )
        return result.to_dict()

    def _validate(self, latitude: float, longitude: float) -> str | None:
        try:
            lat = float(latitude)
            lon = float(longitude)
        except (TypeError, ValueError):
            return "latitude and longitude must be valid numbers."

        if not math.isfinite(lat) or not math.isfinite(lon):
            return "latitude and longitude must be finite numbers."
        if lat < -90 or lat > 90:
            return "latitude must be between -90 and 90."
        if lon < -180 or lon > 180:
            return "longitude must be between -180 and 180."

        return None

    def _score_to_band(self, score: float) -> str:
        if score >= 75:
            return "low"
        if score >= 55:
            return "moderate"
        if score >= 35:
            return "elevated"
        return "high"