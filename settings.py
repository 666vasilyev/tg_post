import os

from dotenv import load_dotenv

from processor import Options

load_dotenv()


def _flag(name, default="0"):
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
SESSION = os.getenv("SESSION_NAME", "tgposter")
TARGET = os.getenv("TARGET_CHANNEL", "")

# Последовательности, которые вырезаются из текста постов (порядок и состав символов важны)
REMOVE_PHRASES = [
    "😁 • ⚡️",
]

OPTS = Options(
    remove_mentions=_flag("REMOVE_MENTIONS"),
    drop_link_text=_flag("DROP_LINK_TEXT", "1"),
    remove_phrases=tuple(REMOVE_PHRASES),
)
