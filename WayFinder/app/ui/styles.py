import streamlit as st


def inject_global_styles() -> None:
    st.html(
        """
        <style>
        .streaming-response {
            white-space: pre-wrap;
            line-height: 1.6;
            font-family: inherit;
        }

        .blinking-cursor {
            display: inline-block;
            margin-left: 2px;
            animation: blink 1s steps(1) infinite;
        }

        @keyframes blink {
            50% { opacity: 0; }
        }
        </style>
        """
    )
