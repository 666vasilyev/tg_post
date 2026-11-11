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

# Точные последовательности, которые вырезаются из текста (порядок символов важен).
# Не используйте вместе с TRIM_LAST_CHARS для одного и того же хвоста — иначе обрежется лишнее.
REMOVE_PHRASES = []

# Сколько последних видимых символов отрезать от текста КАЖДОГО поста (пробелы не считаются,
# эмодзи с селектором — один символ). 0 — не обрезать.
TRIM_LAST_CHARS = int(os.getenv("TRIM_LAST_CHARS", "3"))

OPTS = Options(
    remove_mentions=_flag("REMOVE_MENTIONS"),
    drop_link_text=_flag("DROP_LINK_TEXT", "1"),
    remove_phrases=tuple(REMOVE_PHRASES),
    trim_tail=TRIM_LAST_CHARS,
)
