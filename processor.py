"""Чистая логика обработки постов (без сети) — используется и ботом, и check.py."""
import copy
import re
from dataclasses import dataclass, field

from telethon.tl.types import (
    MessageEntityMention,
    MessageEntityTextUrl,
    MessageEntityUrl,
    MessageMediaContact,
    MessageMediaDice,
    MessageMediaDocument,
    MessageMediaGeo,
    MessageMediaPhoto,
    MessageMediaPoll,
    MessageMediaWebPage,
)

# Ссылки, которые Telegram мог не пометить entity (страховка)
URL_RE = re.compile(
    r"(?i)(?:https?://|tg://|www\.|t\.me/)[^\s<>]*[^\s<>.,;:!?)\]»\"']"
)


@dataclass
class Options:
    remove_mentions: bool = False  # удалять @username
    drop_link_text: bool = False   # удалять текст-гиперссылку целиком (иначе остаётся текст без ссылки)


@dataclass
class Post:
    source_id: int
    source_title: str
    msg_ids: list
    text: str = ""
    entities: list = field(default_factory=list)
    media: list = field(default_factory=list)       # media-объекты Telethon
    media_desc: list = field(default_factory=list)  # человекочитаемо, для check.py
    skip_reason: str | None = None


def _u16(ch: str) -> int:
    return 2 if ord(ch) > 0xFFFF else 1


def _drop(s, idx, spans):
    """Удаляет диапазоны [a,b) из строки s, поддерживая карту idx (новый символ -> исходный индекс)."""
    mask = [False] * len(s)
    for a, b in spans:
        for k in range(a, b):
            mask[k] = True
    return (
        "".join(c for c, m in zip(s, mask) if not m),
        [i for i, m in zip(idx, mask) if not m],
    )


def strip_links(text, entities, opts: Options | None = None):
    """Возвращает (новый_текст, новые_entities) без ссылок.

    Offset/length у Telegram — в UTF-16, поэтому считаем их явно.
    """
    opts = opts or Options()
    text = text or ""
    n = len(text)
    if not n:
        return "", []

    pos16 = [0] * (n + 1)
    for i, ch in enumerate(text):
        pos16[i + 1] = pos16[i] + _u16(ch)
    idx_of = {p: i for i, p in enumerate(pos16)}

    remove = [False] * n
    kept_entities = []  # (entity, start_idx, end_idx)

    def mark(s, t):
        for k in range(s, t):
            remove[k] = True

    for e in entities or []:
        s = idx_of.get(e.offset)
        t = idx_of.get(e.offset + e.length)
        if s is None or t is None:
            continue
        if isinstance(e, MessageEntityUrl):
            mark(s, t)
        elif isinstance(e, MessageEntityTextUrl):
            if opts.drop_link_text:
                mark(s, t)
            # иначе: просто выкидываем entity, текст остаётся
        elif isinstance(e, MessageEntityMention) and opts.remove_mentions:
            mark(s, t)
        else:
            kept_entities.append((e, s, t))

    for m in URL_RE.finditer(text):
        mark(m.start(), m.end())

    # убираем пробелы перед удалённой ссылкой, чтобы не оставались двойные
    i = 0
    while i < n:
        if remove[i]:
            j = i - 1
            while j >= 0 and text[j] in " \t" and not remove[j]:
                remove[j] = True
                j -= 1
            while i < n and remove[i]:
                i += 1
        else:
            i += 1

    idx = [i for i in range(n) if not remove[i]]
    s = "".join(text[i] for i in idx)

    # чистка: пробелы в конце строк, 3+ переводов строк, края
    s, idx = _drop(s, idx, [m.span() for m in re.finditer(r"[ \t]+(?=\n|\Z)", s)])
    s, idx = _drop(s, idx, [(m.start() + 2, m.end()) for m in re.finditer(r"\n{3,}", s)])
    edge = [m.span() for m in re.finditer(r"\A\s+|\s+\Z", s)]
    s, idx = _drop(s, idx, edge)

    kept = set(idx)
    new16 = [0] * (n + 1)
    acc = 0
    for i in range(n):
        new16[i] = acc
        if i in kept:
            acc += _u16(text[i])
    new16[n] = acc

    out = []
    for e, a, b in kept_entities:
        ns, ne = new16[a], new16[b]
        if ne > ns:
            e2 = copy.copy(e)
            e2.offset, e2.length = ns, ne - ns
            out.append(e2)
    return s, out


def describe_media(media) -> str:
    if isinstance(media, MessageMediaPhoto):
        return "photo"
    if isinstance(media, MessageMediaDocument) and media.document:
        d = media.document
        mime = getattr(d, "mime_type", "") or ""
        kinds = {type(a).__name__: a for a in getattr(d, "attributes", [])}
        if "DocumentAttributeAudio" in kinds:
            return "voice" if getattr(kinds["DocumentAttributeAudio"], "voice", False) else "audio"
        if "DocumentAttributeSticker" in kinds:
            return "sticker"
        if "DocumentAttributeVideo" in kinds:
            return "video_note" if getattr(kinds["DocumentAttributeVideo"], "round_message", False) else "video"
        if "DocumentAttributeAnimated" in kinds:
            return "gif"
        name = getattr(kinds.get("DocumentAttributeFilename"), "file_name", "")
        return f"file {name or mime}".strip()
    if isinstance(media, MessageMediaPoll):
        return "poll"
    if isinstance(media, MessageMediaGeo):
        return "geo"
    if isinstance(media, MessageMediaContact):
        return "contact"
    if isinstance(media, MessageMediaDice):
        return "dice"
    return type(media).__name__


def has_comments(msg) -> bool:
    """Комментарии включены, если у поста есть replies с comments=True."""
    r = getattr(msg, "replies", None)
    return bool(r and getattr(r, "comments", False))


def build_post(messages, source_title="", opts: Options | None = None) -> Post:
    """messages — одно сообщение или все сообщения альбома."""
    messages = sorted(messages, key=lambda m: m.id)
    first = messages[0]
    post = Post(
        source_id=first.chat_id,
        source_title=source_title,
        msg_ids=[m.id for m in messages],
    )

    if any(getattr(m, "action", None) for m in messages):
        post.skip_reason = "служебное сообщение"
        return post

    # (а) без комментариев = реклама
    if not any(has_comments(m) for m in messages):
        post.skip_reason = "комментарии отключены (реклама)"
        return post

    # (б) текст без ссылок
    src = next((m for m in messages if m.raw_text), None)
    if src:
        post.text, post.entities = strip_links(src.raw_text, src.entities, opts)

    # (в) все вложения; превью ссылок (webpage) не вложение — ссылки мы убрали
    for m in messages:
        if m.media and not isinstance(m.media, MessageMediaWebPage):
            post.media.append(m.media)
            post.media_desc.append(describe_media(m.media))

    if not post.text and not post.media:
        post.skip_reason = "после удаления ссылок пост пуст"
    return post
