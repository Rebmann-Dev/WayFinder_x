"""
WayFinder — Location Picker API
FastAPI backend for coordinate capture and prediction routing.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional, Any
import os
import sys
import torch
import numpy as np
import logging
from pathlib import Path

# ── Add models package to path ─────────────────────────────────────────────────
_MODELS_DIR = Path(__file__).resolve().parents[3] / "models" / "safety"
sys.path.insert(0, str(_MODELS_DIR.parent.parent))  # puts app/ on path

from app.models.safety.predictor import SafetyPredictor

logger = logging.getLogger(__name__)

app = FastAPI(
    title="WayFinder Location Picker",
    description="Location capture API — milestone 1 of WayFinder safety prediction pipeline.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:3000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Load predictor once at startup ─────────────────────────────────────────────
_predictor: Optional[SafetyPredictor] = None

@app.on_event("startup")
def load_predictor():
    global _predictor
    try:
        _predictor = SafetyPredictor()
        logger.info("SafetyPredictor loaded. v9b available: %s", _predictor._v9b_available)
    except Exception as e:
        logger.error("Failed to load SafetyPredictor: %s", e)
        _predictor = None
##### added above this 4/14 -- trying to combat the lat lon out of bounds & location picker reverting to SA country
app = FastAPI(
    title="WayFinder Location Picker",
    description="Location capture API — milestone 1 of WayFinder safety prediction pipeline.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:3000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


class CoordinatesRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90, description="Latitude")
    lon: float = Field(..., ge=-180, le=180, description="Longitude")
    place_name: Optional[str] = Field(None, description="Full display label from reverse geocoder")
    country: Optional[str] = Field(None, description="Country name")
    country_code: Optional[str] = Field(None, description="ISO-like country code from geocoder")
    state_region: Optional[str] = Field(None, description="State, province, or region")
    county: Optional[str] = Field(None, description="County or district")
    city: Optional[str] = Field(None, description="City, town, village, or municipality")
    postcode: Optional[str] = Field(None, description="Postal code")
    location_source: Optional[str] = Field(None, description="map_click, search, or other origin")


class CoordinatesResponse(BaseModel):
    lat: float
    lon: float
    place_name: Optional[str]
    country: Optional[str]
    country_code: Optional[str]
    state_region: Optional[str]
    county: Optional[str]
    city: Optional[str]
    postcode: Optional[str]
    location_source: Optional[str]
    status: str
    message: str


class PredictionResponse(BaseModel):
    lat: float
    lon: float
    place_name: Optional[str]
    country: Optional[str]
    country_code: Optional[str]
    state_region: Optional[str]
    county: Optional[str]
    city: Optional[str]
    postcode: Optional[str]
    location_source: Optional[str]
    safety_score: Optional[float]
    status: str
    message: str


@app.get("/health")
def health():
    return {"status": "ok", "service": "wayfinder-location-picker"}


@app.post("/api/v1/coordinates/echo", response_model=CoordinatesResponse)
def echo_coordinates(payload: CoordinatesRequest):
    return CoordinatesResponse(
        lat=payload.lat,
        lon=payload.lon,
        place_name=payload.place_name,
        country=payload.country,
        country_code=payload.country_code,
        state_region=payload.state_region,
        county=payload.county,
        city=payload.city,
        postcode=payload.postcode,
        location_source=payload.location_source,
        status="received",
        message=f"Coordinates received: ({payload.lat:.5f}, {payload.lon:.5f})",
    )

##### replaced this 4/14 -- trying to combat the lat lon out of bounds & location picker reverting to SA country
@app.post("/api/v1/predict", response_model=PredictionResponse)
def predict_safety(payload: CoordinatesRequest):
    if _predictor is None:
        return PredictionResponse(
            **payload.model_dump(),
            safety_score=None,
            status="error",
            message="Predictor not loaded — check server logs.",
        )

    try:
        result = _predictor.predict_full(
            latitude=payload.lat,
            longitude=payload.lon,
            country=payload.country,          # passes country name string
        )
        score = result.get("safety_score")
        model_ver = result.get("model_version", "unknown")
        return PredictionResponse(
            **payload.model_dump(),
            safety_score=round(score, 4) if score is not None else None,
            status="ok",
            message=f"[{model_ver}] Safety score for ({payload.lat:.4f}, {payload.lon:.4f}): {score:.2f}" if score else "Score unavailable.",
        )
    except Exception as e:
        logger.exception("predict_safety error")
        return PredictionResponse(
            **payload.model_dump(),
            safety_score=None,
            status="error",
            message=str(e),
        )


_frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(_frontend_dir):
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")