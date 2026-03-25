import streamlit as st

from services.memory_service import MemoryService
from services.model_service import ModelService
from ui.chat_handlers import handle_assistant_response, handle_user_message
from ui.styles import inject_global_styles


# Bump `_cache_version` when `ModelService` API changes so Streamlit does not reuse
# a stale cached instance from before a reload (missing new methods).
@st.cache_resource
def get_model_service(_cache_version: str = "v3-agent-top5") -> ModelService:
    return ModelService()


def render_chat_page() -> None:
    st.title("Travel Agent AI")
    inject_global_styles()

    MemoryService.initialize()
    model_service = get_model_service()

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
