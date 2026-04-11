from models.safety.predictor import SafetyPredictor

class SafetyService:
    def __init__(self) -> None:
        self._predictor = SafetyPredictor()

    def assess_location(
        self,
        latitude: float,
        longitude: float,
        country: str | None = None,
        location_name: str | None = None,
    ) -> dict:
        pred = self._predictor.predict(
            latitude=latitude,
            longitude=longitude,
            country=country,
        )

        score = float(pred["safety_score"])

        if score >= 70:
            risk_band = "low"
        elif score >= 50:
            risk_band = "moderate"
        elif score >= 35:
            risk_band = "elevated"
        else:
            risk_band = "high"

        return {
            "success": True,
            "location_name": location_name,
            "latitude": latitude,
            "longitude": longitude,
            "country": country,
            "safety_score": round(score, 2),
            "risk_band": risk_band,
            "model_version": pred["model_version"],
        }