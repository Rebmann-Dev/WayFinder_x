# WayFinder Location Picker

A portable FastAPI + Leaflet mini app for selecting a point on a world map and capturing latitude/longitude.

## Features
- Interactive Leaflet world map
- Click anywhere to drop a marker
- Latitude/longitude shown immediately in the UI
- Coordinates stored in frontend app state
- Optional place search via Nominatim
- FastAPI backend echo endpoint for integration path
- Stub predictor endpoint for future replacement
- Self-contained portable folder

## Project Structure

```text
location-picker/
├── README.md
├── api/
│   ├── main.py
│   └── requirements.txt
└── frontend/
    ├── index.html
    └── static/
        ├── app.js
        └── style.css
```

## Setup

```bash
cd api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..
uvicorn api.main:app --reload --port 8000
```

Open:
- http://localhost:8000

## Alternate frontend-only dev mode

```bash
cd frontend
python3 -m http.server 8080
```

And in another terminal:

```bash
cd location-picker
source api/.venv/bin/activate
uvicorn api.main:app --reload --port 8000
```

Open:
- http://localhost:8080

## Smoke test
- Open the app
- Click on the map
- Confirm marker appears
- Confirm lat/lon appear in sidebar
- Click Confirm Location
- Confirm echoed JSON appears
- Try search box
- Try Clear

## Future integration
Recommended destination later:

```text
WayFinder/agents/location-picker/
```

Replace `/api/v1/predict` with your model endpoint when ready.
