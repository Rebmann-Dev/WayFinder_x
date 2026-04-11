"""
safety_service.py
Application-facing wrapper around SafetyPredictor.
Handles validation, result packaging, and all new safety dimensions.
"""
from __future__ import annotations

import math
from typing import Any

from models.safety import SafetyPredictor
from models.safety.schemas import SafetyRequest, SafetyResult


class SafetyService:
    def __init__(self) -> None:
        self._predictor = SafetyPredictor()

    # ── Public API ─────────────────────────────────────────────────────────────

    def assess_location(
        self,
        latitude: float,
        longitude: float,
        country: str | None = None,
        location_name: str | None = None,
        include_details: bool = False,
        travel_date: Any = None,
    ) -> dict[str, Any]:
        error = self._validate(latitude, longitude)
        if error:
            return self._error_result(latitude, longitude, country, location_name, error)

        req = SafetyRequest(
            latitude=float(latitude),
            longitude=float(longitude),
            country=self._clean_optional_str(country),
            location_name=self._clean_optional_str(location_name),
            travel_date=travel_date,
        )
        return self.assess_request(req, include_details=include_details)

    def assess_request(
        self,
        req: SafetyRequest,
        include_details: bool = False,
    ) -> dict[str, Any]:
        error = self._validate(req.latitude, req.longitude)
        if error:
            return self._error_result(req.latitude, req.longitude, req.country, req.location_name, error)

        # Primary prediction — prefer v9b if available, else v6
        if self._predictor._v9b_available:
            pred = self._predictor.predict_v9b(req.latitude, req.longitude, req.country)
        else:
            pred = (
                self._predictor.predict_with_features(req.latitude, req.longitude, req.country)
                if include_details
                else self._predictor.predict_score(req.latitude, req.longitude, req.country)
            )

        score = float(pred["safety_score"])
        band = self._score_to_band(score)

        details: dict[str, Any] = {
            "feature_count": pred.get("feature_count"),
            "agreement_band": pred.get("agreement_band"),
            "model_spread": pred.get("model_spread"),
            "mlp_score_v6": pred.get("mlp_score_v6"),
            "rf_score_v6": pred.get("rf_score_v6"),
            "v9b_score": pred.get("safety_score") if self._predictor._v9b_available else None,
            "models_used": pred.get("models_used"),
            "input": pred.get("input"),
        }

        if include_details:
            details["features_used"] = pred.get("features_used")
            details["features"] = pred.get("features")

        # ── Additional safety dimensions ───────────────────────────────────────
        if req.include_lgbt and req.country:
            try:
                lgbt = self._predictor.predict_lgbt(req.country)
                details["lgbt_safety"] = lgbt
            except Exception:
                pass

        if req.include_weather:
            try:
                wx = self._predictor._weather.assess(
                    req.latitude, req.longitude, req.travel_date, req.country
                ) if self._predictor._weather else None
                if wx:
                    details["weather_risk"] = wx
            except Exception:
                pass

        if req.include_ecuador and self._predictor._ecuador:
            try:
                ec = self._predictor._ecuador.assess(req.latitude, req.longitude, req.country)
                details["ecuador_risk"] = ec
            except Exception:
                pass

        # Peru-specific assessment
        try:
            from models.safety.submodels.peru_safety import PeruSafetyModel
            peru_model = PeruSafetyModel()
            peru_result = peru_model.assess(
                latitude=req.latitude,
                longitude=req.longitude,
                country=req.country,
                altitude_m=0.0,
                travel_month=getattr(req, 'travel_month', None),
            )
            details["peru_risk"] = peru_result
        except Exception as e:
            details["peru_risk"] = {"applicable": False, "error": str(e)}

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

    def assess_batch(self, locations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Batch assessment for the comparison harness."""
        return [
            self.assess_location(
                latitude=float(loc["latitude"]),
                longitude=float(loc["longitude"]),
                country=loc.get("country"),
                location_name=loc.get("location_name"),
            )
            for loc in locations
        ]

    def compare_models(self, latitude: float, longitude: float, country: str | None = None) -> dict[str, Any]:
        """Expose compare_all_models for the UI harness."""
        return self._predictor.compare_all_models(latitude, longitude, country)

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _validate(self, latitude: Any, longitude: Any) -> str | None:
        try:
            lat, lon = float(latitude), float(longitude)
        except (TypeError, ValueError):
            return "latitude and longitude must be valid numbers."
        if not (math.isfinite(lat) and math.isfinite(lon)):
            return "latitude and longitude must be finite numbers."
        if not (-90 <= lat <= 90):
            return "latitude must be between -90 and 90."
        if not (-180 <= lon <= 180):
            return "longitude must be between -180 and 180."
        return None

    def _score_to_band(self, score: float) -> str:
        if score >= 75:
            return "Low Risk"
        if score >= 55:
            return "Moderate Risk"
        if score >= 35:
            return "High Risk"
        return "Very High Risk"

    def _clean_optional_str(self, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    def _is_number_like(self, v: Any) -> bool:
        try:
            float(v)
            return True
        except (TypeError, ValueError):
            return False

    def _error_result(
        self,
        lat: Any, lon: Any, country: Any, location_name: Any, error: str
    ) -> dict[str, Any]:
        result = SafetyResult(
            success=False,
            safety_score=None,
            risk_band=None,
            model_version="unknown",
            latitude=float(lat) if self._is_number_like(lat) else 0.0,
            longitude=float(lon) if self._is_number_like(lon) else 0.0,
            country=self._clean_optional_str(country),
            location_name=self._clean_optional_str(location_name),
            details={},
            error=error,
        )
        return result.to_dict()
