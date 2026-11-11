"""Проверка работы бота без публикации: печатает в терминал то, что бот отправил бы.

  python check.py              — слушать новые посты в реальном времени
  python check.py --last 5     — сначала прогнать последние 5 постов каждого канала, затем слушать
  python check.py --last 5 --no-live   — только прогнать историю и выйти

Использует отдельную копию сессии (<SESSION>_check.session), поэтому
можно запускать параллельно с main.py и повторный логин не нужен.
"""
import argparse
import asyncio
import shutil
from pathlib import Path

from telethon import TelegramClient

import settings
from core import ConsoleSender, Reposter
from storage import ChannelStore


def prepare_session() -> str:
    src = Path(settings.SESSION + ".session")
    name = settings.SESSION + "_check"
    dst = Path(name + ".session")
    if not dst.exists():
        if not src.exists():
            raise SystemExit("Сначала войдите в аккаунт: python main.py list/add (создаст сессию)")
        shutil.copy(src, dst)
    return name


async def replay(client, reposter, store, limit):
    for ch in store.channels:
        print(f"===== История: {ch['title']} (последние {limit}) =====\n")
        msgs = [m async for m in client.iter_messages(ch["id"], limit=limit * 10)]
        # соберём «посты»: сообщения альбома объединяем по grouped_id
        msgs.sort(key=lambda m: m.id)
        posts, album = [], {}
        for m in msgs:
            if m.grouped_id:
                album.setdefault(m.grouped_id, []).append(m)
            else:
                posts.append([m])
        posts += list(album.values())
        posts.sort(key=lambda p: p[0].id)
        for p in posts[-limit:]:
            await reposter.handle(p)


async def amain(args):
    store = ChannelStore()
    if not store.channels:
        print("Список каналов пуст. Добавьте: python main.py add @channel")
    reposter = Reposter(store, ConsoleSender(args.debug), settings.OPTS)
    async with TelegramClient(prepare_session(), settings.API_ID, settings.API_HASH) as client:
        if args.last:
            await replay(client, reposter, store, args.last)
        if args.no_live:
            return
        reposter.register(client)
        names = ", ".join(c["title"] for c in store.channels) or "—"
        print(f"Слушаю в реальном времени (ничего не публикуется). Источники: {names}\n")
        await client.run_until_disconnected()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--last", type=int, default=0, help="прогнать N последних постов каждого канала")
    ap.add_argument("--no-live", action="store_true", help="не слушать новые посты")
    ap.add_argument("--debug", action="store_true", help="показать исходный и итоговый текст с кодами символов")
    args = ap.parse_args()
    try:
        asyncio.run(amain(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
