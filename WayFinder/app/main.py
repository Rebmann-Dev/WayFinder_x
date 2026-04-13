import logging

from ui.chat_page import render_chat_page

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-22s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)


def main() -> None:
    render_chat_page()


if __name__ == "__main__":
    main()
