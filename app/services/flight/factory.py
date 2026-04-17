from __future__ import annotations

from core.config import settings

from .base import FlightProvider
from .disabled import DisabledFlightProvider
from .docker_scraper import DockerScraperFlightProvider
from .stub import StubFlightProvider


def get_flight_provider() -> FlightProvider:
    mode = getattr(settings, "flight_scraper_mode", "off")

    if mode == "live":
        return DockerScraperFlightProvider()
    if mode == "stub":
        return StubFlightProvider()

    return DisabledFlightProvider()
