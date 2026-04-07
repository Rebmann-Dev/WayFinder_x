import streamlit as st

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
        return {
            "lat": None,
            "lon": None,
            "country": None,
            "location_name": None,
        }

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


def render_chat_page() -> None:
    st.title("Travel Agent AI")
    inject_global_styles()

    MemoryService.initialize()
    model_service = get_model_service()
    safety_service = get_safety_service()

    if "selected_location" not in st.session_state:
        st.session_state["selected_location"] = None

    if "safety_result" not in st.session_state:
        st.session_state["safety_result"] = None

    if "safety_debug" not in st.session_state:
        st.session_state["safety_debug"] = None

    with st.expander("Pick a location on the map", expanded=False):
        picked_location = location_picker(
            key="wayfinder_location_picker",
            height=760,
            default=st.session_state["selected_location"],
        )

        if picked_location:
            st.session_state["selected_location"] = picked_location
            st.session_state["safety_result"] = None

    if st.session_state["selected_location"]:
        selected = st.session_state["selected_location"]
        fields = get_selected_location_fields()

        st.subheader("Selected location")
        st.write(
            {
                "lat": selected.get("lat"),
                "lon": selected.get("lon"),
                "country": selected.get("country"),
                "state_region": selected.get("state_region"),
                "county": selected.get("county"),
                "city": selected.get("city"),
            }
        )

        col1, col2, col3 = st.columns(3)
        col1.metric("Latitude", f"{fields['lat']:.6f}" if fields["lat"] is not None else "—")
        col2.metric("Longitude", f"{fields['lon']:.6f}" if fields["lon"] is not None else "—")
        col3.metric("Country", fields["country"] if fields["country"] else "—")

        can_score = fields["lat"] is not None and fields["lon"] is not None

        if st.button("Run safety score", disabled=not can_score):
            st.session_state["safety_debug"] = "button_clicked"
            try:
                req = SafetyRequest(
                    latitude=float(fields["lat"]),
                    longitude=float(fields["lon"]),
                    country=fields["country"],
                    location_name=fields["location_name"],
                )

                st.session_state["safety_debug"] = {
                    "stage": "request_built",
                    "request": {
                        "latitude": req.latitude,
                        "longitude": req.longitude,
                        "country": req.country,
                        "location_name": req.location_name,
                    },
                }

                result = safety_service.assess_request(
                    req,
                    include_details=True,
                )

                st.session_state["safety_result"] = result
                st.session_state["safety_debug"] = {
                    "stage": "result_returned",
                    "result": result,
                }
                st.success("Safety score completed.")

            except Exception as e:
                st.session_state["safety_debug"] = {
                    "stage": "exception",
                    "error": repr(e),
                }

    if st.session_state["safety_result"] is not None:
        result = st.session_state["safety_result"]

        st.subheader("Safety result")

        if result.get("success"):
            c1, c2, c3 = st.columns(3)
            c1.metric(
                "Safety score",
                f"{result['safety_score']:.2f}" if result.get("safety_score") is not None else "—",
            )
            c2.metric("Risk band", result.get("risk_band") or "—")
            c3.metric("Model", result.get("model_version") or "—")

            with st.expander("Prediction details", expanded=False):
                st.json(result)
        else:
            st.error(f"Safety scoring failed: {result.get('error')}")

    if st.session_state.get("safety_debug") is not None:
        with st.expander("Safety debug", expanded=True):
            st.json(st.session_state["safety_debug"])

    for message in MemoryService.get_display_messages():
        with st.chat_message(message.role):
            st.markdown(message.content)

    if st.button("Clear chat"):
        MemoryService.clear()
        st.rerun()

    user_input = st.chat_input("Ask about routes, destinations, or itineraries...")

    if user_input:
        handle_user_message(user_input)
        handle_assistant_response(model_service)