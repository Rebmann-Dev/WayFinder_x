import html


def build_streaming_response_html(text: str) -> str:
    safe_text = html.escape(text)

    return f"""
    <div class="streaming-response">
        {safe_text}<span class="blinking-cursor">▌</span>
    </div>
    """


def build_streaming_response(buffer: str) -> str:
    """Text shown token-by-token during streaming. Cursor appended inline."""
    return buffer + "▌"
