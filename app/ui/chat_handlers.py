import streamlit as st

from agents.local_tool_agent import LocalToolAgent
from services.memory_service import MemoryService
from services.model_service import ModelService
from ui.renderers import build_streaming_response


def handle_user_message(user_input: str) -> None:
    MemoryService.add_message("user", user_input)
    MemoryService.append_llm_user(user_input)

    with st.chat_message("user"):
        st.markdown(user_input)


def handle_assistant_response(model_service: ModelService) -> None:
    MemoryService.trim_llm_thread_for_context()
    messages = MemoryService.get_clean_llm_messages()
    agent = LocalToolAgent(model_service)

    with st.chat_message("assistant"):
        status_placeholder = st.empty()
        response_placeholder = st.empty()
        steps: list[str] = []
        buffer = ""

        for event in agent.run(messages):
            if event.kind == "status":
                steps.append(event.text)
                # Show the current step live while the agent is working
                status_placeholder.caption(f"_{event.text}_")

            elif event.kind == "token":
                buffer += event.text
                response_placeholder.markdown(build_streaming_response(buffer))

            elif event.kind == "done":
                buffer = event.text
                # Clear the live status and render the final response
                status_placeholder.empty()
                response_placeholder.markdown(buffer)

                # Show a collapsed summary of what the agent did
                if steps:
                    with status_placeholder.expander("Steps taken", expanded=False):
                        for i, step in enumerate(steps, 1):
                            st.caption(f"{i}. {step}")

    MemoryService.add_message("assistant", buffer)
