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
                    _render_safety_results_panel(result)
                else:
                    st.error(f"Scoring failed: {result.get('error')}")

            if _DEBUG and st.session_state.get("safety_debug") is not None:
                with st.expander("Safety debug", expanded=False):
                    st.json(st.session_state["safety_debug"])


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
    {
        "name": "Kuelap Fortress Trek",
        "region": "Amazonas",
        "lat": -6.4219, "lon": -77.9244,
        "difficulty": "Easy-Moderate",
        "duration": "1-2 days",
        "elevation_m": 3000,
        "description": "Pre-Inca Chachapoya cloud fortress perched at 3000m above the Utcubamba canyon. Often called the 'Machu Picchu of the North'. A cable car now provides easy access from Nuevo Tingo, with shorter hikes around the ruins.",
        "tips": "Cable car from Nuevo Tingo takes 20min. Full ruins circuit takes 2-3hrs. Chachapoyas city is the base (45min from cable car). Combine with Gocta waterfall nearby.",
        "trail_coords": [],
        "wildlife": ["Cock-of-the-rock", "Spectacled bear (rare)", "Cloud forest birds"],
    },
    {
        "name": "Gocta Waterfall Hike",
        "region": "Amazonas",
        "lat": -6.0069, "lon": -77.9047,
        "difficulty": "Moderate",
        "duration": "1 day",
        "elevation_m": 2531,
        "description": "One of the world's tallest waterfalls (771m total drop, two tiers). Hike through cloud forest from Cocachimba village. The upper falls are more dramatic; the lower falls are more accessible.",
        "tips": "Two trailheads: Cocachimba (lower falls, 4km round trip) and San Pablo de Valera (upper falls, 8km). Guides available in both villages. Bring rain gear.",
        "trail_coords": [],
        "wildlife": ["Cock-of-the-rock", "Torrent duck", "Andean condor"],
    },
    {
        "name": "Chachapoyas Cloud Forest Loop",
        "region": "Amazonas",
        "lat": -6.2318, "lon": -77.8686,
        "difficulty": "Moderate",
        "duration": "2-3 days",
        "elevation_m": 2335,
        "description": "Multi-day loop through the cloud forests around Chachapoyas combining Chachapoya archaeological sites, sarcophagi cliffs (Karajia), and primary cloud forest with outstanding biodiversity.",
        "tips": "Karajia sarcophagi require a guide and short cliff-side hike. Leymebamba museum houses mummies from Laguna de los Cóndores. Rainy season Nov-Apr means muddy trails.",
        "trail_coords": [],
        "wildlife": ["Spectacled bear", "Cock-of-the-rock", "Yellow-tailed woolly monkey"],
    },
    {
        "name": "Huascarán Basecamp Trek",
        "region": "Ancash",
        "lat": -9.1219, "lon": -77.6097,
        "difficulty": "Hard",
        "duration": "2-3 days",
        "elevation_m": 4800,
        "description": "Trek to the base of Huascarán (6768m), Peru's highest peak and the world's highest tropical mountain. The route passes through Llanganuco lakes (turquoise glacial lakes between Huascarán and Chopicalqui).",
        "tips": "Start from Yungay via Llanganuco road. Acclimatize in Huaraz first (3250m). The full mountaineering ascent requires technical skill and guides. Basecamp trek is non-technical.",
        "trail_coords": [],
        "wildlife": ["Andean condor", "Puna hawk", "Viscacha", "White-tailed deer"],
    },
    {
        "name": "Pastoruri Glacier Trek",
        "region": "Ancash",
        "lat": -9.9778, "lon": -77.2094,
        "difficulty": "Easy",
        "duration": "1 day",
        "elevation_m": 5240,
        "description": "Accessible high-altitude glacier walk at 5240m in Huascarán National Park. The Puya Raimondi plants (world's largest bromeliad, blooms every 80-100 years) line the approach road. The glacier has retreated significantly but remains dramatic.",
        "tips": "Day trip from Huaraz. Mandatory to go with tour operator. Altitude is extreme — acclimatize 2+ days in Huaraz. Warm layers essential. Horses available for part of route.",
        "trail_coords": [],
        "wildlife": ["Viscacha", "Puna ibis", "Andean condor", "Puya Raimondi plants"],
    },
    {
        "name": "Chavin de Huantar Circuit",
        "region": "Ancash",
        "lat": -9.5931, "lon": -77.1772,
        "difficulty": "Easy",
        "duration": "1-2 days",
        "elevation_m": 3177,
        "description": "UNESCO World Heritage Chavín ruins combined with the Tunnel Trek — a high-mountain route crossing Kahuish Pass (4518m) between Huaraz and Chavín through pristine Andean landscape.",
        "tips": "Tunnel Trek is 2 days each way from Huaraz. Ruins visit is easy from Chavín village. Combine with Laguna Querococha viewpoint on the way.",
        "trail_coords": [],
        "wildlife": ["Andean condor", "Puna hawk", "White-tailed deer"],
    },
    {
        "name": "Cajamarca Highland Walk",
        "region": "Cajamarca",
        "lat": -7.1641, "lon": -78.5128,
        "difficulty": "Easy",
        "duration": "1-2 days",
        "elevation_m": 2750,
        "description": "Cultural highland walk around Cajamarca, site of Atahualpa's capture in 1532. Day hikes to Cumbemayo aqueduct (pre-Inca stone channel), Otuzco windows, and Santa Apolonia hill overlooking the city.",
        "tips": "Cajamarca is Peru's best-kept secret for colonial history + mild hiking. Cumbemayo is 20km from city — mototaxi or tour recommended. Excellent dairy food in region.",
        "trail_coords": [],
        "wildlife": ["Andean condor", "Barn owl", "Andean fox"],
    },
    {
        "name": "Kuélap to Leymebamba Multi-day",
        "region": "Amazonas",
        "lat": -6.6881, "lon": -77.9025,
        "difficulty": "Hard",
        "duration": "4-5 days",
        "elevation_m": 3200,
        "description": "Challenging multi-day trek connecting the Kuelap fortress to Leymebamba village via cloud forest trails, Chachapoya ruins, and the legendary Laguna de los Cóndores where 200+ mummies were discovered in 1997.",
        "tips": "Very remote — guide and mule support essential. Trail poorly marked. Leymebamba museum is unmissable. Rainy Nov-Apr makes trails very muddy. Dry season Jun-Sep ideal.",
        "trail_coords": [],
        "wildlife": ["Spectacled bear", "Yellow-tailed woolly monkey", "Andean condor", "Giant otter (lake)"],
    },
]

COUNTRY_HIKES: dict[str, list] = {
    "Ecuador": ECUADOR_HIKES,
    "Peru": PERU_HIKES,
}

COUNTRY_FOOD = {
    "Ecuador": {
        "history": (
            "Ecuador's food culture is rooted in thousands of years of indigenous Andean tradition, "
            "blended with Spanish colonial influences and distinct coastal, highland, and Amazonian ingredients. "
            "The Inca empire brought techniques like freeze-drying potatoes (chuño) and preserving meats, "
            "while Spanish colonizers introduced pork, wheat, and dairy. Today Ecuadorian cuisine varies "
            "dramatically across its three mainland regions: the Costa (coast), Sierra (highlands), and "
            "Oriente (Amazon). Ecuador is also one of the world's top producers of fine-flavor cacao — "
            "the Arriba Nacional variety is prized globally and has been cultivated for over 5,000 years."
        ),
        "dishes": [
            "Ceviche — fresh seafood marinated in citrus, a coastal staple served with popcorn and chifles",
            "Llapingachos — pan-fried potato and cheese cakes from the Sierra, served with chorizo and fried egg",
            "Seco de pollo — slow-cooked chicken stew with beer, cilantro, and achiote",
            "Encebollado — hearty tuna and onion soup with yuca, considered Ecuador's hangover cure",
            "Fritada — deep-fried pork served with hominy (mote), plantains, and llapingachos",
            "Cuy — roasted guinea pig, a traditional Andean delicacy served whole on special occasions",
            "Sopa de bolas de verde — plantain dumpling soup, a coastal comfort food",
            "Fanesca — a rich soup made from 12 grains and salted cod, eaten only during Holy Week (Easter)",
        ],
        "snacks_and_street_food": [
            "Patacones — twice-fried green plantain slices, served with hogao (tomato-onion sauce) or cheese",
            "Chifles — thin salted plantain chips, served alongside ceviche",
            "Empanadas de viento — fried pastries filled with cheese, topped with powdered sugar",
            "Humitas — steamed fresh corn cakes wrapped in corn husks, sweet or savory",
            "Quimbolitos — steamed sweet corn dough with raisins, wrapped in achira leaves",
            "Morocho — warm spiced corn drink thickened with cracked corn, popular in the Sierra",
            "Canguil — Andean popcorn, often served alongside ceviche on the coast",
            "Maíz tostado — toasted corn kernels, a crunchy highland snack",
        ],
        "drinks": [
            "Colada morada — thick purple corn and fruit drink spiced with cinnamon and cloves, made for Day of the Dead",
            "Chicha de jora — fermented corn beer, an ancient Andean drink still made in rural communities",
            "Naranjilla juice — tart citrus-like fruit (lulo) blended into a bright green juice",
            "Canelazo — hot sugarcane spirit (aguardiente) mixed with cinnamon tea, served at highland festivals",
            "Agua de guayusa — caffeinated leaf tea from the Amazon, used ceremonially by indigenous Kichwa people",
            "Hot chocolate — Ecuador's cacao heritage makes its hot chocolate exceptional; often served with bread and cheese for breakfast",
        ],
        "note": "Cuisine varies dramatically by region: coastal (Costa), Andean highland (Sierra), and Amazon (Oriente). The Sierra tends toward hearty stews and potato dishes; the coast is seafood-forward; the Oriente features yuca, plantains, and jungle game.",
    },
    "Peru": {
        "history": (
            "Peru is widely regarded as one of the world's great culinary destinations — Lima regularly "
            "appears among the world's top restaurant cities. Peruvian food history spans 10,000+ years "
            "of cultivation in the Andes, where the potato originated (over 3,000 native varieties still exist). "
            "The Inca empire developed sophisticated agricultural terracing and food preservation (freeze-drying "
            "potatoes into chuño, drying meat into charqui). Spanish colonization in the 1500s brought new "
            "ingredients — olives, wine grapes, beef, chicken — that fused with indigenous traditions. "
            "Later waves of African, Chinese (Chifa cuisine), Japanese (Nikkei cuisine), and Italian immigration "
            "each added distinct layers, making modern Peruvian cuisine one of the most diverse and creative "
            "in the world. Ceviche has been recognized by UNESCO as an Intangible Cultural Heritage."
        ),
        "dishes": [
            "Ceviche — Peru's national dish; raw fish cured in lime juice with ají amarillo, red onion, and cilantro, served with choclo and sweet potato",
            "Lomo saltado — stir-fried beef with tomatoes, onions, soy sauce, and french fries; a Chinese-Peruvian (Chifa) fusion classic",
            "Ají de gallina — creamy shredded chicken in a rich ají amarillo and bread sauce, served over rice",
            "Causa rellena — chilled layered yellow potato cake filled with chicken, tuna, or avocado",
            "Anticuchos — grilled beef heart skewers marinated in cumin and ají panca, a beloved street food",
            "Rocoto relleno — spicy red rocoto peppers stuffed with ground meat, egg, and cheese then baked",
            "Tiradito — sashimi-style thin-sliced raw fish dressed in a spicy citrus sauce (Japanese-Peruvian Nikkei cuisine)",
            "Pachamanca — meats, potatoes, and corn slow-cooked underground on hot stones, an ancient Andean technique",
            "Sopa a la criolla — thin beef noodle soup with milk, egg, and ají amarillo, a Lima comfort classic",
        ],
        "snacks_and_street_food": [
            "Picarones — pumpkin and sweet potato doughnuts drizzled with chancaca (molasses) syrup",
            "Tamales — steamed corn dough parcels filled with chicken or pork, wrapped in banana leaves",
            "Pan con chicharrón — fried pork belly sandwich with sweet potato and salsa criolla, a Lima breakfast staple",
            "Choclo con queso — giant Andean corn on the cob served with fresh white cheese, sold at every highland market",
            "Tequeños — fried cheese-stuffed bread sticks, a popular party snack",
            "Salchipapas — sliced hot dogs with french fries, the quintessential Peruvian fast food",
            "Canchita — toasted dried corn kernels served as a snack alongside ceviche",
            "Mazamorra morada — purple corn pudding dessert thickened with sweet potato starch and spiced with cinnamon",
        ],
        "drinks": [
            "Pisco Sour — Peru's iconic cocktail: Pisco brandy shaken with lime juice, simple syrup, egg white, and Angostura bitters",
            "Chicha morada — non-alcoholic purple corn beverage boiled with pineapple, cinnamon, and cloves, served cold",
            "Inca Kola — bright yellow bubble-gum-flavored Peruvian soda; more popular than Coca-Cola in Peru",
            "Chicha de jora — ancient fermented corn beer still brewed in Andean communities, often served in ceramic cups",
            "Emoliente — warm herbal street drink made from barley, flaxseed, and medicinal plants, sold from carts in Lima",
            "Mate de coca — coca leaf tea, widely drunk at altitude to ease altitude sickness; legal and mild",
        ],
        "note": "Peru's culinary diversity spans four macro-regions: Lima (coastal, Chifa, Nikkei), the Andes (hearty potato and grain dishes), the Amazon (yuca, plantains, freshwater fish), and Arequipa (known as Peru's culinary capital with its own distinct cuisine).",
    },
}

COUNTRY_HISTORY = {
    "Ecuador": {
        "summary": (
            "Ecuador sits at the crossroads of ancient Andean civilizations, Spanish colonial empire, "
            "and modern South American independence. Its name comes from the equator that runs through it."
        ),
        "timeline": [
            ("10,000+ BCE", "Early human settlements in the Andes and coast; cultivation of crops including maize, potatoes, and quinoa"),
            ("3,500 BCE", "Valdivia culture on the coast — one of the oldest ceramic traditions in the Americas"),
            ("1,000–1,400 CE", "Caras, Puruhá, Cañari, and other cultures develop complex societies across the Andes"),
            ("1463–1533", "Inca expansion northward; Quito becomes a major northern capital of the Inca Empire (Tawantinsuyu)"),
            ("1533", "Spanish conquistador Sebastián de Belalcázar defeats the Inca and founds Spanish Quito on the ruins of the Inca city"),
            ("1563", "Quito becomes the seat of the Royal Audiencia of Quito, a key administrative center of the Spanish colonial empire"),
            ("1736–1744", "French Geodesic Mission confirms the Earth is an oblate spheroid by measuring near the equator in Ecuador"),
            ("1809", "First cry of independence (Primer Grito) in Quito on August 10 — now celebrated as Independence Day"),
            ("1822", "Battle of Pichincha: Simón Bolívar's forces under Antonio José de Sucre defeat the Spanish; Ecuador joins Gran Colombia"),
            ("1830", "Ecuador separates from Gran Colombia and becomes an independent republic"),
            ("1859–1875", "Gabriel García Moreno's conservative theocratic government modernizes infrastructure but suppresses liberalism"),
            ("1895", "Liberal Revolution led by Eloy Alfaro; separation of church and state, secular education, civil marriage"),
            ("1941", "Border war with Peru results in Ecuador losing much of its Amazon territory under the Rio Protocol (1942)"),
            ("1972", "Oil discovered in the Amazon; Ecuador joins OPEC and experiences an oil boom that transforms the economy"),
            ("1998", "New constitution; peace treaty with Peru finally resolves the border dispute"),
            ("2008", "Rafael Correa's government passes a new constitution granting rights to nature (first country to do so)"),
            ("2024", "Ecuador faces escalating gang violence and cartel activity, leading to a state of emergency and military deployments"),
        ],
        "key_facts": [
            "Capital: Quito (one of the highest capitals in the world at 2,850m)",
            "The Galápagos Islands, part of Ecuador, inspired Charles Darwin's theory of evolution (1835 visit)",
            "Ecuador was the first country in the world to grant constitutional rights to nature (2008)",
            "The 'Avenue of the Volcanoes' — a row of massive Andean volcanoes including Chimborazo and Cotopaxi — runs through the center of the country",
            "Chimborazo (6,268m) is the farthest point from Earth's center due to the equatorial bulge — farther than Everest",
        ],
    },
    "Peru": {
        "summary": (
            "Peru is home to one of the ancient world's most sophisticated civilizations — the Inca Empire — "
            "and was the center of Spanish colonial power in South America for nearly 300 years. "
            "Its history spans 12,000 years of continuous human habitation."
        ),
        "timeline": [
            ("10,000+ BCE", "Hunter-gatherers settle the Andes and coast; earliest evidence of human habitation at Huanta caves"),
            ("3,000 BCE", "Caral civilization emerges in the coastal valleys — one of the oldest civilizations in the Americas, contemporary with ancient Egypt"),
            ("900–200 BCE", "Chavín culture creates a pan-Andean religious and artistic tradition centered at Chavín de Huántar"),
            ("200 BCE–600 CE", "Nazca Lines created on the coastal desert — vast geoglyphs still not fully explained"),
            ("600–1000 CE", "Wari (Huari) Empire expands across the Andes, precursor to Inca administrative techniques"),
            ("1438–1533", "Inca Empire (Tawantinsuyu) at its height — stretching 4,000km from Colombia to Chile; Machu Picchu built c.1450"),
            ("1532", "Francisco Pizarro arrives; captures Inca emperor Atahualpa at Cajamarca; Inca Empire collapses"),
            ("1535", "Lima founded by Pizarro as Ciudad de los Reyes; becomes capital of the Viceroyalty of Peru"),
            ("1569–1581", "Viceroy Francisco de Toledo consolidates Spanish colonial power; forced labor (mita) system established in mines"),
            ("1780–1781", "Túpac Amaru II leads the largest indigenous rebellion against Spanish rule; defeated and executed in Cusco"),
            ("1821", "José de San Martín declares Peruvian independence on July 28; Simón Bolívar completes liberation by 1824"),
            ("1879–1884", "War of the Pacific against Chile; Peru loses the Tarapacá region and suffers devastating defeat"),
            ("1911", "Hiram Bingham 'discovers' Machu Picchu (already known to locals) and brings it to world attention"),
            ("1968–1980", "Military government of Juan Velasco Alvarado nationalizes industries and undertakes land reform"),
            ("1980–2000", "Internal conflict with Shining Path (Sendero Luminoso) Maoist guerrillas and MRTA kills ~70,000 people"),
            ("1990–2000", "Alberto Fujimori's authoritarian presidency; captures Shining Path leader Abimael Guzmán (1992) but ends in corruption scandal"),
            ("2000s–present", "Democracy restored; strong economic growth driven by mining and tourism; Lima emerges as a global culinary capital"),
            ("2021", "Pedro Castillo elected president; impeached and arrested 2022 amid political turmoil"),
        ],
        "key_facts": [
            "Capital: Lima (home to over 10 million people, roughly 1/3 of Peru's population)",
            "Machu Picchu was built c.1450 CE and abandoned ~100 years later; rediscovered by the outside world in 1911",
            "Peru has 3 UNESCO World Heritage Sites related to the Inca: Machu Picchu, Cusco, and the Chavín archaeological site",
            "The Amazon River begins in Peru (from the Apurímac River headwaters near Arequipa)",
            "Lake Titicaca (shared with Bolivia) is the world's highest navigable lake at 3,812m",
            "Peru has 84 of the world's 117 life zones (ecosystems), making it one of the most biodiverse countries on Earth",
            "The potato originated in Peru — over 3,000 native varieties are still grown in the Andean highlands",
        ],
    },
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
            area = hike.get('province') or hike.get('region', '—')
            st.caption(f"📍 {area} · {hike['difficulty']} · {hike['duration']}")
            st.caption(f"⛰️ Max elevation: {hike['elevation_m']:,}m")
            st.markdown(hike["description"])
            st.markdown("**Tips:**")
            st.caption(hike["tips"])
            if hike.get("wildlife"):
                st.markdown("**Wildlife you may see:**")
                st.caption(", ".join(hike["wildlife"]))

        with col2:
            m = folium.Map(location=[hike["lat"], hike["lon"]], zoom_start=10, tiles="OpenStreetMap")
            folium.Marker(
                [hike["lat"], hike["lon"]],
                popup=folium.Popup(f"<b>{hike['name']}</b><br>{hike['difficulty']} · {hike['duration']}", max_width=200),
                tooltip=hike["name"],
                icon=folium.Icon(color="green", icon="leaf", prefix="glyphicon"),
            ).add_to(m)
            st_folium(m, use_container_width=True, height=600, key=f"hike_map_{idx}")


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


def _render_safety_results_panel(result: dict, label: str = "") -> None:
    """Render all safety scoring outputs as a clean tabbed panel."""
    import datetime as _dt

    score = result.get("safety_score")
    band = result.get("risk_band", "—")
    band_emoji = {"Low Risk": "🟢", "Moderate Risk": "🟡", "Elevated Risk": "🟠", "High Risk": "🔴"}.get(band, "⚪")
    model_version = result.get("model_version", "—")

    if label:
        st.markdown(f"**{label}**")

    # Top-line score
    m_col1, m_col2, m_col3 = st.columns(3)
    m_col1.metric("Safety Score", f"{score:.1f}/100" if score is not None else "—")
    m_col2.metric("Risk Band", f"{band_emoji} {band}")
    m_col3.metric("Model", model_version)

    # Tabs for each dimension
    details = result.get("details", {})
    weather = result.get("weather_risk", {})
    ecuador = result.get("ecuador_risk", {})
    peru_r  = result.get("peru_risk", {})
    lgbt    = result.get("lgbt_safety") or result.get("details", {}).get("lgbt_safety", {})

    # Build tab list dynamically based on what's available
    tab_labels = ["📊 Score Details"]
    if weather and not weather.get("error"):
        tab_labels.append("🌦️ Weather")
    if ecuador and ecuador.get("applicable"):
        tab_labels.append("🐆 Ecuador")
    if peru_r and peru_r.get("applicable"):
        tab_labels.append("🐆 Peru")
    if lgbt and "lgbt_safety_score" in lgbt:
        tab_labels.append("🏳️‍🌈 LGBT")

    tabs = st.tabs(tab_labels)
    tab_idx = 0

    # ── Score Details tab ──────────────────────────────────────────────────
    with tabs[tab_idx]:
        tab_idx += 1
        d_col1, d_col2 = st.columns(2)
        with d_col1:
            st.markdown("**Model breakdown**")
            mlp = details.get("mlp_score_v6")
            rf  = details.get("rf_score_v6")
            v9b = details.get("v9b_score")
            if mlp is not None:
                st.metric("MLP v6", f"{mlp:.1f}")
            if rf is not None:
                st.metric("Random Forest v6", f"{rf:.1f}")
            if v9b is not None:
                st.metric("v9b MLP", f"{v9b:.1f}")
            else:
                v9b_err = details.get("v9b_error", "artifacts missing or failed to load")
                st.caption(f"⚠️ v9b not loaded: {v9b_err}")
            st.caption(f"Active model: {result.get('model_version', '—')}")
            agreement = details.get("agreement_band", "—")
            spread = details.get("model_spread")
            st.caption(f"Model agreement: **{agreement}**" + (f" (spread: {spread:.1f})" if spread else ""))
        with d_col2:
            st.markdown("**Location**")
            lat = result.get("latitude")
            lon = result.get("longitude")
            country = result.get("country", "—")
            if lat and lon:
                st.caption(f"📍 {lat:.4f}, {lon:.4f}")
            st.caption(f"🌍 {country}")
            feat_count = details.get("feature_count")
            if feat_count:
                st.caption(f"Features used: {feat_count}")

        # Feature values expander
        features = details.get("features") or details.get("features_used") or {}
        if features:
            with st.expander("🔬 Feature values used in prediction", expanded=False):
                if isinstance(features, dict):
                    feat_rows = sorted(features.items())
                    for fname, fval in feat_rows:
                        try:
                            st.caption(f"**{fname}**: {fval:.4f}" if isinstance(fval, float) else f"**{fname}**: {fval}")
                        except Exception:
                            st.caption(f"**{fname}**: {fval}")
                else:
                    st.json(features)

        # Full raw result expander (replaces old debug JSON)
        with st.expander("🗂️ Full prediction output (all fields)", expanded=False):
            st.json({k: v for k, v in result.items() if k != "details"})
            if details:
                st.markdown("**details:**")
                st.json(details)

    # ── Weather tab ────────────────────────────────────────────────────────
    if weather and not weather.get("error") and tab_idx <= len(tabs) - 1:
        with tabs[tab_idx]:
            tab_idx += 1
            w_score = weather.get("weather_risk_score", "—")
            w_label = weather.get("weather_risk_label", "—")
            st.metric("Weather Risk", f"{w_score}/5 — {w_label}")
            assessment = weather.get("travel_month_assessment", "")
            if assessment:
                st.info(assessment)
            risks = weather.get("risks", [])
            if risks:
                st.markdown("**Active risks this month:**")
                for r in risks:
                    sev = r.get("severity", 0)
                    sev_bar = "🔴" * min(sev, 5)
                    with st.expander(f"{r['type'].replace('_',' ').title()} {sev_bar}", expanded=sev >= 4):
                        st.write(r.get("description", ""))

    # ── Ecuador tab ────────────────────────────────────────────────────────
    if ecuador and ecuador.get("applicable") and tab_idx <= len(tabs) - 1:
        with tabs[tab_idx]:
            tab_idx += 1
            e_col1, e_col2, e_col3 = st.columns(3)
            e_col1.metric("Overall Risk", f"{ecuador.get('overall_risk','—')}/5")
            e_col2.metric("Crime Risk", f"{ecuador.get('crime_risk','—')}/5")
            e_col3.metric("Wildlife Risk", f"{ecuador.get('wildlife_risk','—')}/5")
            st.caption(f"Province: **{ecuador.get('province','—')}** · Homicide rate: {ecuador.get('homicide_rate_per_100k','—')}/100k")
            crime_notes = ecuador.get("crime_notes","")
            if crime_notes:
                st.warning(crime_notes)

    # ── Peru tab ───────────────────────────────────────────────────────────
    if peru_r and peru_r.get("applicable") and tab_idx <= len(tabs) - 1:
        with tabs[tab_idx]:
            tab_idx += 1
            p_col1, p_col2, p_col3 = st.columns(3)
            p_col1.metric("Overall Risk", f"{peru_r.get('overall_risk','—')}/5")
            p_col2.metric("Crime Risk", f"{peru_r.get('crime_risk','—')}/5")
            p_col3.metric("Wildlife Risk", f"{peru_r.get('wildlife_risk','—')}/5")
            st.caption(f"Region: **{peru_r.get('region','—')}** · Homicide rate: {peru_r.get('homicide_rate_per_100k','—')}/100k")
            crime_notes = peru_r.get("crime_notes","")
            if crime_notes:
                st.warning(crime_notes)

    # ── LGBT tab ───────────────────────────────────────────────────────────
    if lgbt and "lgbt_safety_score" in lgbt and tab_idx <= len(tabs) - 1:
        with tabs[tab_idx]:
            tab_idx += 1
            score_l = lgbt.get("lgbt_safety_score")
            labels = {
                1: "Criminalized — serious legal risk",
                2: "Hostile — discrimination common",
                3: "Neutral — limited legal protections",
                4: "Accepting — legal protections exist",
                5: "Very Safe — full legal equality",
            }
            label_l = labels.get(score_l, "—")
            legal_idx = lgbt.get("lgbt_legal_index")
            confidence = lgbt.get("lgbt_confidence") or lgbt.get("confidence", "—")
            criminalized = lgbt.get("criminalized", False)
            death_risk = lgbt.get("death_penalty_risk", False)

            l_col1, l_col2 = st.columns(2)
            l_col1.metric("LGBT Safety Score", f"{score_l}/5" if score_l else "—")
            if legal_idx is not None:
                l_col2.metric("Legal Index", f"{legal_idx:.1f}/100")
            st.markdown(f"**{label_l}**")
            st.caption(f"Data confidence: {confidence}")

            if death_risk:
                st.error("🚨 Death penalty or corporal punishment may apply to same-sex relations in this country.")
            elif criminalized:
                st.warning("⚠️ Same-sex relations are criminalized in this country. Exercise extreme caution.")

            st.caption("Source: ILGA World, Rainbow Map, and WayFinder LGBT classifier (1 = Criminalized → 5 = Very Safe)")



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

    tab_map, tab_hikes, tab_wildlife, tab_food, tab_history = st.tabs(["🗺️ Map", "🥾 Hikes", "🐆 Wildlife", "🍽️ Food", "🏛️ History"])

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

        map_data = st_folium(m, use_container_width=True, height=900, key="explore_main_map")

        # ── Capture map click and reverse-geocode ─────────────────────────
        clicked = map_data.get("last_clicked") if map_data else None
        if clicked and clicked.get("lat") is not None and clicked.get("lng") is not None:
            c_lat, c_lng = clicked["lat"], clicked["lng"]
            # Only update if coords actually changed to avoid infinite reruns
            if (c_lat != st.session_state.get("explore_click_lat")
                    or c_lng != st.session_state.get("explore_click_lon")):
                st.session_state["explore_click_lat"] = c_lat
                st.session_state["explore_click_lon"] = c_lng
                # Reverse-geocode via Nominatim
                import requests as _req
                try:
                    rg = _req.get(
                        "https://nominatim.openstreetmap.org/reverse",
                        params={"lat": c_lat, "lon": c_lng, "format": "json"},
                        headers={"User-Agent": "WayFinder/1.0"},
                        timeout=3,
                    )
                    if rg.ok and rg.json().get("display_name"):
                        parts = rg.json()["display_name"].split(",")
                        st.session_state["explore_click_name"] = parts[0].strip()
                    else:
                        st.session_state["explore_click_name"] = f"{c_lat:.4f}, {c_lng:.4f}"
                except Exception:
                    st.session_state["explore_click_name"] = f"{c_lat:.4f}, {c_lng:.4f}"
                st.rerun()

        # ── Safety scoring from explore map ────────────────────────────────
        st.divider()
        st.markdown("### 🛡️ Safety Score")
        score_col1, score_col2 = st.columns([3, 1])
        with score_col1:
            explore_dest = st.text_input(
                "Score a location",
                placeholder="e.g. Quito, Cusco, Iquitos…",
                key="explore_score_input",
                value=st.session_state.get("explore_click_name", ""),
                label_visibility="collapsed",
            )
        with score_col2:
            score_btn = st.button("Run Score", use_container_width=True, key="explore_run_score")

        # Show clicked location info
        click_lat = st.session_state.get("explore_click_lat")
        click_lon = st.session_state.get("explore_click_lon")
        click_name = st.session_state.get("explore_click_name", "")
        if click_lat is not None:
            st.info(
                f"📍 **Selected from map:** {click_name}  \n"
                f"Lat: `{click_lat:.5f}` · Lon: `{click_lon:.5f}`"
            )

        # Month selector for travel month assessment
        month_names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        sel_month = st.selectbox(
            "Travel month (for weather assessment)",
            options=list(range(1, 13)),
            format_func=lambda x: month_names[x-1],
            index=datetime.date.today().month - 1,
            key="explore_travel_month",
        )

        if score_btn:
            import requests as _req
            lat = lon = country = None
            location_name = explore_dest

            if explore_dest:
                # Forward-geocode the typed destination
                try:
                    geo_r = _req.get(
                        "https://nominatim.openstreetmap.org/search",
                        params={"q": explore_dest, "format": "json", "limit": 1},
                        headers={"User-Agent": "WayFinder/1.0"},
                        timeout=5,
                    )
                    if geo_r.ok and geo_r.json():
                        geo = geo_r.json()[0]
                        lat = float(geo["lat"])
                        lon = float(geo["lon"])
                        country = geo.get("display_name", "").split(",")[-1].strip()
                    else:
                        st.warning(f"Could not find '{explore_dest}' — try a more specific name.")
                except Exception as e:
                    st.error(f"Geocoding failed: {e}")
            elif (st.session_state.get("explore_click_lat") is not None
                    and st.session_state.get("explore_click_lon") is not None):
                # Use click coordinates directly — skip forward geocode
                lat = st.session_state["explore_click_lat"]
                lon = st.session_state["explore_click_lon"]
                location_name = st.session_state.get("explore_click_name", f"{lat:.4f}, {lon:.4f}")
                country = active_country

            if lat is not None and lon is not None:
                _ss = get_safety_service()
                try:
                    req = SafetyRequest(
                        latitude=lat,
                        longitude=lon,
                        country=country,
                        location_name=location_name,
                        travel_month=sel_month,
                    )
                    result = _ss.assess_request(req, include_details=True)
                    st.session_state["explore_safety_result"] = result
                    st.session_state["explore_scored_location"] = location_name
                    st.rerun()
                except Exception as e:
                    st.error(f"Scoring failed: {e}")

        # Display explore safety result
        explore_result = st.session_state.get("explore_safety_result")
        if explore_result and explore_result.get("success"):
            _render_safety_results_panel(explore_result, label=st.session_state.get("explore_scored_location",""))
        elif explore_result:
            st.error(f"Scoring failed: {explore_result.get('error')}")

    with tab_hikes:
        st.markdown(f"### {st.session_state.get('explore_country','Ecuador')} Hikes")
        st.caption("Select a hike to see details and view it on the map.")
        _render_hikes_tab()

    with tab_wildlife:
        st.markdown(f"### {st.session_state.get('explore_country','Ecuador')} Wildlife Threats")
        _render_wildlife_tab()

    # ── Food tab ────────────────────────────────────────────────────────────
    with tab_food:
        country = st.session_state.get("explore_country", "Ecuador")
        food = COUNTRY_FOOD.get(country)
        if food:
            st.markdown(f"## 🍽️ {country} — Food & Cuisine")
            st.write(food["history"])
            st.divider()
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                st.markdown("### Main Dishes")
                for item in food["dishes"]:
                    st.markdown(f"- {item}")
            with col_f2:
                st.markdown("### Snacks & Street Food")
                for item in food["snacks_and_street_food"]:
                    st.markdown(f"- {item}")
            st.divider()
            st.markdown("### Drinks")
            for item in food["drinks"]:
                st.markdown(f"- {item}")
            st.divider()
            st.caption(food["note"])
            st.info("🚧 More details — restaurant recommendations, dietary notes, food safety tips, and regional breakdowns — will be added in a future update.")
        else:
            st.info(f"Food information for {country} coming soon.")

    # ── History tab ─────────────────────────────────────────────────────────
    with tab_history:
        country = st.session_state.get("explore_country", "Ecuador")
        hist = COUNTRY_HISTORY.get(country)
        if hist:
            st.markdown(f"## 🏛️ {country} — History")
            st.write(hist["summary"])
            st.divider()
            st.markdown("### Timeline")
            for year, event in hist["timeline"]:
                st.markdown(f"**{year}** — {event}")
            st.divider()
            st.markdown("### Key Facts")
            for fact in hist["key_facts"]:
                st.markdown(f"- {fact}")
        else:
            st.info(f"History information for {country} coming soon.")


def render_chat_page() -> None:
    try:
        st.set_page_config(layout="wide", page_title="WayFinder", page_icon="✈️")
    except Exception:
        pass
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
        ("explore_safety_result", None),
        ("explore_scored_location", ""),
        ("explore_click_lat", None),
        ("explore_click_lon", None),
        ("explore_click_name", ""),
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
