"""Общее ядро: подписка на новые посты + «отправитель» (настоящий или консольный)."""
import logging
from datetime import datetime

from telethon import events

from processor import Options, Post, build_post
from storage import ChannelStore

log = logging.getLogger("tg_post")


class TelegramSender:
    """Реально публикует пост в целевой канал."""

    def __init__(self, client, target):
        self.client, self.target = client, target

    async def process(self, post: Post):
        label = f"{post.source_title} #{post.msg_ids[0]}"
        if post.skip_reason:
            log.info("SKIP  %s — %s", label, post.skip_reason)
            return
        text, ents = post.text, post.entities
        parse = lambda _t: (text, ents)  # отдаём Telethon уже готовые entities
        if post.media:
            media = post.media if len(post.media) > 1 else post.media[0]
            await self.client.send_file(self.target, media, caption=text, parse_mode=parse)
        else:
            await self.client.send_message(self.target, text, parse_mode=parse, link_preview=False)
        log.info("POST  %s — отправлено (вложений: %d)", label, len(post.media))


class ConsoleSender:
    """Ничего не отправляет, а печатает то, что было бы опубликовано."""

    def __init__(self, debug=False):
        self.debug = debug

    async def process(self, post: Post):
        ts = datetime.now().strftime("%H:%M:%S")
        ids = ",".join(map(str, post.msg_ids))
        head = f"[{ts}] {post.source_title} #{ids}"
        if post.skip_reason:
            print(f"{head}\n  ⛔ ПРОПУЩЕН: {post.skip_reason}\n")
            return
        print(f"{head}\n  ✅ БЫЛ БЫ ОПУБЛИКОВАН")
        print("  ┌─ текст " + "─" * 40)
        body = post.text or "(без текста)"
        for line in body.split("\n"):
            print("  │ " + line)
        if post.entities:
            kinds = ", ".join(sorted({type(e).__name__.replace("MessageEntity", "") for e in post.entities}))
            print(f"  ├─ форматирование: {kinds}")
        print(f"  └─ вложения: {', '.join(post.media_desc) if post.media_desc else 'нет'}")
        if self.debug:
            print(f"  [debug] исходный текст: {post.raw_text!a}")
            print(f"  [debug] итоговый текст: {post.text!a}")
        print()


class Reposter:
    def __init__(self, store: ChannelStore, sender, opts: Options):
        self.store, self.sender, self.opts = store, sender, opts

    async def handle(self, messages):
        self.store.refresh_if_changed()
        src = self.store.get(messages[0].chat_id)
        if not src:
            return
        try:
            post = build_post(messages, src["title"], self.opts)
            await self.sender.process(post)
        except Exception:
            log.exception("Ошибка при обработке поста %s", [m.id for m in messages])

    def register(self, client):
        @client.on(events.NewMessage())
        async def on_message(event):
            m = event.message
            if m.grouped_id:  # альбомы обрабатываются ниже одним постом
                return
            await self.handle([m])

        @client.on(events.Album())
        async def on_album(event):
            await self.handle(list(event.messages))
