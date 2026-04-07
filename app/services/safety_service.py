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
        include_details: bool = False,
    ) -> dict[str, Any]:
        error = self._validate(latitude, longitude)
        if error:
            result = SafetyResult(
                success=False,
                safety_score=None,
                risk_band=None,
                model_version="v6",
                latitude=float(latitude) if self._is_number_like(latitude) else latitude,
                longitude=float(longitude) if self._is_number_like(longitude) else longitude,
                country=self._clean_optional_str(country),
                location_name=self._clean_optional_str(location_name),
                details={},
                error=error,
            )
            return result.to_dict()

        req = SafetyRequest(
            latitude=float(latitude),
            longitude=float(longitude),
            country=self._clean_optional_str(country),
            location_name=self._clean_optional_str(location_name),
        )

        return self.assess_request(req, include_details=include_details)

    def assess_request(
        self,
        req: SafetyRequest,
        include_details: bool = False,
    ) -> dict[str, Any]:
        error = self._validate(req.latitude, req.longitude)
        if error:
            result = SafetyResult(
                success=False,
                safety_score=None,
                risk_band=None,
                model_version="v6",
                latitude=req.latitude,
                longitude=req.longitude,
                country=req.country,
                location_name=req.location_name,
                details={},
                error=error,
            )
            return result.to_dict()

        pred = (
            self._predictor.predict_with_features(
                latitude=req.latitude,
                longitude=req.longitude,
                country=req.country,
            )
            if include_details
            else self._predictor.predict_score(
                latitude=req.latitude,
                longitude=req.longitude,
                country=req.country,
            )
        )

        score = float(pred["safety_score"])
        band = self._score_to_band(score)

        details: dict[str, Any] = {
            "feature_count": pred.get("feature_count"),
            "agreement_band": pred.get("agreement_band"),
            "model_spread": pred.get("model_spread"),
            "mlp_score_v6": pred.get("mlp_score_v6"),
            "rf_score_v6": pred.get("rf_score_v6"),
            "models_used": pred.get("models_used"),
            "input": pred.get("input"),
        }

        if include_details:
            details["features_used"] = pred.get("features_used")
            details["features"] = pred.get("features")

        result = SafetyResult(
            success=True,
            safety_score=round(score, 2),
            risk_band=band,
            model_version=str(pred.get("model_version", "v6")),
            latitude=req.latitude,
            longitude=req.longitude,
            country=req.country,
            location_name=req.location_name,
            details=details,
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

    def _clean_optional_str(self, value: Any) -> str | None:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return None

    def _is_number_like(self, value: Any) -> bool:
        try:
            float(value)
            return True
        except (TypeError, ValueError):
            return False