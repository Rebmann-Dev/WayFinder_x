"""Rebuilt Explore page — single scrollable view with expandable sections."""

import json
import logging
from pathlib import Path

import streamlit as st

log = logging.getLogger("wayfinder.explore")

_COUNTRIES_DIR = Path(__file__).resolve().parent.parent / "data" / "countries"

_COUNTRY_CODE_MAP = {
    "Ecuador": "ec",
    "Peru": "pe",
}

# Continent subfolders to search (parallel subagent may move JSONs here)
_CONTINENT_FOLDERS = ["south_america", "north_america", "europe", "asia", "africa", "oceania"]

# Flag emojis
_FLAGS = {"ec": "\U0001f1ea\U0001f1e8", "pe": "\U0001f1f5\U0001f1ea"}


def _load_country_json(country_code: str) -> dict | None:
    """Load country JSON, checking continent subfolders then root."""
    cc = country_code.lower().strip()
    base = _COUNTRIES_DIR

    # Check each continent folder
    for continent in _CONTINENT_FOLDERS:
        path = base / continent / f"{cc}.json"
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                log.error("Failed to load country JSON %s: %s", path, e)
                return None

    # Fallback: check root
    path = base / f"{cc}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            log.error("Failed to load country JSON %s: %s", path, e)
            return None

    # Try longer name match (e.g. "ecuador.json" from code "ec")
    for p in base.glob("*.json"):
        if p.stem.lower().startswith(cc):
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                log.error("Failed to load country JSON %s: %s", p, e)
                return None
    for continent in _CONTINENT_FOLDERS:
        continent_dir = base / continent
        if continent_dir.is_dir():
            for p in continent_dir.glob("*.json"):
                if p.stem.lower().startswith(cc):
                    try:
                        return json.loads(p.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError) as e:
                        log.error("Failed to load country JSON %s: %s", p, e)
                        return None

    return None


def _get(data, dotpath, default=None):
    """Resolve a dot-separated path into nested dicts."""
    if data is None:
        return default
    node = data
    for part in dotpath.split("."):
        if not isinstance(node, dict):
            return default
        node = node.get(part)
        if node is None:
            return default
    return node


def _no_data():
    st.caption("\U0001f4e1 More data coming soon")


def _render_cards(items: list, fields: list[tuple[str, str]], title_key: str = "name"):
    """Render a list of dicts as card-style blocks."""
    if not items:
        _no_data()
        return
    for item in items:
        name = item.get(title_key, "Unknown")
        st.markdown(f"**{name}**")
        cols = st.columns(min(len(fields), 4))
        for i, (key, label) in enumerate(fields):
            val = item.get(key)
            if val is not None:
                cols[i % len(cols)].caption(f"{label}: {val}")
        desc = item.get("description", "")
        if desc:
            st.caption(desc)
        best = item.get("best_months")
        if best:
            if isinstance(best, list):
                best = ", ".join(str(m) for m in best)
            st.caption(f"\U0001f4c5 Best months: {best}")
        st.divider()


def render_explore_page() -> None:
    """Main explore page entry point — called from chat_page when in explore mode."""

    # ── Auto-detect country from sidebar destination ──────────────────
    destination = st.session_state.get("destination_airport", {})

    country_name = None
    country_code = None

    if isinstance(destination, dict):
        country_name = destination.get("country", "")
        country_map = {
            "Ecuador": "ecuador",
            "Peru": "peru",
            "EC": "ecuador",
            "PE": "peru",
            "ec": "ecuador",
            "pe": "peru",
        }
        country_code = country_map.get(country_name) or country_map.get(
            destination.get("country_code", "")
        )
    elif isinstance(destination, str) and destination:
        country_map = {
            "Ecuador": "ecuador",
            "Peru": "peru",
            "EC": "ecuador",
            "PE": "peru",
            "ec": "ecuador",
            "pe": "peru",
        }
        country_code = country_map.get(destination)

    # Also check destination_city session state
    if not country_code:
        dest_city = st.session_state.get("destination_city", "")
        if dest_city:
            if any(
                c in dest_city.lower()
                for c in ["quito", "guayaquil", "cuenca", "manta", "esmeraldas"]
            ):
                country_code = "ecuador"
            elif any(
                c in dest_city.lower()
                for c in ["lima", "cusco", "arequipa", "trujillo", "iquitos", "mancora"]
            ):
                country_code = "peru"

    if not country_code:
        st.info("\U0001f4cd Set a destination in the sidebar to explore country information.")
        return

    # Load JSON using new multi-folder loader
    data = _load_country_json(country_code)
    if data is None:
        st.warning(f"No data available for {country_code}.")
        return

    # ── Header ────────────────────────────────────────────────────────
    cc = _COUNTRY_CODE_MAP.get(country_code.title(), country_code[:2])
    flag = _get(data, "identity.flag_emoji") or _FLAGS.get(cc, "\U0001f30d")
    country_name = _get(data, "identity.name") or country_code.title()
    st.markdown(f"# {flag} Explore: {country_name}")

    # Quick facts bar — use correct JSON schema paths
    capital = _get(data, "identity.capital", "\u2014")
    currency = _get(data, "language_and_money.currency", "\u2014")
    language = _get(data, "language_and_money.primary_language", "\u2014")
    calling_code = _get(data, "identity.country_calling_code", "\u2014")
    driving_side = _get(data, "identity.driving_side", "\u2014")

    cols = st.columns(5)
    cols[0].metric("Capital", capital)
    cols[1].metric("Currency", currency)
    cols[2].metric("Language", language)
    cols[3].metric("Calling Code", calling_code)
    cols[4].metric("Driving Side", driving_side)

    st.divider()

    # ── Important Travel Info (always expanded) ───────────────────────
    with st.expander("\u26a0\ufe0f Important Travel Info", expanded=True):
        visa = _get(data, "entry_and_border.visa_requirements") or _get(data, "entry_and_border.visa_on_arrival")
        vaccines = _get(data, "health.recommended_vaccines") or _get(data, "health.vaccinations")
        advisory = _get(data, "safety.advisory_level") or _get(data, "safety.travel_advisory")
        emergency = _get(data, "safety.emergency_numbers") or _get(data, "safety.emergency_number")
        embassy = _get(data, "safety.us_embassy") or _get(data, "entry_and_border.us_embassy")

        if visa:
            if isinstance(visa, list):
                st.markdown("**Visa:** " + "; ".join(str(v) for v in visa))
            elif isinstance(visa, dict):
                for k, v in visa.items():
                    st.caption(f"**{k}**: {v}")
            else:
                st.markdown(f"**Visa:** {visa}")

        if vaccines:
            if isinstance(vaccines, list):
                st.markdown("**Vaccines:** " + ", ".join(str(v) if isinstance(v, str) else v.get("name", str(v)) for v in vaccines))
            else:
                st.markdown(f"**Vaccines:** {vaccines}")

        if advisory:
            st.markdown(f"**Advisory Level:** {advisory}")

        st.markdown(f"**Currency:** {currency}")

        if emergency:
            if isinstance(emergency, dict):
                parts = [f"{k}: {v}" for k, v in emergency.items()]
                st.markdown("**Emergency Numbers:** " + " | ".join(parts))
            else:
                st.markdown(f"**Emergency Numbers:** {emergency}")

        if embassy:
            if isinstance(embassy, dict):
                for k, v in embassy.items():
                    st.caption(f"**{k}**: {v}")
            else:
                st.markdown(f"**US Embassy:** {embassy}")

        if not any([visa, vaccines, advisory, emergency, embassy]):
            _no_data()

    # ── Hikes & Trekking ──────────────────────────────────────────────
    with st.expander("\U0001f3d4\ufe0f Hikes & Trekking", expanded=False):
        day_hikes = _get(data, "outdoors.top_day_hikes", [])
        multi_treks = _get(data, "outdoors.multi_day_treks", [])
        all_hikes = (day_hikes or []) + (multi_treks or [])
        if not all_hikes:
            _no_data()
        else:
            for hike in all_hikes:
                name = hike.get("name", "Unknown")
                st.markdown(f"**{name}**")
                c1, c2, c3 = st.columns(3)
                if hike.get("difficulty"):
                    c1.caption(f"Difficulty: {hike['difficulty']}")
                if hike.get("duration"):
                    c2.caption(f"Duration: {hike['duration']}")
                if hike.get("region"):
                    c3.caption(f"Region: {hike['region']}")
                if hike.get("description"):
                    st.caption(hike["description"])
                best = hike.get("best_months")
                if best:
                    if isinstance(best, list):
                        best = ", ".join(str(m) for m in best)
                    st.caption(f"\U0001f4c5 Best months: {best}")
                st.divider()

    # ── Wildlife & Nature Zones ───────────────────────────────────────
    with st.expander("\U0001f406 Wildlife & Nature Zones", expanded=False):
        wildlife = _get(data, "outdoors.wildlife", [])
        zones = _get(data, "outdoors.wildlife_zones", [])
        all_wildlife = (wildlife or []) + (zones or [])
        if not all_wildlife:
            _no_data()
        else:
            for item in all_wildlife:
                name = item.get("name") or item.get("zone_name", "Unknown")
                st.markdown(f"**{name}**")
                c1, c2 = st.columns(2)
                if item.get("region"):
                    c1.caption(f"Region: {item['region']}")
                species = item.get("key_species") or item.get("species", [])
                if species:
                    if isinstance(species, list):
                        c2.caption(f"Key species: {', '.join(species)}")
                    else:
                        c2.caption(f"Key species: {species}")
                best = item.get("best_months")
                if best:
                    if isinstance(best, list):
                        best = ", ".join(str(m) for m in best)
                    st.caption(f"\U0001f4c5 Best months: {best}")
                st.divider()

    # ── Surf Spots ────────────────────────────────────────────────────
    with st.expander("\U0001f3c4 Surf Spots", expanded=False):
        spots = _get(data, "outdoors.surf_spots", [])
        if not spots:
            _no_data()
        else:
            for spot in spots:
                name = spot.get("name", "Unknown")
                st.markdown(f"**{name}**")
                c1, c2, c3 = st.columns(3)
                if spot.get("region"):
                    c1.caption(f"Region: {spot['region']}")
                if spot.get("wave_type"):
                    c2.caption(f"Wave type: {spot['wave_type']}")
                if spot.get("difficulty"):
                    c3.caption(f"Difficulty: {spot['difficulty']}")
                best = spot.get("best_months")
                if best:
                    if isinstance(best, list):
                        best = ", ".join(str(m) for m in best)
                    st.caption(f"\U0001f4c5 Best months: {best}")
                if spot.get("description"):
                    st.caption(spot["description"])
                st.divider()

    # ── National Parks & Preserves ────────────────────────────────────
    with st.expander("\U0001f33f National Parks & Preserves", expanded=False):
        parks = _get(data, "outdoors.top_national_parks", [])
        if not parks:
            _no_data()
        else:
            for park in parks:
                if isinstance(park, dict):
                    name = park.get("name", "Unknown")
                    desc = park.get("description", "")
                    st.markdown(f"**{name}**")
                    if desc:
                        st.caption(desc)
                elif isinstance(park, str):
                    st.markdown(f"- {park}")
                st.divider()

    # ── Food & Drink ──────────────────────────────────────────────────
    with st.expander("\U0001f37d\ufe0f Food & Drink", expanded=False):
        food = _get(data, "food")
        if not food:
            _no_data()
        else:
            sig = food.get("signature_dishes") or food.get("dishes", [])
            if sig:
                st.markdown("**Signature Dishes**")
                for item in sig:
                    if isinstance(item, dict):
                        st.markdown(f"- **{item.get('name', '')}** — {item.get('description', '')}")
                    else:
                        st.markdown(f"- {item}")

            drinks = food.get("must_try_drinks") or food.get("drinks", [])
            if drinks:
                st.markdown("**Must-Try Drinks**")
                for d in drinks:
                    if isinstance(d, dict):
                        st.markdown(f"- **{d.get('name', '')}** — {d.get('description', '')}")
                    else:
                        st.markdown(f"- {d}")

            street = food.get("street_food_safety")
            if street:
                st.markdown(f"**Street Food Safety:** {street}")

            alcohol = food.get("alcohol_rules") or food.get("alcohol")
            if alcohol:
                st.markdown(f"**Alcohol Rules:** {alcohol}")

            regional = food.get("regional_specialties", [])
            if regional:
                st.markdown("**Regional Specialties**")
                for r in regional:
                    if isinstance(r, dict):
                        st.markdown(f"- **{r.get('region', '')}**: {r.get('specialty', r.get('description', ''))}")
                    else:
                        st.markdown(f"- {r}")

    # ── Where to Stay ─────────────────────────────────────────────────
    with st.expander("\U0001f3e8 Where to Stay", expanded=False):
        accom = _get(data, "accommodation")
        if not accom:
            _no_data()
        else:
            best_areas = accom.get("best_areas", [])
            if best_areas:
                st.markdown("**Best Areas**")
                for a in best_areas:
                    if isinstance(a, dict):
                        st.markdown(f"- **{a.get('name', '')}** — {a.get('description', '')}")
                    else:
                        st.markdown(f"- {a}")

            surf_towns = accom.get("surf_towns", [])
            if surf_towns:
                st.markdown("**Surf Towns**")
                for t in surf_towns:
                    if isinstance(t, dict):
                        st.markdown(f"- **{t.get('name', '')}** — {t.get('description', '')}")
                    else:
                        st.markdown(f"- {t}")

            eco = accom.get("eco_lodges", [])
            if eco:
                st.markdown("**Eco Lodges**")
                for e in eco:
                    if isinstance(e, dict):
                        st.markdown(f"- **{e.get('name', '')}** — {e.get('description', '')}")
                    else:
                        st.markdown(f"- {e}")

            peak = accom.get("peak_booking_season") or accom.get("peak_season")
            if peak:
                st.markdown(f"**Peak Booking Season:** {peak}")

    # ── Getting Around ────────────────────────────────────────────────
    with st.expander("\U0001f68c Getting Around", expanded=False):
        transport = _get(data, "transport")
        if not transport:
            _no_data()
        else:
            airports = transport.get("airports") or transport.get("main_airports", [])
            if airports:
                st.markdown("**Airports**")
                for a in airports:
                    if isinstance(a, dict):
                        st.markdown(f"- **{a.get('name', '')}** ({a.get('code', '')})")
                    else:
                        st.markdown(f"- {a}")

            transit = transport.get("transit_quality") or transport.get("public_transit")
            if transit:
                st.markdown(f"**Transit Quality:** {transit}")

            ridehail = transport.get("ride_hailing_apps") or transport.get("ride_hailing", [])
            if ridehail:
                if isinstance(ridehail, list):
                    st.markdown(f"**Ride Hailing:** {', '.join(str(r) for r in ridehail)}")
                else:
                    st.markdown(f"**Ride Hailing:** {ridehail}")

            roads = transport.get("road_conditions")
            if roads:
                st.markdown(f"**Road Conditions:** {roads}")

    # ── Budget & Costs ────────────────────────────────────────────────
    with st.expander("\U0001f4b0 Budget & Costs", expanded=False):
        budget = _get(data, "budget")
        if not budget:
            _no_data()
        else:
            tiers = budget.get("daily_budget_tiers") or budget.get("daily_budget", {})
            if tiers:
                st.markdown("**Daily Budget Tiers**")
                if isinstance(tiers, dict):
                    for tier, amount in tiers.items():
                        st.caption(f"**{tier}**: {amount}")
                elif isinstance(tiers, list):
                    for t in tiers:
                        if isinstance(t, dict):
                            st.caption(f"**{t.get('tier', '')}**: {t.get('amount', t.get('range', ''))}")
                        else:
                            st.caption(str(t))

            hostel = budget.get("hostel_avg") or budget.get("hostel")
            hotel = budget.get("hotel_avg") or budget.get("hotel")
            meal = budget.get("meal_avg") or budget.get("meal")
            if hostel:
                st.caption(f"Hostel avg: {hostel}")
            if hotel:
                st.caption(f"Hotel avg: {hotel}")
            if meal:
                st.caption(f"Meal avg: {meal}")

            vfm = budget.get("value_for_money")
            if vfm:
                st.markdown(f"**Value for Money:** {vfm}")

    # ── Health & Vaccines ─────────────────────────────────────────────
    with st.expander("\U0001f4cb Health & Vaccines", expanded=False):
        health = _get(data, "health")
        if not health:
            _no_data()
        else:
            rec = health.get("recommended_vaccines") or health.get("vaccinations", [])
            if rec:
                st.markdown("**Recommended Vaccines**")
                for v in rec:
                    if isinstance(v, dict):
                        st.markdown(f"- **{v.get('name', '')}** — {v.get('notes', '')}")
                    else:
                        st.markdown(f"- {v}")

            req = health.get("required_vaccines", [])
            if req:
                st.markdown("**Required Vaccines**")
                for v in req:
                    if isinstance(v, dict):
                        st.markdown(f"- **{v.get('name', '')}** — {v.get('notes', '')}")
                    else:
                        st.markdown(f"- {v}")

            malaria = health.get("malaria") or health.get("malaria_risk")
            if malaria:
                st.markdown(f"**Malaria:** {malaria}")

            altitude = health.get("altitude_sickness") or health.get("altitude")
            if altitude:
                st.markdown(f"**Altitude Sickness:** {altitude}")

            water = health.get("tap_water") or health.get("water_safety")
            if water:
                st.markdown(f"**Tap Water:** {water}")

    # ── Safety & Scams ────────────────────────────────────────────────
    with st.expander("\U0001f512 Safety & Scams", expanded=False):
        safety = _get(data, "safety")
        if not safety:
            _no_data()
        else:
            advisory = safety.get("advisory_level") or safety.get("travel_advisory")
            if advisory:
                st.markdown(f"**Advisory Level:** {advisory}")

            crime = safety.get("crime_risk") or safety.get("crime")
            if crime:
                st.markdown(f"**Crime Risk:** {crime}")

            scams = safety.get("common_scams", [])
            if scams:
                st.markdown("**Common Scams**")
                for s in scams:
                    if isinstance(s, dict):
                        st.markdown(f"- **{s.get('name', '')}** — {s.get('description', '')}")
                    else:
                        st.markdown(f"- {s}")

            avoid = safety.get("areas_to_avoid", [])
            if avoid:
                st.markdown("**Areas to Avoid**")
                for a in avoid:
                    if isinstance(a, dict):
                        st.markdown(f"- **{a.get('name', '')}** — {a.get('reason', a.get('description', ''))}")
                    else:
                        st.markdown(f"- {a}")

            emergency = safety.get("emergency_numbers") or safety.get("emergency_number")
            if emergency:
                if isinstance(emergency, dict):
                    parts = [f"{k}: {v}" for k, v in emergency.items()]
                    st.markdown("**Emergency Numbers:** " + " | ".join(parts))
                else:
                    st.markdown(f"**Emergency Numbers:** {emergency}")

    # ── Weather & Best Time ───────────────────────────────────────────
    with st.expander("\U0001f324\ufe0f Weather & Best Time", expanded=False):
        weather = _get(data, "weather_and_seasonality")
        if not weather:
            _no_data()
        else:
            zones = weather.get("climate_zones", [])
            if zones:
                st.markdown("**Climate Zones**")
                for z in zones:
                    if isinstance(z, dict):
                        st.markdown(f"- **{z.get('zone', z.get('name', ''))}**: {z.get('description', '')}")
                    else:
                        st.markdown(f"- {z}")

            dry = weather.get("dry_season")
            rainy = weather.get("rainy_season")
            if dry:
                st.markdown(f"**Dry Season:** {dry}")
            if rainy:
                st.markdown(f"**Rainy Season:** {rainy}")

            by_activity = weather.get("best_months_by_activity") or weather.get("best_time", {})
            if by_activity:
                st.markdown("**Best Months by Activity**")
                if isinstance(by_activity, dict):
                    for activity, months in by_activity.items():
                        if isinstance(months, list):
                            st.caption(f"**{activity}**: {', '.join(str(m) for m in months)}")
                        else:
                            st.caption(f"**{activity}**: {months}")
                elif isinstance(by_activity, list):
                    for item in by_activity:
                        if isinstance(item, dict):
                            st.caption(f"**{item.get('activity', '')}**: {item.get('months', '')}")

    # ── Gear Checklist ────────────────────────────────────────────────
    with st.expander("\U0001f392 Gear Checklist", expanded=False):
        gear = _get(data, "gear") or _get(data, "gear_checklist")
        if not gear:
            _no_data()
        else:
            if isinstance(gear, dict):
                for category, items in gear.items():
                    st.markdown(f"**{category}**")
                    if isinstance(items, list):
                        for item in items:
                            st.checkbox(str(item), value=False, disabled=True, key=f"gear_{category}_{item}")
                    else:
                        st.checkbox(str(items), value=False, disabled=True, key=f"gear_{category}")
            elif isinstance(gear, list):
                for item in gear:
                    if isinstance(item, dict):
                        st.checkbox(item.get("name", str(item)), value=False, disabled=True, key=f"gear_{item.get('name', '')}")
                    else:
                        st.checkbox(str(item), value=False, disabled=True, key=f"gear_{item}")

    # ── Laws & Rules ──────────────────────────────────────────────────
    with st.expander("\u2696\ufe0f Laws & Rules", expanded=False):
        laws = _get(data, "laws") or _get(data, "laws_and_rules")
        if not laws:
            _no_data()
        else:
            if isinstance(laws, dict):
                drug = laws.get("drug_laws")
                drone = laws.get("drone_rules") or laws.get("drone_laws")
                photo = laws.get("photography_restrictions") or laws.get("photography")
                if drug:
                    st.markdown(f"**Drug Laws:** {drug}")
                if drone:
                    st.markdown(f"**Drone Rules:** {drone}")
                if photo:
                    st.markdown(f"**Photography Restrictions:** {photo}")
                # Show any other keys
                for k, v in laws.items():
                    if k not in ("drug_laws", "drone_rules", "drone_laws", "photography_restrictions", "photography"):
                        st.markdown(f"**{k.replace('_', ' ').title()}:** {v}")
            elif isinstance(laws, list):
                for item in laws:
                    st.markdown(f"- {item}")

    # ── Sports & Activities ───────────────────────────────────────────
    with st.expander("\U0001f3c3 Sports & Activities", expanded=False):
        sports = _get(data, "sports") or _get(data, "sports_and_activities")
        if not sports:
            _no_data()
        else:
            if isinstance(sports, list):
                for s in sports:
                    if isinstance(s, dict):
                        name = s.get("name", "Unknown")
                        st.markdown(f"**{name}**")
                        c1, c2, c3 = st.columns(3)
                        if s.get("popularity"):
                            c1.caption(f"Popularity: {s['popularity']}")
                        regions = s.get("regions") or s.get("region")
                        if regions:
                            if isinstance(regions, list):
                                c2.caption(f"Regions: {', '.join(regions)}")
                            else:
                                c2.caption(f"Regions: {regions}")
                        best = s.get("best_months")
                        if best:
                            if isinstance(best, list):
                                c3.caption(f"Best months: {', '.join(str(m) for m in best)}")
                            else:
                                c3.caption(f"Best months: {best}")
                        levels = s.get("skill_levels") or s.get("skill_level")
                        if levels:
                            if isinstance(levels, list):
                                st.caption(f"Skill levels: {', '.join(levels)}")
                            else:
                                st.caption(f"Skill levels: {levels}")
                        st.divider()
                    else:
                        st.markdown(f"- {s}")
            elif isinstance(sports, dict):
                for name, details in sports.items():
                    st.markdown(f"**{name.replace('_', ' ').title()}**")
                    if isinstance(details, dict):
                        for k, v in details.items():
                            st.caption(f"{k}: {v}")
                    else:
                        st.caption(str(details))

    # ── Connectivity ──────────────────────────────────────────────────
    with st.expander("\U0001f4f6 Connectivity", expanded=False):
        conn = _get(data, "connectivity")
        if not conn:
            _no_data()
        else:
            sims = conn.get("sim_providers") or conn.get("sim_cards", [])
            if sims:
                if isinstance(sims, list):
                    st.markdown(f"**SIM Providers:** {', '.join(str(s) for s in sims)}")
                else:
                    st.markdown(f"**SIM Providers:** {sims}")

            esim = conn.get("esim")
            if esim:
                st.markdown(f"**eSIM:** {esim}")

            wifi = conn.get("wifi_quality") or conn.get("wifi")
            if wifi:
                st.markdown(f"**WiFi Quality:** {wifi}")

            outlets = conn.get("power_outlets") or conn.get("power")
            if outlets:
                st.markdown(f"**Power Outlets:** {outlets}")

            voltage = conn.get("voltage")
            if voltage:
                st.markdown(f"**Voltage:** {voltage}")

    # ── Family & Accessibility ────────────────────────────────────────
    with st.expander("\U0001f468\u200d\U0001f469\u200d\U0001f467 Family & Accessibility", expanded=False):
        family = _get(data, "family") or _get(data, "family_and_accessibility")
        if not family:
            _no_data()
        else:
            kid_friendly = family.get("kid_friendly")
            if kid_friendly is not None:
                st.markdown(f"**Kid Friendly:** {'Yes' if kid_friendly else 'No'}" if isinstance(kid_friendly, bool) else f"**Kid Friendly:** {kid_friendly}")

            stroller = family.get("stroller") or family.get("stroller_friendly")
            if stroller is not None:
                st.markdown(f"**Stroller Friendly:** {'Yes' if stroller else 'No'}" if isinstance(stroller, bool) else f"**Stroller Friendly:** {stroller}")

            activities = family.get("family_activities", [])
            if activities:
                st.markdown("**Family Activities**")
                for a in activities:
                    if isinstance(a, dict):
                        st.markdown(f"- **{a.get('name', '')}** — {a.get('description', '')}")
                    else:
                        st.markdown(f"- {a}")
