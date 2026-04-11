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

        if st.button("🌿 Explore Ecuador", use_container_width=True, key="btn_explore"):
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


def _render_hikes_tab() -> None:
    import folium
    from streamlit_folium import st_folium

    selected_hike = st.session_state.get("selected_hike_idx")

    # Hike selector
    hike_names = [h["name"] for h in ECUADOR_HIKES]
    chosen = st.selectbox("Choose a hike:", ["— Select a hike —"] + hike_names, key="hike_selector")

    if chosen != "— Select a hike —":
        idx = hike_names.index(chosen)
        hike = ECUADOR_HIKES[idx]
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
            m = folium.Map(location=[hike["lat"], hike["lon"]], zoom_start=12, tiles="CartoDB dark_matter")
            folium.Marker(
                [hike["lat"], hike["lon"]],
                popup=hike["name"],
                tooltip=hike["name"],
                icon=folium.Icon(color="green", icon="tree-conifer", prefix="glyphicon"),
            ).add_to(m)
            st_folium(m, use_container_width=True, height=400, key=f"hike_map_{idx}")


def _render_wildlife_tab() -> None:
    from models.safety.submodels.ecuador_safety import _WILDLIFE_THREATS

    # Group by type
    by_type = {}
    for t in _WILDLIFE_THREATS:
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
        st.subheader("🌿 Explore Ecuador")

    tab_map, tab_hikes, tab_wildlife = st.tabs(["🗺️ Map", "🥾 Hikes", "🐆 Wildlife"])

    with tab_map:
        m = folium.Map(location=[-1.5, -78.0], zoom_start=7, tiles="CartoDB dark_matter")
        # Add destination pin if selected
        sel = st.session_state.get("selected_location")
        if sel and sel.get("lat"):
            folium.Marker(
                [sel["lat"], sel["lon"]],
                popup=sel.get("city", "Destination"),
                icon=folium.Icon(color="red", icon="map-marker"),
            ).add_to(m)
        st_folium(m, use_container_width=True, height=700, key="explore_main_map")

    with tab_hikes:
        st.markdown("### Ecuador Hikes")
        st.caption("Select a hike to see details and view it on the map.")
        _render_hikes_tab()

    with tab_wildlife:
        st.markdown("### Ecuador Wildlife Threats")
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
