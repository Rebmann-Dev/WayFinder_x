"""OpenAI-style tool schemas for Qwen `apply_chat_template(..., tools=TOOLS)."""

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_airports",
            "description": (
                "Find IATA airport codes by city name, country, airport name, or free-text query. "
                "Use this before search_flights when the user says a place name (e.g. 'Vancouver', "
                "'Canada') instead of a 3-letter code."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search text, e.g. city name, country, or airport name.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 12).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_flights",
            "description": (
                "Search available flights between two airports for a departure date. "
                "Origin and destination must be IATA codes (3 letters, e.g. SEA, YVR). "
                "Date must be YYYY-MM-DD."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {
                        "type": "string",
                        "description": "Origin airport IATA code.",
                    },
                    "destination": {
                        "type": "string",
                        "description": "Destination airport IATA code.",
                    },
                    "departure_date": {
                        "type": "string",
                        "description": "Departure date as YYYY-MM-DD.",
                    },
                    "trip_type": {
                        "type": "string",
                        "description": 'Trip type: "oneway" or "roundtrip".',
                        "enum": ["oneway", "roundtrip"],
                    },
                    "return_date": {
                        "type": "string",
                        "description": "Return date YYYY-MM-DD if roundtrip.",
                    },
                    "max_stops": {
                        "type": "integer",
                        "description": "Max stops: -1 any, 0 nonstop, 1 one stop, 2 two stops.",
                    },
                    "max_price": {
                        "type": "number",
                        "description": "Maximum price filter, or 0 for no limit.",
                    },
                    "adults": {"type": "integer"},
                    "children": {"type": "integer"},
                },
                "required": ["origin", "destination", "departure_date"],
            },
        },
    },
]
"""
added below for saftey functions
"""

{
    "type": "function",
    "function": {
        "name": "get_safety_assessment",
        "description": (
            "Predict a travel safety score for a geographic location using latitude and longitude. "
            "Use this for questions about whether a destination, area, stop, waypoint, beach, or town may be safe."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "latitude": {
                    "type": "number",
                    "description": "Latitude of the location."
                },
                "longitude": {
                    "type": "number",
                    "description": "Longitude of the location."
                },
                "country": {
                    "type": "string",
                    "description": "Optional country name."
                },
                "location_name": {
                    "type": "string",
                    "description": "Optional human-readable location name."
                }
            },
            "required": ["latitude", "longitude"],
        },
    },
}