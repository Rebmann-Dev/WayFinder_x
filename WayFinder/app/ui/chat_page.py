import streamlit as st

import datetime
import os

from services.memory_service import MemoryService
from services.model_service import ModelService
from services.safety_service import SafetyService
from ui.chat_handlers import handle_assistant_response, handle_user_message
from ui.styles import inject_global_styles
from components.location_picker import location_picker
from models.safety.schemas import SafetyRequest
from models.safety.submodels.peru_safety import _WILDLIFE_THREATS_PERU  # noqa — lazy import ok


@st.cache_resource
def get_model_service(_cache_version: str = "v6-mps-eager-attn") -> ModelService:
    return ModelService()


@st.cache_resource
def get_safety_service() -> SafetyService:
    return SafetyService()


def get_selected_location_fields() -> dict:
    selected = st.session_state.get("selected_location")
    if not selected:
        return {"lat": None, "lon": None, "country": None, "location_name": None}

    short_location_name = (
        selected.get("city")
        or selected.get("county")
        or selected.get("state_region")
        or selected.get("country")
    )
    return {
        "lat": selected.get("lat"),
        "lon": selected.get("lon"),
        "country": selected.get("country"),
        "location_name": short_location_name,
    }


# ── only show raw debug JSON in local dev ──────────────────────────────────────
_DEBUG = os.getenv("WAYFINDER_DEBUG", "").lower() in ("1", "true", "yes")


@st.dialog("Pick a destination", width="large")
def _location_picker_modal(safety_service: SafetyService) -> None:
    picked_location = location_picker(
        key="wayfinder_location_picker_modal",
        height=520,
        default=st.session_state["selected_location"],
    )

    if picked_location and picked_location.get("lat") is not None:
        st.session_state["selected_location"] = picked_location
        st.session_state["safety_result"] = None
        st.rerun()


def _render_sidebar(safety_service: SafetyService) -> None:
    with st.sidebar:
        st.header("WayFinder")

        explore_country = st.selectbox(
            "Explore country",
            ["Ecuador", "Peru"],
            key="explore_country",
            label_visibility="collapsed",
        )
        if st.button("🌿 Explore", use_container_width=True, key="btn_explore"):
            st.session_state["explore_mode"] = True
            st.rerun()

        if st.button("🗑️ Clear chat", use_container_width=True):
            MemoryService.clear()
            st.rerun()

        st.divider()

        # ── Travel date ───────────────────────────────────────────────────────────
        st.caption("📅 TRAVEL DATE")

        if "departure_date_picker" not in st.session_state:
            st.session_state["departure_date_picker"] = st.session_state.get(
                "departure_date"
            ) or datetime.date.today() + datetime.timedelta(days=1)
        else:
            # Sync from canonical store — only safe before the widget renders
            stored = st.session_state.get("departure_date")
            if (
                stored
                and stored != st.session_state["departure_date_picker"]
                and st.session_state.get("_date_from_chat")
            ):
                st.session_state["departure_date_picker"] = stored

        picked_date = st.date_input(
            label="Travel date",
            label_visibility="collapsed",
            min_value=datetime.date.today(),
            key="departure_date_picker",
        )

        if picked_date:
            st.session_state["departure_date"] = picked_date
            date_source = st.session_state.get("_date_from_chat")
            st.caption(
                f"{'💬 Updated from chat' if date_source else '📅'} "
                f"**{picked_date.strftime('%A, %b %d %Y')}**"
            )
            st.session_state["_date_from_chat"] = None

        st.divider()

        # ── Departure city ────────────────────────────────────────────────────
        st.caption("🛫 DEPARTURE CITY")
        if "departure_input_field" not in st.session_state:
            st.session_state["departure_input_field"] = st.session_state.get("departure_city_raw", "")
        departure_input = st.text_input(
            label="Departure city",
            label_visibility="collapsed",
            placeholder="e.g. Phoenix, PHX, New York…",
            key="departure_input_field",
        )

        if departure_input != st.session_state.get("departure_city_raw", ""):
            st.session_state["departure_city_raw"] = departure_input
            st.session_state["departure_city_resolved"] = None
            st.session_state["departure_city_candidates"] = []

        if departure_input and len(departure_input.strip()) >= 2:
            from services.airport_search_service import search_airports as _search

            # Only re-search if candidates aren't already loaded for this input
            if not st.session_state.get("departure_city_candidates"):
                matches = _search(departure_input.strip(), limit=5)
                st.session_state["departure_city_candidates"] = matches

            candidates = st.session_state.get("departure_city_candidates", [])

            if not candidates:
                st.caption("⚠️ No airport found — try a city name or IATA code")

            elif len(candidates) == 1:
                # Unambiguous — auto-resolve
                st.session_state["departure_city_resolved"] = candidates[0]
                resolved = candidates[0]
                st.success(f"✈️ **{resolved['iata']}** · {resolved['name']}")

            else:
                # Multiple matches — let the user pick inline, no chat loop needed
                resolved = st.session_state.get("departure_city_resolved")
                options = {
                    f"{c['iata']} — {c['name']} ({c['city']})": c for c in candidates
                }
                current_label = next(
                    (
                        k
                        for k, v in options.items()
                        if resolved and v["iata"] == resolved["iata"]
                    ),
                    None,
                )
                chosen_label = st.selectbox(
                    "Which airport?",
                    options=list(options.keys()),
                    index=list(options.keys()).index(current_label)
                    if current_label
                    else 0,
                    key="departure_airport_select",
                )
                st.session_state["departure_city_resolved"] = options[chosen_label]
                resolved = options[chosen_label]
                st.success(f"✈️ **{resolved['iata']}** · {resolved['name']}")

        st.divider()

        # ── Location picker — opens a modal ───────────────────────────────────
        if st.button("📍 Pick a destination", use_container_width=True):
            _location_picker_modal(safety_service)

        st.caption("— or type a destination —")
        typed_dest = st.text_input(
            "Destination",
            label_visibility="collapsed",
            placeholder="e.g. Quito, Montañita, Tena…",
            key="typed_destination_input",
        )
        if typed_dest and len(typed_dest.strip()) >= 2:
            # Geocode using Nominatim (no API key needed)
            import requests as _req
            if st.session_state.get("_last_typed_dest") != typed_dest:
                try:
                    r = _req.get(
                        "https://nominatim.openstreetmap.org/search",
                        params={"q": typed_dest, "format": "json", "limit": 1},
                        headers={"User-Agent": "WayFinder/1.0"},
                        timeout=5,
                    )
                    if r.ok and r.json():
                        geo = r.json()[0]
                        st.session_state["selected_location"] = {
                            "lat": float(geo["lat"]),
                            "lon": float(geo["lon"]),
                            "country": geo.get("display_name", "").split(",")[-1].strip(),
                            "city": typed_dest,
                        }
                        st.session_state["_last_typed_dest"] = typed_dest
                        st.session_state["safety_result"] = None
                        st.rerun()
                except Exception:
                    pass

        # ── Selected location summary ─────────────────────────────────────────
        if st.session_state["selected_location"]:
            fields = get_selected_location_fields()
            selected = st.session_state["selected_location"]

            st.divider()
            st.caption("📌 Selected destination")

            # Show the most specific name available
            display_name = (
                selected.get("city")
                or selected.get("county")
                or selected.get("state_region")
                or selected.get("country")
                or "Unknown location"
            )
            st.markdown(f"**{display_name}**")
            st.caption(
                f"{fields['lat']:.4f}, {fields['lon']:.4f}"
                + (f" · {fields['country']}" if fields["country"] else "")
            )

            col1, col2 = st.columns(2)

            with col1:
                if st.button(
                    "✏️ Change",
                    use_container_width=True,
                    key="btn_change_location",
                ):
                    _location_picker_modal(safety_service)

            with col2:
                if st.button(
                    "✕ Clear",
                    use_container_width=True,
                    key="btn_clear_location",
                ):
                    st.session_state["selected_location"] = None
                    st.session_state["safety_result"] = None
                    st.rerun()

            # ── Safety score ──────────────────────────────────────────────────
            st.divider()
            can_score = fields["lat"] is not None and fields["lon"] is not None

            if st.button(
                "🛡️ Run safety score", disabled=not can_score, use_container_width=True
            ):
                try:
                    req = SafetyRequest(
                        latitude=float(fields["lat"]),
                        longitude=float(fields["lon"]),
                        country=fields["country"],
                        location_name=fields["location_name"],
                    )
                    result = safety_service.assess_request(req, include_details=True)
                    st.session_state["safety_result"] = result
                    st.session_state["safety_debug"] = {
                        "stage": "result_returned",
                        "result": result,
                    }
                except Exception as e:
                    st.session_state["safety_debug"] = {
                        "stage": "exception",
                        "error": repr(e),
                    }

            if st.session_state["safety_result"] is not None:
                result = st.session_state["safety_result"]
                if result.get("success"):
                    score = result.get("safety_score")
                    band = result.get("risk_band", "—")
                    band_color = {
                        "low": "🟢",
                        "moderate": "🟡",
                        "elevated": "🟠",
                        "high": "🔴",
                    }.get(band, "⚪")
                    st.metric(
                        "Safety score", f"{score:.2f}" if score is not None else "—"
                    )
                    st.caption(f"{band_color} Risk band: **{band}**")
                    with st.expander("Prediction details", expanded=False):
                        st.json(result)
                else:
                    st.error(f"Scoring failed: {result.get('error')}")

            if _DEBUG and st.session_state.get("safety_debug") is not None:
                with st.expander("Safety debug", expanded=False):
                    st.json(st.session_state["safety_debug"])

        result = st.session_state.get("safety_result", {}) or {}
        if result.get("success"):
            # Weather risks
            weather = result.get("weather_risk", {})
            if weather and not weather.get("error"):
                with st.expander("🌦️ Weather Risks", expanded=False):
                    st.caption(f"Risk level: **{weather.get('weather_risk_label', '—')}** ({weather.get('weather_risk_score', '—')}/5)")
                    st.caption(weather.get("travel_month_assessment", ""))
                    for r in weather.get("risks", []):
                        st.markdown(f"**{r['type'].replace('_',' ').title()}** (severity {r['severity']}/5)")
                        st.caption(r.get("description", ""))

            # Ecuador risks
            ec = result.get("ecuador_risk", {})
            if ec and ec.get("applicable"):
                with st.expander("🐆 Ecuador Wildlife & Crime", expanded=False):
                    st.caption(f"Province: **{ec.get('province','—')}** | Crime risk: {ec.get('crime_risk','—')}/5 | Wildlife risk: {ec.get('wildlife_risk','—')}/5")
                    st.caption(ec.get("crime_notes", ""))
                    st.markdown("**Active wildlife threats:**")
                    for threat in ec.get("wildlife_threat_details", []):
                        with st.expander(f"{'⚠️' if threat['risk'] >= 4 else '⚡'} {threat['name']} (risk {threat['risk']}/5)", expanded=False):
                            st.caption(f"Type: {threat.get('type','—')} | Habitats: {', '.join(threat.get('habitats',[]))}")
                            st.markdown(threat.get("notes", ""))

            # LGBT safety
            lgbt = result.get("lgbt_safety", {})
            if lgbt and not lgbt.get("error"):
                with st.expander("🏳️‍🌈 LGBT Safety", expanded=False):
                    score = lgbt.get("lgbt_safety_score")
                    label = {1:"Criminalized",2:"Hostile",3:"Neutral",4:"Accepting",5:"Very Safe"}.get(score, "—")
                    st.metric("LGBT Safety", f"{score}/5 — {label}" if score else "—")

        # TODO: population filter — requires global dataset integration


ECUADOR_HIKES = [
    {
        "name": "Quilotoa Loop",
        "province": "Cotopaxi",
        "lat": -0.8635, "lon": -78.9,
        "difficulty": "Moderate",
        "duration": "3-4 days",
        "elevation_m": 3914,
        "description": "Iconic volcanic crater lake circuit through indigenous villages. The crater rim hike (14km) offers stunning views of the turquoise lake. Start in Latacunga or Sigchos.",
        "tips": "Altitude acclimatize in Quito first. Bring warm layers — nights drop below 5°C. Camping and guesthouses available in Quilotoa, Chugchilán, Isinliví.",
        "wildlife": ["Andean condor", "Carunculated caracara", "Páramo rabbit"],
    },
    {
        "name": "Cotopaxi Volcano Trek",
        "province": "Cotopaxi",
        "lat": -0.6835, "lon": -78.4378,
        "difficulty": "Hard",
        "duration": "1-2 days",
        "elevation_m": 5897,
        "description": "Summit attempt on one of the world's highest active volcanoes. The standard route climbs from José Rivas refuge (4864m) to the summit crater at 5897m.",
        "tips": "Requires crampons, ice axe, and guide. Check IGEPN volcanic activity alerts. Acclimatize 3+ days. Start summit push at midnight.",
        "wildlife": ["Andean condor", "Puma (rare sighting)"],
    },
    {
        "name": "Avenue of the Volcanoes",
        "province": "Multiple",
        "lat": -1.5, "lon": -78.5,
        "difficulty": "Easy-Hard (varies)",
        "duration": "7-14 days",
        "elevation_m": 4000,
        "description": "Alexander von Humboldt's famous route through the Andes passing Cayambe, Cotopaxi, Tungurahua, Chimborazo and more. Can be done by bus/train with day hikes from each base.",
        "tips": "Baños makes a great mid-point base. Riobamba for Chimborazo access. Train del Tren heritage railway connects several stops.",
        "wildlife": ["Andean condor", "Spectacled bear (rare)", "Puma"],
    },
    {
        "name": "El Ángel Páramo",
        "province": "Carchi",
        "lat": 0.6136, "lon": -77.9349,
        "difficulty": "Easy",
        "duration": "1 day",
        "elevation_m": 4000,
        "description": "High-altitude páramo reserve famous for giant Frailejones (Espeletia) plants. Otherworldly alien landscape with lagoons and endemic flora.",
        "tips": "Very cold — bring full waterproofs and layers. Morning visits before cloud rolls in. Can be day-tripped from Tulcán or Ibarra.",
        "wildlife": ["Andean condor", "Curiquingue falcon", "Spectacled bear"],
    },
    {
        "name": "Napo Wildlife Center Trails",
        "province": "Orellana",
        "lat": -0.5334, "lon": -76.2167,
        "difficulty": "Easy",
        "duration": "2-5 days",
        "elevation_m": 280,
        "description": "Amazon jungle guided walks from the Napo Wildlife Center lodge. Canopy tower for bird/wildlife viewing, oxbow lake canoe, and night walks for herps and insects.",
        "tips": "Accessible only by motorized canoe from Coca (2hr). All-inclusive lodge. Best birding Oct-Jan. Malaria prophylaxis recommended.",
        "wildlife": ["Jaguar (occasional)", "Giant otter", "Harpy eagle", "400+ bird species"],
    },
    {
        "name": "Cajas National Park Circuit",
        "province": "Azuay",
        "lat": -2.7833, "lon": -79.2167,
        "difficulty": "Moderate",
        "duration": "1-3 days",
        "elevation_m": 4450,
        "description": "Stunning high-altitude lakes circuit near Cuenca. Over 230 lakes amid moorland and polylepis forest. The Toreadora area is most accessible for day hikes.",
        "tips": "Weather changes rapidly — always bring rain gear. Easy access from Cuenca (30min). Fishing permitted in some lakes (trout).",
        "wildlife": ["Andean condor", "Spectacled bear", "White-tailed deer"],
    },
    {
        "name": "Mindo Cloud Forest",
        "province": "Pichincha",
        "lat": -0.05, "lon": -78.7667,
        "difficulty": "Easy",
        "duration": "1-3 days",
        "elevation_m": 1250,
        "description": "World-class birdwatching destination 2hrs from Quito. 500+ species including toucans, tanagers, cock-of-the-rock. Butterfly farms, chocolate tours, tubing.",
        "tips": "Best birding at dawn (5-9am). Many guesthouses. Cable car (tarabita) crosses the cloud forest canyon. Bring binoculars.",
        "wildlife": ["Cock-of-the-rock", "Toucan Barbet", "Andean cock-of-the-rock", "Glass frogs"],
    },
    {
        "name": "Tungurahua Volcano Viewpoint",
        "province": "Tungurahua",
        "lat": -1.4679, "lon": -78.446,
        "difficulty": "Moderate",
        "duration": "1 day",
        "elevation_m": 5023,
        "description": "Hike to the refuge and viewpoints on 'The Black Giant'. The active volcano last erupted significantly in 2016. Great views of Baños and the Pastaza valley.",
        "tips": "Check volcanic activity status before going. Lower slopes accessible from Baños. Upper hike requires guide. Nighttime eruption viewing is spectacular when active.",
        "wildlife": ["Andean condor", "Páramo hummingbirds"],
    },
    {
        "name": "Podocarpus National Park",
        "province": "Loja / Zamora",
        "lat": -4.1167, "lon": -79.15,
        "difficulty": "Moderate",
        "duration": "2-4 days",
        "elevation_m": 3700,
        "description": "Biodiversity hotspot straddling Andes and Amazon. Podocarpus trees (Ecuador's only native conifer), countless orchids, and exceptional bird diversity.",
        "tips": "Two sectors: Cajanuma (highland) near Loja, and Bombuscaro (lowland) near Zamora. Camping available. Guides recommended for backcountry.",
        "wildlife": ["Spectacled bear", "Mountain tapir", "600+ bird species including Royal Sunangel"],
    },
    {
        "name": "Sierra Negra Volcano — Galápagos",
        "province": "Galápagos",
        "lat": -0.8303, "lon": -91.1702,
        "difficulty": "Moderate",
        "duration": "1 day",
        "elevation_m": 1124,
        "description": "Largest volcanic caldera in the Galápagos (10km wide). The hike crosses lava fields to the rim with views into the active crater and across Isabela Island.",
        "tips": "Guide required (Galápagos NP rule). Start from Puerto Villamil. Bring sun protection — very exposed. Best in dry season (June-Dec).",
        "wildlife": ["Giant tortoise", "Marine iguana", "Galápagos penguin (near coast)", "Flightless cormorant"],
    },
]

PERU_HIKES = [
    {
        "name": "Inca Trail to Machu Picchu",
        "region": "Cusco",
        "lat": -13.1631, "lon": -72.5450,
        "difficulty": "Hard",
        "duration": "4 days",
        "elevation_m": 4215,
        "description": "The world's most iconic trekking route. The classic 4-day, 43km trail passes Inca ruins, cloud forest, and high mountain passes before descending to Machu Picchu through the Sun Gate.",
        "tips": "Permits sell out months in advance — book by January for high season. Altitude acclimatize in Cusco for 2+ days. Only 500 trekkers per day allowed. Guided tours mandatory.",
        "trail_coords": [
            [-13.5209, -71.9784],  # Km 82 start
            [-13.3892, -72.1428],  # Llulluchayoc
            [-13.3167, -72.2833],  # Dead Woman's Pass 4215m
            [-13.2833, -72.3667],  # Runkurakay
            [-13.2167, -72.4333],  # Sayacmarca
            [-13.1944, -72.4667],  # Phuyupatamarca
            [-13.1833, -72.5000],  # Wiñay Wayna
            [-13.1631, -72.5450],  # Machu Picchu
        ],
        "wildlife": ["Spectacled bear", "Andean condor", "Cock-of-the-rock", "Mountain tapir"],
    },
    {
        "name": "Salkantay Trek",
        "region": "Cusco",
        "lat": -13.3347, "lon": -72.5864,
        "difficulty": "Hard",
        "duration": "5 days",
        "elevation_m": 4600,
        "description": "Alternative to Inca Trail crossing beneath Salkantay mountain (6271m). Passes through glaciers, cloud forest, and coffee farms before reaching Aguas Calientes.",
        "tips": "No permit required. Highest point 4600m — acclimatize well. Cold nights at Salkantay Pass camp. Lower cost than Inca Trail.",
        "trail_coords": [
            [-13.5278, -72.3069],  # Mollepata
            [-13.4278, -72.4431],  # Soraypampa
            [-13.3347, -72.5864],  # Salkantay Pass
            [-13.2889, -72.6333],  # La Playa
            [-13.2014, -72.5872],  # Aguas Calientes
        ],
        "wildlife": ["Andean condor", "Viscacha", "Puma (rare)", "Hummingbirds"],
    },
    {
        "name": "Cordillera Blanca — Santa Cruz Trek",
        "region": "Ancash",
        "lat": -8.9761, "lon": -77.6294,
        "difficulty": "Hard",
        "duration": "4 days",
        "elevation_m": 4750,
        "description": "Peru's finest high-altitude circuit in the world's highest tropical mountain range. Passes glaciers, turquoise lakes, and 6000m+ peaks. Highest point: Punta Unión pass at 4750m.",
        "tips": "Start from Cashapampa or Vaquería. Huaraz is the base — acclimatize 3+ days. Guide recommended but not mandatory. Ice axes needed for pass in wet season.",
        "trail_coords": [
            [-8.9344, -77.7603],   # Cashapampa
            [-8.9447, -77.7217],   # Llamacorral
            [-8.9761, -77.6294],   # Punta Unión 4750m
            [-9.0139, -77.5989],   # Taullipampa
            [-9.0683, -77.5494],   # Vaquería
        ],
        "wildlife": ["Andean condor", "Puma", "White-tailed deer", "Viscacha"],
    },
    {
        "name": "Colca Canyon Trek",
        "region": "Arequipa",
        "lat": -15.5306, "lon": -71.9886,
        "difficulty": "Moderate",
        "duration": "2-3 days",
        "elevation_m": 3400,
        "description": "One of the world's deepest canyons (3270m depth). Trek down to the oasis village of Sangalle, swim in natural pools, then hike back up. Best condor viewing point at Cruz del Cóndor.",
        "tips": "Start from Cabanaconde (3287m). Descent takes 3-4hrs, ascent 4-5hrs — start very early. Water available in Sangalle. Condors most active 8-10am.",
        "trail_coords": [
            [-15.6217, -71.9700],  # Cabanaconde
            [-15.5778, -71.9833],  # Tapay trail junction
            [-15.5306, -71.9886],  # Sangalle oasis
        ],
        "wildlife": ["Andean condor (abundant)", "Viscacha", "Andean fox", "Hummingbirds"],
    },
    {
        "name": "Ausangate Circuit",
        "region": "Cusco",
        "lat": -13.7833, "lon": -71.2167,
        "difficulty": "Hard",
        "duration": "5-7 days",
        "elevation_m": 5200,
        "description": "Remote circuit around Ausangate mountain (6384m). Passes through rainbow-colored mineral mountains, glacial lakes, and high-altitude puna grasslands with traditional Quechua communities.",
        "tips": "Highest circuit pass at 5200m — serious acclimatization required. Pack horses available. Nights below -10°C. Vinicunca (Rainbow Mountain) on southern approach.",
        "trail_coords": [
            [-13.7167, -71.2833],  # Tinqui
            [-13.7500, -71.2500],  # Upispampa
            [-13.7833, -71.2167],  # Ausangate base
            [-13.8167, -71.1833],  # Palomani pass
            [-13.7667, -71.1500],  # Laguna Sibinacocha
            [-13.7167, -71.2833],  # Tinqui
        ],
        "wildlife": ["Andean condor", "Vicuña", "Alpaca herds", "Puma (rare)"],
    },
    {
        "name": "Huayhuash Circuit",
        "region": "Ancash / Huánuco",
        "lat": -10.2736, "lon": -76.9039,
        "difficulty": "Very Hard",
        "duration": "9-12 days",
        "elevation_m": 5450,
        "description": "Often called the world's greatest trek. Full circuit around the Cordillera Huayhuash passes 6+ glaciated peaks over 6000m including Yerupajá (6634m). Extremely remote and demanding.",
        "tips": "Community fees at multiple checkpoints. Ice axe and crampons recommended. Muleteers available from Chiquián or Llamac. Medical evacuation extremely difficult — do not go solo.",
        "trail_coords": [
            [-10.1833, -76.9833],  # Llamac
            [-10.2167, -76.9500],  # Pocpa
            [-10.2736, -76.9039],  # Laguna Jahuacocha
            [-10.3500, -76.8833],  # Rondoy pass
            [-10.4167, -76.8167],  # Laguna Carhuacocha
            [-10.3000, -76.7500],  # Huayhuash pass
        ],
        "wildlife": ["Andean condor", "Vicuña", "Puma", "Giant hummingbird"],
    },
    {
        "name": "Choquequirao Trek",
        "region": "Cusco / Apurímac",
        "lat": -13.5389, "lon": -72.8486,
        "difficulty": "Hard",
        "duration": "4-5 days",
        "elevation_m": 3085,
        "description": "The lost Inca citadel that only ~30 trekkers per day visit (vs 5000/day at Machu Picchu). Dramatic descent to Apurímac canyon and climb to the ruins. Often called 'Machu Picchu without the crowds'.",
        "tips": "No road access — only on foot or horse. Start from Cachora. Drop 1500m to river, climb 1500m to ruins. Very hot in canyon. Camping mandatory.",
        "trail_coords": [
            [-13.6450, -72.7872],  # Cachora
            [-13.5833, -72.8167],  # Chiquisca camp
            [-13.5389, -72.8486],  # Choquequirao ruins
        ],
        "wildlife": ["Andean condor", "Cock-of-the-rock", "White-bellied parrot"],
    },
    {
        "name": "Manu National Park Trails",
        "region": "Madre de Dios / Cusco",
        "lat": -11.8768, "lon": -71.4894,
        "difficulty": "Easy",
        "duration": "4-7 days",
        "elevation_m": 380,
        "description": "UNESCO Biosphere Reserve — the most biodiverse place on Earth. Guided walks from lodges to oxbow lakes, clay licks for parrots and macaws, canopy platforms, and night walks.",
        "tips": "Only accessible by licensed operators. Entry requires pre-arranged tour from Cusco. Malaria prophylaxis essential. October-April wet season best for wildlife.",
        "trail_coords": [
            [-13.0583, -71.5725],  # Patria checkpoint
            [-12.5000, -71.5000],  # Cocha Salvador
            [-11.8768, -71.4894],  # Cocha Otorongo
        ],
        "wildlife": ["Jaguar", "Giant otter", "Harpy eagle", "1000+ bird species", "Giant river otter"],
    },
    {
        "name": "Vinicunca Rainbow Mountain",
        "region": "Cusco",
        "lat": -13.8076, "lon": -71.3122,
        "difficulty": "Moderate",
        "duration": "1 day",
        "elevation_m": 5200,
        "description": "Surreal mineral-stained mountain revealing red, yellow, green, and purple stripes. One of Peru's most photogenic destinations. Day trip from Cusco via Pitumarca.",
        "tips": "5200m — acclimatize in Cusco 3+ days first. Horses available for rent on trail. Starts at 4300m, gains 900m. Cold and windy at top. Go early for fewer crowds.",
        "trail_coords": [
            [-13.8600, -71.3500],  # Cusipata trailhead
            [-13.8300, -71.3300],  # Mid-trail
            [-13.8076, -71.3122],  # Vinicunca summit
        ],
        "wildlife": ["Vicuña", "Alpaca", "Andean condor", "Mountain viscacha"],
    },
    {
        "name": "Lares Trek",
        "region": "Cusco",
        "lat": -13.0833, "lon": -72.0000,
        "difficulty": "Moderate",
        "duration": "3 days",
        "elevation_m": 4400,
        "description": "Cultural and scenic alternative to the Inca Trail through traditional Quechua weaving villages. Hot springs at Lares, 4400m passes, and ends at Ollantaytambo for train to Machu Picchu.",
        "tips": "No permit required. Less crowded than Inca Trail. Cultural experience with local artisan communities. Horses available from Lares village.",
        "trail_coords": [
            [-13.0000, -72.0833],  # Lares hot springs
            [-13.0417, -72.0417],  # Ipsaycocha pass 4400m
            [-13.0833, -72.0000],  # Patacancha
            [-13.2578, -72.2639],  # Ollantaytambo
        ],
        "wildlife": ["Andean condor", "Viscacha", "Alpaca", "Spectacled bear (rare)"],
    },
]

COUNTRY_HIKES: dict[str, list] = {
    "Ecuador": ECUADOR_HIKES,
    "Peru": PERU_HIKES,
}


def _render_hikes_tab() -> None:
    import folium
    from streamlit_folium import st_folium

    active_country = st.session_state.get("explore_country", "Ecuador")
    hikes = COUNTRY_HIKES.get(active_country, ECUADOR_HIKES)
    hike_names = [h["name"] for h in hikes]
    chosen = st.selectbox("Choose a hike:", ["— Select a hike —"] + hike_names, key="hike_selector")

    if chosen != "— Select a hike —":
        idx = hike_names.index(chosen)
        hike = hikes[idx]
        st.session_state["selected_hike_idx"] = idx

        col1, col2 = st.columns([2, 3])
        with col1:
            st.markdown(f"### {hike['name']}")
            st.caption(f"📍 {hike['province']} · {hike['difficulty']} · {hike['duration']}")
            st.caption(f"⛰️ Max elevation: {hike['elevation_m']:,}m")
            st.markdown(hike["description"])
            st.markdown("**Tips:**")
            st.caption(hike["tips"])
            if hike.get("wildlife"):
                st.markdown("**Wildlife you may see:**")
                st.caption(", ".join(hike["wildlife"]))

        with col2:
            m = folium.Map(location=[hike["lat"], hike["lon"]], zoom_start=11, tiles="OpenStreetMap")
            # Draw trail polyline if coordinates available
            trail_coords = hike.get("trail_coords")
            if trail_coords and len(trail_coords) >= 2:
                folium.PolyLine(
                    locations=trail_coords,
                    color="#e05c00",
                    weight=4,
                    opacity=0.85,
                    tooltip=f"{hike['name']} trail",
                ).add_to(m)
                # Start and end markers
                folium.Marker(
                    trail_coords[0],
                    popup="Start",
                    tooltip="Start",
                    icon=folium.Icon(color="green", icon="play", prefix="glyphicon"),
                ).add_to(m)
                folium.Marker(
                    trail_coords[-1],
                    popup="End / Summit",
                    tooltip="End / Summit",
                    icon=folium.Icon(color="red", icon="flag", prefix="glyphicon"),
                ).add_to(m)
            else:
                # Fallback: single point marker
                folium.Marker(
                    [hike["lat"], hike["lon"]],
                    popup=hike["name"],
                    tooltip=hike["name"],
                    icon=folium.Icon(color="green", icon="tree-conifer", prefix="glyphicon"),
                ).add_to(m)
            st_folium(m, use_container_width=True, height=500, key=f"hike_map_{idx}")


def _render_wildlife_tab() -> None:
    active_country = st.session_state.get("explore_country", "Ecuador")
    if active_country == "Peru":
        from models.safety.submodels.peru_safety import _WILDLIFE_THREATS_PERU as threats_list
    else:
        from models.safety.submodels.ecuador_safety import _WILDLIFE_THREATS as threats_list

    # Group by type
    by_type = {}
    for t in threats_list:
        ttype = t.get("type", "other")
        by_type.setdefault(ttype, []).append(t)

    type_labels = {
        "venomous snake": "🐍 Venomous Snakes",
        "large predator": "🐆 Large Predators",
        "disease vector": "🦟 Disease Vectors",
        "venomous spider": "🕷️ Venomous Spiders",
        "venomous insect": "🐜 Venomous Insects",
        "parasitic insect": "🪲 Parasitic Insects",
        "parasitic fish": "🐟 Parasitic Fish",
        "electric fish": "⚡ Electric Fish",
        "rabies vector": "🦇 Rabies Vectors",
        "geological": "🌋 Geological Hazards",
        "environmental": "🏔️ Environmental Hazards",
        "weather": "⛈️ Weather Hazards",
        "wildlife encounter": "🦎 Wildlife Encounters",
    }

    for ttype, threats in sorted(by_type.items()):
        label = type_labels.get(ttype, ttype.title())
        with st.expander(label, expanded=False):
            for threat in sorted(threats, key=lambda x: -x["risk"]):
                risk_stars = "🔴" * min(threat["risk"], 5)
                st.markdown(f"**{threat['name']}** {risk_stars} ({threat['risk']}/5)")
                st.caption(f"Habitats: {', '.join(threat.get('habitats', []))} | Max altitude: {threat.get('altitude_max_m', 'N/A')}m")
                st.caption(threat.get("notes", ""))
                st.divider()


def _render_explore_panel() -> None:
    import folium
    from streamlit_folium import st_folium

    col_back, col_title = st.columns([1, 6])
    with col_back:
        if st.button("← Back to chat"):
            st.session_state["explore_mode"] = False
            st.rerun()
    with col_title:
        st.subheader(f"🌿 Explore {st.session_state.get('explore_country','Ecuador')}")

    tab_map, tab_hikes, tab_wildlife = st.tabs(["🗺️ Map", "🥾 Hikes", "🐆 Wildlife"])

    with tab_map:
        # Determine country context from selected location
        active_country = st.session_state.get("explore_country", "Ecuador")
        country_centers = {
            "Ecuador": ([-1.5, -78.0], 7),
            "Peru":    ([-9.0, -75.0], 6),
        }
        center, zoom = country_centers.get(active_country, ([-1.5, -78.0], 7))

        # Map controls row
        map_col1, map_col2, map_col3 = st.columns([2, 2, 3])
        with map_col1:
            show_wildlife = st.checkbox("🐆 Show wildlife zones", value=st.session_state.get("map_show_wildlife", False), key="map_show_wildlife")
        with map_col2:
            show_hikes = st.checkbox("🥾 Show hike markers", value=st.session_state.get("map_show_hikes", True), key="map_show_hikes")
        with map_col3:
            wildlife_risk_filter = st.slider("Min wildlife risk to show", 1, 5, st.session_state.get("wildlife_risk_filter", 3), key="wildlife_risk_filter")

        m = folium.Map(location=center, zoom_start=zoom, tiles="OpenStreetMap")

        # Add destination pin
        sel = st.session_state.get("selected_location")
        if sel and sel.get("lat"):
            folium.Marker(
                [sel["lat"], sel["lon"]],
                popup=sel.get("city", "Destination"),
                tooltip="Your destination",
                icon=folium.Icon(color="red", icon="map-marker"),
            ).add_to(m)

        # Wildlife zone circles
        if show_wildlife:
            if active_country == "Ecuador":
                from models.safety.submodels.ecuador_safety import _WILDLIFE_THREATS as _wt
                _prov_centroids = {
                    "Guayas": (-1.83, -79.97), "Esmeraldas": (0.96, -79.65),
                    "Sucumbíos": (0.09, -76.89), "Orellana": (-0.46, -76.99),
                    "Napo": (-0.99, -77.81), "Pastaza": (-1.49, -78.00),
                    "Pichincha": (-0.18, -78.47), "Manabí": (-1.05, -80.45),
                    "Guayas coast": (-2.0, -80.0), "Amazon": (-1.0, -76.5),
                }
                _threat_centers = {
                    "amazon": (-1.0, -76.5), "coastal_lowland": (-1.5, -80.5),
                    "cloud_forest": (-0.5, -78.5), "andes": (-1.5, -78.5),
                    "galapagos": (-0.6, -90.5), "rural": (-2.0, -79.0), "urban": (-0.2, -78.5),
                }
            else:
                from models.safety.submodels.peru_safety import _WILDLIFE_THREATS_PERU as _wt
                _threat_centers = {
                    "amazon": (-5.0, -74.0), "coastal_lowland": (-10.0, -77.0),
                    "cloud_forest": (-10.0, -74.0), "andes": (-13.0, -72.0),
                    "rural": (-8.0, -75.0), "urban": (-12.0, -77.0),
                }

            risk_colors = {5: "#cc0000", 4: "#ff6600", 3: "#ffaa00", 2: "#88cc00", 1: "#00aa44"}
            shown_threats = set()
            for threat in _wt:
                if threat["risk"] < wildlife_risk_filter:
                    continue
                habitats = threat.get("habitats", [])
                for hab in habitats:
                    if hab in _threat_centers:
                        clat, clon = _threat_centers[hab]
                        key = (threat["name"], hab)
                        if key in shown_threats:
                            continue
                        shown_threats.add(key)
                        color = risk_colors.get(threat["risk"], "#888888")
                        folium.Circle(
                            location=[clat, clon],
                            radius=80000,  # 80km radius
                            color=color,
                            fill=True,
                            fill_opacity=0.15,
                            opacity=0.5,
                            tooltip=f"{threat['name']} (risk {threat['risk']}/5)\n{threat.get('notes','')[:80]}",
                            popup=folium.Popup(
                                f"<b>{threat['name']}</b><br>Risk: {threat['risk']}/5<br>Type: {threat.get('type','')}<br>{threat.get('notes','')}",
                                max_width=250
                            ),
                        ).add_to(m)
                        break  # one circle per threat

        # Hike markers
        if show_hikes:
            hikes_to_show = COUNTRY_HIKES.get(active_country, [])
            for hike in hikes_to_show:
                folium.Marker(
                    [hike["lat"], hike["lon"]],
                    popup=folium.Popup(
                        f"<b>{hike['name']}</b><br>{hike['difficulty']} · {hike['duration']}<br>{hike['description'][:100]}...",
                        max_width=200
                    ),
                    tooltip=f"🥾 {hike['name']}",
                    icon=folium.Icon(color="green", icon="leaf", prefix="glyphicon"),
                ).add_to(m)
                # Draw trail polyline if available
                if hike.get("trail_coords") and len(hike["trail_coords"]) >= 2:
                    folium.PolyLine(
                        locations=hike["trail_coords"],
                        color="#006600",
                        weight=2,
                        opacity=0.6,
                        tooltip=hike["name"],
                    ).add_to(m)

        st_folium(m, use_container_width=True, height=800, key="explore_main_map")

    with tab_hikes:
        st.markdown(f"### {st.session_state.get('explore_country','Ecuador')} Hikes")
        st.caption("Select a hike to see details and view it on the map.")
        _render_hikes_tab()

    with tab_wildlife:
        st.markdown(f"### {st.session_state.get('explore_country','Ecuador')} Wildlife Threats")
        _render_wildlife_tab()


def render_chat_page() -> None:
    st.title("✈️ WayFinder")
    inject_global_styles()

    MemoryService.initialize()
    model_service = get_model_service()
    safety_service = get_safety_service()

    # Initialize session state keys
    for key, default in [
        ("selected_location", None),
        ("safety_result", None),
        ("safety_debug", None),
        ("explore_mode", False),
        ("explore_country", "Ecuador"),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    # ── Sidebar holds all controls ────────────────────────────────────────────
    _render_sidebar(safety_service)

    # ── Explore mode: full-screen panel instead of chat ─────────────────────
    if st.session_state.get("explore_mode"):
        _render_explore_panel()
        return  # don't render chat while in explore mode

    # ── Main column is purely the chat ────────────────────────────────────────
    for message in MemoryService.get_display_messages():
        with st.chat_message(message.role):
            st.markdown(message.content)

    user_input = st.chat_input("Ask about routes, destinations, or itineraries...")

    if user_input:
        handle_user_message(user_input)
        handle_assistant_response(model_service)
