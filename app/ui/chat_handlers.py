import streamlit as st

from agents.local_tool_agent import LocalToolAgent
from services.memory_service import MemoryService
from services.model_service import ModelService
from ui.renderers import build_final_response_text, build_streaming_response_html


def handle_user_message(user_input: str) -> None:
    MemoryService.add_message("user", user_input)
    MemoryService.append_llm_user(user_input)

    with st.chat_message("user"):
        st.markdown(user_input)


def handle_assistant_response(model_service: ModelService) -> None:
    messages = MemoryService.get_llm_messages()
    agent = LocalToolAgent(model_service)

    with st.chat_message("assistant"):
        status_placeholder = st.empty()
        response_placeholder = st.empty()
        buffer = ""

        for event in agent.run(messages):
            if event.kind == "status":
                status_placeholder.caption(f"_{event.text}_")
            elif event.kind == "token":
                buffer += event.text
                response_placeholder.markdown(
                    build_streaming_response_html(buffer),
                    unsafe_allow_html=True,
                )
            elif event.kind == "done":
                buffer = event.text
                status_placeholder.empty()
                response_placeholder.markdown(
                    build_final_response_text(buffer)
                )

    MemoryService.add_message("assistant", buffer)
