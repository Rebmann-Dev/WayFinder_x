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
    {
        "type": "function",
        "function": {
            "name": "get_safety_assessment",
            "description": (
                "Predict a travel safety score for a city or location. "
                "Pass the city or place name as location_name — no coordinates required. "
                "Use this whenever the user asks about safety, crime, or risk level for any destination, city, or country."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "location_name": {
                        "type": "string",
                        "description": "City or place name, e.g. 'Los Angeles', 'Bangkok', 'Paris'.",
                    },
                    "country": {
                        "type": "string",
                        "description": "Country name to improve accuracy, e.g. 'United States', 'Thailand'.",
                    },
                    "latitude": {
                        "type": "number",
                        "description": "Latitude — only provide if you already have exact coordinates.",
                    },
                    "longitude": {
                        "type": "number",
                        "description": "Longitude — only provide if you already have exact coordinates.",
                    },
                },
                "required": ["location_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": (
                "Search the web for up-to-date information on travel logistics, "
                "such as visa entry requirements, top hiking trails, regional foods, "
                "budget guidelines, or customs and etiquette."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query formulation.",
                    },
                    "country_code": {
                        "type": "string",
                        "description": "Optional 2-letter ISO country code to retrieve/save local cached info.",
                    },
                },
                "required": ["query"],
            },
        },
    },
]
